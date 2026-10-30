"""Regression tests for independent HEMS acknowledgement and downward-only enforcement.
Uses the deployed YAML expressions/scripts, with simulated state reports and Modbus failures.
"""
import unittest,datetime as dt
from test_bender_stop_safety import Harness,PACKAGE,NOW
GUARD=next(a for a in PACKAGE['automation'] if a.get('id')=='bender_independent_hems_guard')
WATCHDOG=next(a for a in PACKAGE['automation'] if a.get('id')=='bender_hard_failsafe_watchdog')
RECOVERED=next(a for a in PACKAGE['automation'] if a.get('id')=='bender_hard_failsafe_recovered')
class ConfirmationTests(unittest.TestCase):
    def harness(self,target=6,reported=0,age=20):
        h=Harness();h.states.set('input_select.bender_charging_strategy','ChargePV')
        h.states.set('input_number.bender_requested_current',target,changed=NOW-age)
        h.states.set('input_number.bender_hems_unconfirmed_since',NOW-age)
        h.states.set('sensor.bender_hems_limit',reported,reported=NOW)
        return h
    def test_pending_window_and_timeout_are_bounded(self):
        for age,healthy in [(0,True),(44.9,True),(45,True),(45.1,False),(60,False)]:
            h=self.harness(age=age)
            self.assertEqual(h.template('bender_hems_command_confirmed'),'False')
            self.assertEqual(h.template('bender_hems_control_healthy'),str(healthy),age)
    def test_service_success_is_not_feedback_confirmation(self):
        h=Harness();h.states.set('input_select.bender_charging_strategy','ChargePV');h.run('set_bender_hems_limit',current=6)
        self.assertEqual(h.states('input_number.bender_commanded_current'),'6.0')
        self.assertEqual(h.states('input_number.bender_requested_current'),'6.0')
        self.assertEqual(h.template('bender_hems_command_confirmed'),'False')
        h.states.set('sensor.bender_hems_limit',6)
        self.assertEqual(h.template('bender_hems_command_confirmed'),'True')
    def test_failed_write_keeps_request_and_deadline_but_no_positive_credit(self):
        h=Harness();h.states.set('input_select.bender_charging_strategy','ChargePV');h.fail_write=True
        with self.assertRaises(RuntimeError):h.run('set_bender_hems_limit',current=10)
        self.assertEqual(h.states('input_number.bender_requested_current'),'10.0')
        self.assertEqual(float(h.states('input_number.bender_hems_unconfirmed_since')),NOW)
        self.assertEqual(h.states('input_number.bender_commanded_current'),'0.0')
    def test_retries_and_changed_targets_do_not_extend_oldest_deadline(self):
        h=self.harness(age=25)
        for target in [6,7,8,10,0]:
            h.run('set_bender_hems_limit',current=target)
            self.assertEqual(float(h.states('input_number.bender_hems_unconfirmed_since')),NOW-25)
    def test_confirmed_retries_do_not_churn_deadline_helper(self):
        h=self.harness(target=6,reported=6,age=20)
        h.states.set('input_number.bender_commanded_current',6)
        h.states.set('input_number.bender_hems_unconfirmed_since',0)
        h.run('set_bender_hems_limit',current=6)
        self.assertFalse(h.calls)
        self.assertEqual(float(h.states('input_number.bender_hems_unconfirmed_since')),0)
    def test_resolved_old_request_allows_new_deadline(self):
        h=self.harness(target=6,reported=6,age=200)
        h.run('set_bender_hems_limit',current=10)
        self.assertEqual(float(h.states('input_number.bender_hems_unconfirmed_since')),NOW)
    def test_fresh_exact_read_after_request_is_required(self):
        for value,when,expected in [('6',NOW,True),('6',NOW-21,False),('6.9',NOW,False),('6',NOW+1,False),('nan',NOW,False),('unknown',NOW,False),('unavailable',NOW,False)]:
            h=self.harness(age=20);h.states.set('sensor.bender_hems_limit',value,reported=when)
            self.assertEqual(h.template('bender_hems_command_confirmed'),str(expected),(value,when))
    def test_steady_equal_values_must_still_be_reported_within_45s(self):
        for age,expected in [(44.9,True),(45,True),(45.1,False)]:
            h=self.harness(target=0,reported=0,age=1000)
            h.states.set('sensor.bender_hems_limit',0,changed=NOW-86400,reported=NOW-age)
            self.assertEqual(h.template('bender_hems_command_confirmed'),str(expected))
            self.assertEqual(h.template('bender_hems_control_healthy'),str(expected))
    def test_old_matching_feedback_does_not_suppress_write(self):
        h=self.harness(target=0,reported=0,age=20);h.states.set('sensor.bender_hems_limit',0,reported=NOW-21)
        h.run('set_bender_hems_limit',current=0);self.assertEqual(h.calls[-1][1],0)
    def test_failsafe_cannot_recover_on_grace_or_positive_confirmation(self):
        h=self.harness(target=6,reported=6);h.states.set('input_boolean.bender_failsafe_active','on')
        self.assertEqual(h.template('bender_hems_control_healthy'),'False')
        h.states.set('input_number.bender_requested_current',0)
        self.assertEqual(h.template('bender_hems_control_healthy'),'False')
        h.states.set('sensor.bender_hems_limit',0)
        self.assertEqual(h.template('bender_hems_control_healthy'),'True')
        self.assertIn({'condition':'state','entity_id':'binary_sensor.bender_hems_control_healthy','state':'on'},RECOVERED['condition'])
    def test_healthy_heartbeat_cannot_mask_hems_failure(self):
        h=self.harness(age=46);h.states.set('binary_sensor.bender_hems_control_healthy','off')
        v=h.variables(WATCHDOG['variables']);fault=next(a['choose'] for a in WATCHDOG['action'] if 'choose' in a)[1]['conditions']
        self.assertTrue(v['nodered_healthy']);self.assertFalse(v['hems_healthy']);self.assertTrue(h.conditions(fault,v))
        self.assertIn('HEMS',v['failure_reason'])
    def test_guard_lowers_with_green_heartbeat_and_never_raises(self):
        h=self.harness(target=16,reported=16);h.states.set('sensor.bender_loadbalancer_available_current',10.8)
        v=h.variables(GUARD['variables']);self.assertTrue(v['must_lower']);self.assertEqual(v['lower_target'],10)
        for lb in [0,5.9,6,10,16,'unknown','nan']:
            for requested in [0,6,10,16]:
                h=self.harness(target=requested,reported=requested);h.states.set('sensor.bender_loadbalancer_available_current',lb)
                v=h.variables(GUARD['variables']);self.assertLessEqual(v['lower_target'],requested)
                self.assertIn(v['lower_target'],[0,*range(6,17)])
    def test_off_and_health_faults_make_zero_the_only_guard_target(self):
        for entity,value in [('input_select.bender_charging_strategy','Uit'),('binary_sensor.bender_dsmr_data_healthy','off'),('binary_sensor.bender_nodered_heartbeat_healthy','off'),('input_boolean.bender_failsafe_active','on')]:
            h=self.harness(target=16,reported=16);h.states.set(entity,value)
            self.assertEqual(h.variables(GUARD['variables'])['lower_target'],0)
    def test_stop_retry_is_independent_but_does_not_interrupt_busy_writer(self):
        h=self.harness(target=0,reported='unavailable',age=20);v=h.variables(GUARD['variables'])
        self.assertTrue(v['retry_stop']);conditions=GUARD['action'][1]['if']
        self.assertTrue(h.conditions(conditions,v))
        h.states.set('script.set_bender_hems_limit','on');self.assertFalse(h.conditions(conditions,v))
        h.states.set('script.set_bender_hems_limit','off')
        for mode in ['Uit','Monitoren']:
            h.states.set('input_select.bender_failsafe_mode',mode);self.assertFalse(h.conditions(conditions,v))
    def test_aged_or_unknown_feedback_blocks_positive_writer_in_active_mode(self):
        for value in [0,'unknown']:
            h=self.harness(target=0,reported=value,age=90);h.states.set('sensor.bender_hems_limit',value,reported=NOW-46)
            h.run('set_bender_hems_limit',current=16)
            self.assertEqual(h.calls[-1][1],0)
    def test_notification_failures_do_not_abort_watchdog_or_recovery(self):
        def walk(actions):
            for a in actions:
                if a.get('action')=='notify.send_message':yield a
                for key in ['then','else','default']:yield from walk(a.get(key,[]))
                for choice in a.get('choose',[]):yield from walk(choice['sequence'])
        notifications=list(walk(WATCHDOG['action']))+list(walk(RECOVERED['action']))
        self.assertEqual(len(notifications),2)
        self.assertTrue(all(a.get('continue_on_error') for a in notifications))
if __name__=='__main__':unittest.main()
