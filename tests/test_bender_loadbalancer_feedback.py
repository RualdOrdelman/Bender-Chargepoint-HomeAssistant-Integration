"""Closed-loop regressions using shipped templates and scripts; no network/HA writes.
Reports and command updates are deliberately separate, like P1 and Modbus polling.
"""
import unittest
import test_bender_stop_safety as base
from test_bender_manual_memory import ManualSimulation, START, CMD, LB


class LoadbalancerFeedbackTests(unittest.TestCase):
    def setUp(self): base.NOW = START
    def tearDown(self): base.NOW = START

    def setup_night(self):
        h = ManualSimulation(desired=16, commanded=16)
        h.states.set('input_number.bender_house_max_power', 17250)
        h.states.set('input_number.bender_loadbalancer_margin', 1000)
        # 18 November 06:42:08: independent P1/Modbus samples, before car reacted.
        for phase, grid, voltage, current in [(1, 3.675, 230.2, 15002),
                (2, 5.548, 231.4, 15047), (3, 3.544, 232.1, 15083)]:
            h.states.set(f'sensor.dsmr_reading_phase_currently_delivered_l{phase}', grid)
            h.states.set(f'sensor.dsmr_reading_phase_currently_returned_l{phase}', 0)
            h.states.set(f'sensor.dsmr_reading_phase_voltage_l{phase}', voltage)
            h.states.set(f'sensor.bender_current_l{phase}', current)
        return h

    def cycle(self, h):
        h.states.set(LB, h.template('bender_loadbalancer_available_current'))
        h.run('bender_manual_reconcile')
        return h.command()

    def test_recorded_night_reduces_once_to_14_not_cascade_to_zero(self):
        h = self.setup_night()
        before = [h.template(f'bender_house_consumption_l{p}') for p in (1,2,3)]
        self.assertEqual(float(h.template('bender_loadbalancer_available_current')), 14.6)
        self.assertEqual([self.cycle(h) for _ in range(12)], [14]*12)
        self.assertEqual(h.desired(), 16)
        self.assertEqual(before, [h.template(f'bender_house_consumption_l{p}') for p in (1,2,3)])
        self.assertEqual(float(h.states('input_number.bender_loadbalancer_margin')), 1000)

    def test_arriving_reduced_current_and_matching_p1_settle_without_more_reduction(self):
        h = self.setup_night(); self.cycle(h)
        # Same house load; car current and P1 finally reflect the new 14A command.
        for p in (1,2,3):
            voltage=float(h.states(f'sensor.dsmr_reading_phase_voltage_l{p}'))
            old=float(h.states(f'sensor.bender_current_l{p}'))/1000
            grid=float(h.states(f'sensor.dsmr_reading_phase_currently_delivered_l{p}'))
            h.states.set(f'sensor.dsmr_reading_phase_currently_delivered_l{p}',grid-(old-14)*voltage/1000)
            h.states.set(f'sensor.bender_current_l{p}',14000)
        self.assertEqual([self.cycle(h) for _ in range(5)], [14]*5)

    def test_new_overload_during_pending_reduction_is_not_delayed(self):
        for extra, expected in [(1.0,10),(2.1,0),(5,0)]:
            with self.subTest(extra_kw=extra):
                h=self.setup_night();self.assertEqual(self.cycle(h),14)
                h.states.set('sensor.dsmr_reading_phase_currently_delivered_l2',5.548+extra)
                # No clock advance, confirmation or new Modbus report required to reduce.
                self.assertEqual(self.cycle(h),expected)
                self.assertEqual(h.calls[-1][1],expected)
                self.assertEqual(h.desired(),16)

    def test_direct_writer_also_reduces_immediately_without_confirmation(self):
        h=self.setup_night();h.states.set('input_select.bender_charging_strategy','Direct')
        for expected,grid in [(14,5.548),(10,6.548),(0,7.648)]:
            h.states.set('sensor.dsmr_reading_phase_currently_delivered_l2',grid)
            h.states.set(LB,h.template('bender_loadbalancer_available_current'))
            h.run('set_bender_hems_limit',current=16)
            self.assertEqual(h.command(),expected)

    def test_each_phase_can_independently_force_immediate_stop(self):
        for p in (1,2,3):
            h=self.setup_night()
            h.states.set(f'sensor.dsmr_reading_phase_currently_delivered_l{p}',9)
            self.assertEqual(self.cycle(h),0)

    def test_zero_command_never_credits_old_current_and_pause_survives(self):
        h=self.setup_night();h.run('bender_manual_set_current',current=0)
        # Grid falls first; old charger measurements would otherwise invent spare room.
        for p in (1,2,3):h.states.set(f'sensor.dsmr_reading_phase_currently_delivered_l{p}',4.6)
        self.assertLess(float(h.template('bender_loadbalancer_available_current')),6)
        self.assertEqual([self.cycle(h) for _ in range(10)],[0]*10)
        self.assertEqual(h.desired(),0)
        self.assertEqual(h.template('bender_charger_stopped_fresh'),'False')

    def test_lower_p1_before_modbus_confirmation_does_not_raise_current(self):
        h=self.setup_night();self.cycle(h)
        h.states.set('sensor.dsmr_reading_phase_currently_delivered_l2',4.0)
        # Sensor now says 16A; Manual must still await actual settled feedback.
        self.assertEqual(float(h.template('bender_loadbalancer_available_current')),16)
        self.assertEqual([self.cycle(h) for _ in range(5)],[14]*5)
        self.assertEqual(h.template('bender_manual_feedback_fresh'),'False')

    def test_bad_old_future_and_missing_measurement_cannot_add_capacity(self):
        for value,reported in [('unknown',START),('unavailable',START),('NaN',START),
                ('inf',START),(-1,START),(17001,START),(15047,START-25.1),(15047,START+1)]:
            with self.subTest(value=value,reported=reported):
                h=self.setup_night();h.states.set('sensor.bender_current_l2',value,reported=reported)
                self.assertEqual(self.cycle(h),0)
        h=self.setup_night();h.states.items.pop('sensor.bender_current_l2')
        self.assertEqual(self.cycle(h),0)

    def test_unchanged_fresh_current_is_valid_and_all_views_agree(self):
        h=self.setup_night()
        for p in (1,2,3):
            h.states.set(f'sensor.bender_current_l{p}',15000,changed=START-86400,reported=START)
        for cmd in (16,14,10,6):
            h.states.set(CMD,cmd)
            per_phase=[float(h.template(f'bender_lb_available_current_l{p}')) for p in (1,2,3)]
            self.assertEqual(float(h.template('bender_loadbalancer_available_current')),min(per_phase))
            for p,room in enumerate(per_phase,1):
                v=float(h.states(f'sensor.dsmr_reading_phase_voltage_l{p}'))
                house=float(h.template(f'bender_house_consumption_l{p}'))
                self.assertAlmostEqual(room,(17250-1000)/690-house/v,delta=.06)

    def test_credit_bounded_by_installation_max_and_invalid_command_gives_none(self):
        h=self.setup_night();h.states.set('sensor.bender_current_l2',17000)
        self.assertLessEqual(float(h.template('bender_lb_available_current_l2')),15.6)
        for cmd in (0,-1,5,17,'unknown','NaN',6.5):
            h=self.setup_night();h.states.set(CMD,cmd)
            self.assertEqual(float(h.template('bender_loadbalancer_available_current')),0)

if __name__=='__main__': unittest.main()
