"""Regression for the real Manual startup warning, with absent HA entities.

Unlike the original harness, a missing states.domain.entity returns None here.
Metadata access on None is a test failure, even if as_timestamp would mask it.
No HA instance, server connection or Modbus is used.
"""
import unittest
import jinja2
import test_bender_stop_safety as base
from test_bender_manual_memory import ManualSimulation, START, READY, INTENT, CMD, STRATEGY


class ActualMissingDomain(base.Domain):
    def __getattr__(self, name):
        return self.states.items.get(self.domain + '.' + name)


class ActualMissingStates(base.States):
    def __getattr__(self, domain):
        return ActualMissingDomain(self, domain)


class NoMissingMetadata(jinja2.Environment):
    def getattr(self, obj, attribute):
        if obj is None and attribute in ('last_changed', 'last_reported'):
            raise AssertionError(f"Startup template warning: None has no attribute {attribute}")
        return super().getattr(obj, attribute)


def check_missing_entities(h):
    h.states.__class__ = ActualMissingStates
    h.env.__class__ = NoMissingMetadata
    return h


class ManualStartupTests(unittest.TestCase):
    def setUp(self):
        base.NOW = START

    def tearDown(self):
        base.NOW = START

    def missing_ready(self, commanded=0, desired=16):
        h = check_missing_entities(ManualSimulation(commanded=commanded, desired=desired))
        h.states.items.pop(READY, None)
        h.since = None
        return h

    def test_recorded_uit_zero_before_manual_ready_exists_has_no_warning(self):
        h = check_missing_entities(base.Harness())
        h.states.set(STRATEGY, 'Uit')
        self.assertIsNone(h.states.binary_sensor.bender_manual_increase_ready)
        h.run('set_bender_hems_limit', current=0)
        self.assertEqual(float(h.states(CMD)), 0)
        self.assertFalse(any(c[1] > 0 for c in h.calls))

    def test_missing_ready_prevents_start_and_increase_without_erasing_choice(self):
        for commanded in (0, 6, 12):
            with self.subTest(commanded=commanded):
                h = self.missing_ready(commanded)
                h.run('bender_manual_reconcile')
                self.assertEqual(h.command(), commanded)
                self.assertEqual(h.desired(), 16)
                self.assertFalse(h.calls)

    def test_unknown_unavailable_and_off_ready_do_not_allow_increase(self):
        for state in ('unknown', 'unavailable', 'off'):
            with self.subTest(state=state):
                h = self.missing_ready(commanded=12)
                h.states.set(READY, state, changed=START - 60)
                h.run('bender_manual_reconcile')
                self.assertEqual(h.command(), 12)
                self.assertFalse(h.calls)

    def test_lowering_still_works_without_ready_sensor(self):
        h = self.missing_ready(commanded=12)
        h.run('bender_manual_set_current', current=10)
        self.assertEqual(h.command(), 10)
        self.assertEqual(h.desired(), 10)
        self.assertEqual([c[1] for c in h.calls], [10])

    def test_fault_stop_without_ready_preserves_user_intent(self):
        h = self.missing_ready(commanded=12)
        h.states.set('input_boolean.bender_failsafe_active', 'on')
        h.states.set('binary_sensor.bender_charging_control_healthy', 'off')
        h.run('bender_manual_reconcile')
        self.assertEqual(h.command(), 0)
        self.assertEqual(h.desired(), 16)
        self.assertEqual([c[1] for c in h.calls], [0])

    def test_ready_return_still_waits_before_starting_at_six(self):
        h = self.missing_ready(desired=10)
        h.run('bender_manual_reconcile')
        h.advance(30)
        self.assertEqual(h.command(), 0)
        self.assertFalse(h.calls)
        h.advance(5)
        self.assertEqual(h.command(), 6)
        self.assertEqual(h.desired(), 10)
        self.assertEqual([c[1] for c in h.calls], [6])

    def test_pause_while_ready_missing_remains_after_sensor_returns(self):
        h = self.missing_ready(commanded=12)
        h.run('bender_stop_charging')
        self.assertEqual(h.command(), 0)
        self.assertEqual(h.desired(), 0)
        h.advance(120)
        self.assertEqual(h.command(), 0)
        self.assertEqual(h.desired(), 0)
        self.assertTrue(all(c[1] == 0 for c in h.calls))

    def test_direct_does_not_depend_on_manual_ready_sensor(self):
        h = check_missing_entities(base.Harness())
        h.states.set('binary_sensor.bender_charger_stopped_fresh', 'on', changed=START-40)
        h.states.set('binary_sensor.bender_direct_resume_ready', 'on', changed=START-10)
        h.run('set_bender_hems_limit', current=6)
        self.assertEqual([c[1] for c in h.calls], [6])


if __name__ == '__main__':
    unittest.main()
