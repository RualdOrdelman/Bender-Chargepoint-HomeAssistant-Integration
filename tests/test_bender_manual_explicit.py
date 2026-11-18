"""Execute real YAML: explicit intent may jump; automatic recovery still ramps."""
import asyncio
import unittest
import test_bender_stop_safety as base
from test_bender_manual_memory import ManualSimulation, START, INTENT, CMD, REQUEST, LB
from test_bender_pause_concurrency import AsyncYaml


class ExplicitChoiceTests(unittest.TestCase):
    def setUp(self): base.NOW = START
    def tearDown(self): base.NOW = START

    def test_explicit_choices_start_and_raise_immediately_with_fresh_confirmation(self):
        for previous in (0, 6, 10, 12):
            for chosen in (6, 10, 16):
                with self.subTest(previous=previous, chosen=chosen):
                    h=ManualSimulation(desired=0,commanded=previous)
                    h.run('bender_manual_set_current',current=chosen)
                    self.assertEqual(h.command(),chosen)
                    self.assertEqual(h.desired(),chosen)

    def test_clicking_same_saved_choice_retries_explicitly(self):
        h=ManualSimulation(desired=16,commanded=6)
        h.run('bender_manual_set_current',current=16)
        self.assertEqual(h.command(),16)

    def test_limits_still_apply_and_automatic_recovery_has_no_fast_flag(self):
        h=ManualSimulation(desired=0,commanded=0)
        h.states.set(LB,10.8)
        h.run('bender_manual_set_current',current=16)
        self.assertEqual(h.command(),10);self.assertEqual(h.desired(),16)
        h.states.set(LB,16);h.advance(30)
        self.assertEqual(h.command(),10)
        h.advance(5);self.assertEqual(h.command(),11)
        h=ManualSimulation(desired=0,commanded=0)
        h.states.set('input_number.bender_strategy_max_current',8)
        h.run('bender_manual_set_current',current=16)
        self.assertEqual(h.command(),8)

    def test_invalid_feedback_or_unconfirmed_stop_prevents_fast_start(self):
        for entity,value,reported in [
            ('sensor.bender_hems_limit',6,START),
            ('sensor.bender_hems_limit',0,START-46),
            ('sensor.bender_current_l1',0,START-26),
            ('sensor.bender_current_l2','unknown',START),
            ('sensor.bender_current_l3',201,START),
            ('sensor.bender_totalpower',51,START),
            ('sensor.bender_current_l1',0,START+1)]:
            with self.subTest(entity=entity,value=value,reported=reported):
                h=ManualSimulation(desired=0,commanded=0)
                h.states.set(entity,value,reported=reported)
                h.run('bender_manual_set_current',current=16)
                self.assertEqual(h.command(),0)

    def test_faults_zero_worker_and_bad_dsmr_still_block_explicit_start(self):
        for entity,value in [
            ('input_boolean.bender_failsafe_active','on'),
            ('binary_sensor.bender_charging_control_healthy','off'),
            ('script.bender_write_hems_zero','on'),
            ('sensor.dsmr_reading_timestamp','unavailable'),
            ('sensor.dsmr_reading_phase_voltage_l1',0),(LB,'unknown'),(LB,5.9)]:
            with self.subTest(entity=entity):
                h=ManualSimulation(desired=0,commanded=0)
                h.states.set(entity,value)
                h.run('bender_manual_set_current',current=16)
                self.assertEqual(h.command(),0)

    def test_new_pause_during_prepare_cancels_explicit_positive(self):
        h=ManualSimulation(desired=0,commanded=0);original=h.states.set
        def pause(entity,value,**kwargs):
            original(entity,value,**kwargs)
            if entity==REQUEST:
                base.NOW+=.01;original(INTENT,0.0)
        h.states.set=pause
        h.run('bender_manual_set_current',current=16)
        self.assertFalse(h.calls);self.assertEqual(h.desired(),0)

    def test_explicit_pause_and_restart_do_not_reuse_fast_permission(self):
        h=ManualSimulation(desired=0,commanded=0)
        h.run('bender_manual_set_current',current=16)
        h.feedback();h.run('bender_manual_set_current',current=0)
        h.advance(120);self.assertEqual(h.command(),0);self.assertEqual(h.desired(),0)
        h=ManualSimulation(desired=16,commanded=0)
        h.run('bender_manual_reconcile');self.assertEqual(h.command(),0)
        h.advance(30);self.assertEqual(h.command(),6)


class ExplicitConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_intent_trigger_does_not_replace_explicit_write_and_pause_wins(self):
        base.NOW=START
        e=AsyncYaml(commanded=0);e.h.states.set(INTENT,0.0,changed=START-60)
        e.trigger_intent=True
        try:
            task=e.launch('bender_manual_set_current',current=16)
            op=await e.next_write()
            self.assertEqual(op.value,16)
            e.launch('bender_manual_reconcile');await e.pump()
            self.assertEqual(op.state,'pending')
            e.launch('bender_manual_set_current',current=0)
            zero=await e.next_write();self.assertEqual(zero.value,0)
            e.release(zero);await e.pump()
            self.assertEqual(float(e.h.states(INTENT)),0)
            self.assertEqual(float(e.h.states(CMD)),0)
            self.assertEqual(op.state,'cancelled')
        finally:
            await e.close();base.NOW=START


if __name__=='__main__':unittest.main()
