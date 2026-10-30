"""Offline execution of shipped Manual templates/scripts with a simulated clock.
The small delay_on model does not validate HA's scheduler or real Modbus timing.
"""
import datetime as dt
import json
import unittest
import test_bender_stop_safety as base
from test_bender_stop_safety import Harness, PACKAGE, TEMPLATES, ROOT

START = base.NOW
INTENT = 'input_number.bender_manual_desired_current'
CMD = 'input_number.bender_commanded_current'
REQUEST = 'input_number.bender_requested_current'
READY = 'binary_sensor.bender_manual_increase_ready'
STRATEGY = 'input_select.bender_charging_strategy'
LB = 'sensor.bender_loadbalancer_available_current'

class ManualSimulation(Harness):
    def __init__(self, desired=16, commanded=16):
        super().__init__()
        self.since = None
        for entity, value in [(STRATEGY,'Manual'), (INTENT,float(desired)),
            (CMD,float(commanded)), (REQUEST,float(commanded)),
            ('input_number.bender_strategy_max_current',16), (READY,'off')]:
            self.states.set(entity,value,changed=base.NOW-60)
        self.feedback(commanded)
        self.evaluate()
    def feedback(self, current=None):
        current = float(self.states(CMD)) if current is None else current
        self.states.set('sensor.bender_hems_limit',current)
        self.states.set('sensor.bender_totalpower',0 if current==0 else current*690)
        for p in (1,2,3): self.states.set(f'sensor.bender_current_l{p}',current*1000)
    def evaluate(self):
        self.states.set('binary_sensor.bender_hems_command_confirmed',
            'on' if self.template('bender_hems_command_confirmed')=='True' else 'off')
        self.states.set('binary_sensor.bender_manual_feedback_fresh',
            'on' if self.template('bender_manual_feedback_fresh')=='True' else 'off')
        if self.template('bender_manual_increase_ready')=='True':
            if self.since is None: self.since=base.NOW
        else: self.since=None
        self.states.set(READY,'on' if self.since is not None and base.NOW-self.since>=30 else 'off')
    def tick(self, seconds=5, reports=True, reconcile=True):
        base.NOW += seconds
        self.states.set('sensor.dsmr_reading_timestamp',dt.datetime.fromtimestamp(base.NOW,dt.timezone.utc).isoformat())
        if reports:self.feedback()
        self.evaluate()
        if reconcile:
            self.run('bender_manual_reconcile')
            # HA state triggers re-evaluate feedback immediately after a command.
            self.evaluate()
    def advance(self, seconds, **kwargs):
        for _ in range(seconds//5):self.tick(**kwargs)
    def command(self):return int(float(self.states(CMD)))
    def desired(self):return int(float(self.states(INTENT)))

class ManualMemoryTests(unittest.TestCase):
    def setUp(self):base.NOW=START
    def tearDown(self):base.NOW=START
    def test_recorded_16_to_12_limit_then_four_confirmed_one_amp_steps(self):
        h=ManualSimulation();h.states.set(LB,12.7);h.run('bender_manual_reconcile')
        self.assertEqual(h.command(),12);self.assertEqual(h.desired(),16)
        h.states.set(LB,16)
        h.advance(30);self.assertEqual(h.command(),12)
        h.advance(110)
        self.assertEqual([c[1] for c in h.calls],[12,13,14,15,16])
        self.assertEqual(h.desired(),16)
        h.advance(60);self.assertEqual(len(h.calls),5)
    def test_below_ev_minimum_stops_and_stale_current_cannot_start_again(self):
        h=ManualSimulation();h.states.set(LB,5.9);h.run('bender_manual_reconcile')
        self.assertEqual(h.command(),0);self.assertEqual(h.desired(),16)
        h.states.set(LB,16)
        # HEMS says zero, but phase measurements still show the old load.
        h.states.set('sensor.bender_hems_limit',0)
        h.advance(40,reports=False)
        self.assertEqual(h.command(),0)
        h.advance(35)
        self.assertEqual(h.command(),6);self.assertEqual(h.desired(),16)
    def test_pause_cancels_recovery_and_old_flow_messages_cannot_resume(self):
        for entry in ['bender_stop_charging','bender_manual_set_current']:
            with self.subTest(entry=entry):
                h=ManualSimulation(commanded=12);h.run(entry,current=0)
                self.assertEqual(h.desired(),0);self.assertEqual(h.command(),0)
                h.advance(120)
                h.run('bender_set_charging_current',current=16)
                h.run('set_bender_hems_limit',current=16)
                self.assertEqual(h.command(),0);self.assertEqual(h.desired(),0)
    def test_fault_preserves_choice_and_recovery_ramps_but_pause_during_fault_wins(self):
        for pause in (False,True):
            h=ManualSimulation();h.states.set('input_boolean.bender_failsafe_active','on')
            h.states.set('binary_sensor.bender_charging_control_healthy','off')
            h.run('bender_manual_reconcile');self.assertEqual(h.command(),0)
            self.assertEqual(h.desired(),16)
            if pause:h.run('bender_stop_charging')
            h.feedback(0);h.states.set('input_boolean.bender_failsafe_active','off')
            h.states.set('binary_sensor.bender_charging_control_healthy','on')
            h.advance(35)
            self.assertEqual(h.command(),0 if pause else 6)
            self.assertEqual(h.desired(),0 if pause else 16)
    def test_requested_lower_value_and_maximum_limit_lower_immediately(self):
        h=ManualSimulation();h.run('bender_manual_set_current',current=10)
        self.assertEqual(h.command(),10);self.assertEqual(h.desired(),10)
        h.run('bender_manual_set_current',current=16)
        self.assertEqual(h.command(),10);self.assertEqual(h.desired(),16)
        h.states.set('input_number.bender_strategy_max_current',8)
        h.run('bender_manual_reconcile');self.assertEqual(h.command(),8)
        h.advance(40);self.assertEqual(h.command(),8)
        h.states.set('input_number.bender_strategy_max_current',16)
        h.advance(30);self.assertEqual(h.command(),8)
        h.advance(5);self.assertEqual(h.command(),9)
    def test_brief_headroom_dip_restarts_continuous_wait(self):
        h=ManualSimulation(commanded=12);h.advance(25)
        h.states.set(LB,12);h.evaluate();h.run('bender_manual_reconcile')
        h.states.set(LB,16);h.evaluate()
        h.advance(25);self.assertEqual(h.command(),12)
        h.advance(5);self.assertEqual(h.command(),13)
    def test_stale_ready_flag_cannot_bypass_raw_feedback_or_rearm(self):
        for entity,value,reported in [
            ('sensor.bender_current_l1',12000,START-26),
            ('sensor.bender_current_l2','unknown',START),
            ('sensor.bender_current_l3',12000,START+1),
            ('sensor.bender_totalpower','nan',START),
            ('sensor.bender_hems_limit',12,START-46),
            ('sensor.bender_hems_limit',11,START),
            ('sensor.bender_current_l1',16000,START)]:
            h=ManualSimulation(commanded=12);h.states.set(READY,'on')
            h.states.set(entity,value,reported=reported)
            h.run('bender_manual_reconcile')
            self.assertLessEqual(h.command(),12,(entity,value,reported))
        h=ManualSimulation(commanded=12);h.states.set(READY,'on',changed=START-30)
        h.states.set(INTENT,16.0,changed=START-10)
        h.run('bender_manual_reconcile');self.assertEqual(h.command(),12)
    def test_bad_source_data_blocks_manual_even_when_cached_health_and_ready_are_green(self):
        for entity,value in [('sensor.dsmr_reading_phase_voltage_l1',0),
            ('sensor.dsmr_reading_timestamp','unavailable'),(LB,'nan'),(LB,'unknown')]:
            h=ManualSimulation(commanded=12);h.states.set(READY,'on');h.states.set(entity,value)
            h.run('bender_manual_reconcile');self.assertEqual(h.command(),0)
            self.assertEqual(h.desired(),16)
    def test_unconfirmed_write_cannot_accumulate_extra_steps(self):
        h=ManualSimulation(commanded=12);h.advance(30)
        self.assertEqual(h.command(),13)
        h.advance(30,reports=False)
        self.assertLessEqual(h.command(),13)
        self.assertNotIn(14,[c[1] for c in h.calls])
    def test_failed_write_retains_intent_and_no_positive_credit(self):
        h=ManualSimulation(commanded=0);h.states.set(READY,'on');h.fail_write=True
        with self.assertRaises(RuntimeError):h.run('bender_manual_reconcile')
        self.assertEqual(h.command(),0);self.assertEqual(h.desired(),16)
        self.assertEqual(float(h.states(REQUEST)),6)
        deadline=h.states('input_number.bender_hems_unconfirmed_since')
        base.NOW+=5
        h.run('bender_manual_reconcile');self.assertEqual(len(h.background_errors),1)
        self.assertEqual(h.states('input_number.bender_hems_unconfirmed_since'),deadline)
    def test_restart_uses_saved_choice_but_zero_command_and_fresh_confirmation(self):
        self.assertNotIn('initial',PACKAGE['input_number']['bender_manual_desired_current'])
        self.assertEqual(PACKAGE['input_number']['bender_manual_desired_current']['min'],0)
        for desired in [0,16]:
            h=ManualSimulation(desired=desired,commanded=0)
            h.run('bender_manual_reconcile');self.assertEqual(h.command(),0)
            h.advance(30);self.assertEqual(h.command(),0 if desired==0 else 6)
    def test_strategy_exit_clears_choice_and_delayed_manual_call_does_not_touch_direct(self):
        h=ManualSimulation();h.states.set(STRATEGY,'Direct')
        automation=next(a for a in PACKAGE['automation'] if a.get('id')=='bender_manual_clear_on_strategy_change')
        self.assertTrue(h.conditions(automation['condition'],{}))
        h.sequence(automation['action'],{})
        self.assertEqual(h.desired(),0)
        h.run('set_bender_hems_limit',current=16,expected_strategy='Manual')
        h.run('bender_manual_reconcile');self.assertFalse(h.calls)
        h.states.set(STRATEGY,'Manual');h.run('bender_manual_reconcile')
        self.assertEqual(h.command(),0)
    def test_invalid_choices_do_not_change_intent(self):
        for value in [-1,1,5,6.5,17,'unknown','nan','inf']:
            h=ManualSimulation();h.run('bender_manual_set_current',current=value)
            self.assertEqual(h.desired(),16);self.assertFalse(h.calls)
    def test_pause_between_helper_updates_and_modbus_prevents_stale_write(self):
        h=ManualSimulation(commanded=12);h.states.set(READY,'on')
        original=h.states.set
        def pause_on_request(entity,value,**kwargs):
            original(entity,value,**kwargs)
            if entity==REQUEST:
                base.NOW+=0.01
                original(INTENT,0.0)
        h.states.set=pause_on_request
        h.run('bender_manual_reconcile');self.assertFalse(h.calls)
        h.run('bender_manual_reconcile');self.assertEqual(h.command(),0)
    def test_disconnected_car_still_recovers_limit_without_inventing_load(self):
        class IdleSimulation(ManualSimulation):
            def feedback(self,current=None):
                super().feedback(current)
                self.states.set('sensor.bender_totalpower',0)
                for p in (1,2,3):self.states.set(f'sensor.bender_current_l{p}',0)
        h=IdleSimulation(commanded=12)
        h.advance(140)
        self.assertEqual(h.command(),16);self.assertEqual(h.desired(),16)
        self.assertEqual([c[1] for c in h.calls],[13,14,15,16])
    def test_failed_pause_is_not_forgotten_and_retry_never_restores_old_choice(self):
        h=ManualSimulation();h.fail_write=True
        h.run('bender_stop_charging');self.assertEqual(len(h.background_errors),1)
        self.assertEqual(h.desired(),0);self.assertEqual(h.command(),0)
        self.assertEqual(float(h.states('sensor.bender_hems_limit')),16)
        h.fail_write=False;h.run('bender_manual_reconcile')
        self.assertEqual(h.calls[-1][1],0)
        h.advance(120)
        self.assertTrue(all(c[1]==0 for c in h.calls));self.assertEqual(h.desired(),0)
    def test_30_second_hems_and_10_second_phase_polling_allow_bounded_progress(self):
        h=ManualSimulation(commanded=12)
        commands=[]
        for elapsed in range(5,241,5):
            base.NOW+=5
            h.states.set('sensor.dsmr_reading_timestamp',dt.datetime.fromtimestamp(base.NOW,dt.timezone.utc).isoformat())
            if elapsed%30==0:h.states.set('sensor.bender_hems_limit',h.command())
            if elapsed%10==0:
                h.states.set('sensor.bender_totalpower',h.command()*690)
                for p in (1,2,3):h.states.set(f'sensor.bender_current_l{p}',h.command()*1000)
            h.evaluate();before=h.command();h.run('bender_manual_reconcile');h.evaluate()
            if h.command()!=before:commands.append((elapsed,h.command()))
        self.assertEqual([c for t,c in commands],[13,14,15,16])
        self.assertTrue(all(b[0]-a[0]>=30 for a,b in zip(commands,commands[1:])))

    def test_nodered_only_reconciles_and_dashboard_buttons_are_explicit_choices(self):
        nodes=json.loads((ROOT/'NodeRed/bender_strategy_manual.json').read_text())
        action=next(n for n in nodes if n['type']=='api-call-service')
        self.assertEqual(action['action'],'script.bender_manual_reconcile')
        self.assertEqual(action['queue'],'none');self.assertTrue(action['blockInputOverrides'])
        self.assertFalse(any(n['type']=='api-current-state' for n in nodes))
        dashboard=(ROOT/'HomeAssistant/dashboards/bender_chargepoint.yaml').read_text()
        self.assertEqual(dashboard.count('service: script.bender_manual_set_current'),3)
        self.assertNotIn('bender_failsafe_manual_restore_pending',str(PACKAGE))
        self.assertEqual(TEMPLATES['bender_manual_increase_ready']['delay_on'],'00:00:30')

if __name__=='__main__':unittest.main()
