"""Cross the real exported Master stop wire into the real HA YAML script model.
Offline only. The adapter models static service configuration; the HA/Node-RED
runtime and physical timing still require a controlled deployment test.
"""
import json
import subprocess
import unittest
from functools import lru_cache
import test_bender_stop_safety as base
from test_bender_manual_memory import ManualSimulation, START, INTENT, CMD, LB, READY
from test_bender_pause_concurrency import AsyncYaml

@lru_cache(None)
def stop_actions(value=0):
    result=subprocess.run(['node',str(base.ROOT/'tests/master-flow-harness.cjs'),
        json.dumps([16,value])],check=True,capture_output=True,text=True)
    actions=json.loads(result.stdout)
    if len(actions)!=1:raise AssertionError('Exactly one automatic stop required')
    return actions

def automatic_stop(h,value=0):
    h.sequence(stop_actions(value),{})

class MasterManualStopTests(unittest.TestCase):
    def setUp(self):base.NOW=START
    def tearDown(self):base.NOW=START
    def test_invalid_or_subminimum_master_reading_stops_without_forgetting_choice(self):
        for value in [0,5.9,-1,None,'','unknown','unavailable','NaN','Infinity']:
            with self.subTest(value=value):
                h=ManualSimulation();h.states.set(LB,value)
                automatic_stop(h,value)
                self.assertEqual(h.command(),0)
                self.assertEqual(h.desired(),16)
                self.assertEqual([c[1] for c in h.calls],[0])
    def test_recorded_dsmr_loss_stops_before_cached_health_updates_and_recovers(self):
        h=ManualSimulation();h.states.set('sensor.dsmr_reading_timestamp','unavailable')
        # Real loadbalancer template publishes zero before the watchdog turns red.
        value=float(h.template('bender_loadbalancer_available_current'))
        self.assertEqual(value,0);h.states.set(LB,value);automatic_stop(h,value)
        self.assertEqual(h.command(),0);self.assertEqual(h.desired(),16)
        h.states.set('input_boolean.bender_failsafe_active','on')
        h.states.set('binary_sensor.bender_charging_control_healthy','off')
        h.feedback(0);h.advance(60)
        self.assertTrue(all(c[1]==0 for c in h.calls))
        h.states.set('input_boolean.bender_failsafe_active','off')
        h.states.set('binary_sensor.bender_charging_control_healthy','on')
        h.states.set(LB,16);h.advance(30);self.assertEqual(h.command(),0)
        h.advance(5);self.assertEqual(h.command(),6)
        h.advance(35);self.assertEqual(h.command(),7);self.assertEqual(h.desired(),16)
    def test_real_headroom_shortage_requires_fresh_stop_and_stable_recovery(self):
        h=ManualSimulation();h.states.set(LB,5.9);automatic_stop(h,5.9)
        h.states.set(LB,16);h.states.set('sensor.bender_hems_limit',0)
        h.advance(40,reports=False);self.assertEqual(h.command(),0)
        h.advance(35);self.assertEqual(h.command(),6);self.assertEqual(h.desired(),16)
    def test_pause_before_during_or_after_fault_wins_over_late_automatic_stop(self):
        for when in ('before','during','after'):
            for pause in ('bender_stop_charging','bender_manual_set_current'):
                with self.subTest(when=when,pause=pause):
                    h=ManualSimulation()
                    if when=='before':h.run(pause,current=0)
                    h.states.set(LB,0);h.states.set('input_boolean.bender_failsafe_active','on')
                    h.states.set('binary_sensor.bender_charging_control_healthy','off')
                    automatic_stop(h)
                    if when=='during':h.run(pause,current=0)
                    h.feedback(0);h.states.set(LB,16)
                    h.states.set('input_boolean.bender_failsafe_active','off')
                    h.states.set('binary_sensor.bender_charging_control_healthy','on')
                    if when=='after':h.run(pause,current=0)
                    automatic_stop(h) # late old zero must not restore a saved choice
                    h.advance(120);h.run('bender_set_charging_current',current=16)
                    self.assertEqual(h.desired(),0);self.assertEqual(h.command(),0)
                    self.assertTrue(all(c[1]==0 for c in h.calls))
    def test_failed_automatic_stop_retains_choice_and_retries_with_same_deadline(self):
        h=ManualSimulation();h.states.set(LB,0);h.fail_write=True;automatic_stop(h)
        self.assertEqual(h.desired(),16);self.assertEqual(h.command(),0)
        self.assertEqual(len(h.background_errors),1)
        deadline=h.states('input_number.bender_hems_unconfirmed_since')
        base.NOW+=5;h.fail_write=False;automatic_stop(h)
        self.assertEqual(h.states('input_number.bender_hems_unconfirmed_since'),deadline)
        self.assertEqual(h.desired(),16);self.assertTrue(all(c[1]==0 for c in h.calls))

class MasterStopConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):base.NOW=START;self.e=AsyncYaml()
    async def asyncTearDown(self):await self.e.close();base.NOW=START
    async def test_automatic_zero_and_user_pause_share_one_uncancelled_write(self):
        e=self.e;e.trigger_intent=True
        await e.sequence(stop_actions(),{});zero=await e.next_write()
        self.assertEqual(float(e.h.states(INTENT)),16)
        await e.invoke('bender_stop_charging')
        for _ in range(10):await e.sequence(stop_actions(),{})
        await e.pump()
        self.assertEqual([w.value for w in e.writes],[0]);self.assertEqual(zero.state,'pending')
        self.assertEqual(float(e.h.states(INTENT)),0)
        e.release(zero);await e.pump();self.assertEqual(zero.state,'completed')
        self.assertEqual(e.errors,[])
    async def test_automatic_stop_preempts_positive_write_but_preserves_choice(self):
        e=self.e;e.h.states.set(READY,'on')
        e.launch('set_bender_hems_limit',current=16);positive=await e.next_write()
        await e.sequence(stop_actions(),{});zero=await e.next_write()
        self.assertEqual(positive.state,'cancelled');self.assertEqual(zero.value,0)
        self.assertEqual(float(e.h.states(INTENT)),16);self.assertEqual(float(e.h.states(CMD)),0)
        e.release(zero);await e.pump();self.assertEqual(zero.state,'completed')
        self.assertEqual(e.errors,[])

if __name__=='__main__':unittest.main()
