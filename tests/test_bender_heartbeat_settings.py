"""Offline checks of shipped templates and the HA restoration configuration.

Uses real Europe/Amsterdam DST transitions. This does not restart Home Assistant.
"""
import datetime as dt
import json
import unittest
from zoneinfo import ZoneInfo

from test_bender_stop_safety import Harness, PACKAGE, ROOT

ZONE = ZoneInfo('Europe/Amsterdam')
HEARTBEAT = 'input_datetime.bender_nodered_heartbeat'
SETTINGS = {
    'bender_strategy_max_current': (6, 16),
    'bender_loadbalancer_margin': (0, 5000),
    'bender_house_max_power': (5000, 25000),
}


class HeartbeatTimeTests(unittest.TestCase):
    def age(self, stamp, now, state=None):
        h = Harness()
        if state is None:
            state = dt.datetime.fromtimestamp(stamp, ZONE).strftime('%Y-%m-%d %H:%M:%S')
        h.states.set(HEARTBEAT, state)
        h.env.globals.update(
            state_attr=lambda entity, attribute: stamp if (entity, attribute) == (HEARTBEAT, 'timestamp') else None,
            now=lambda: dt.datetime.fromtimestamp(now, ZONE),
        )
        return float(h.template('bender_nodered_heartbeat_age'))

    def healthy(self, age):
        h = Harness()
        h.states.set('sensor.bender_nodered_heartbeat_age', age)
        return h.template('bender_nodered_heartbeat_healthy') == 'True'

    def test_both_occurrences_of_0230_have_a_fresh_heartbeat(self):
        for fold in (0, 1):
            with self.subTest(fold=fold):
                stamp = dt.datetime(2026, 10, 25, 2, 30, tzinfo=ZONE, fold=fold).timestamp()
                self.assertEqual(self.age(stamp, stamp + 10), 10)
                self.assertTrue(self.healthy(self.age(stamp, stamp + 10)))

    def test_same_clock_text_from_first_hour_is_stale_in_second_hour(self):
        first = dt.datetime(2026, 10, 25, 2, 30, tzinfo=ZONE, fold=0).timestamp()
        second = dt.datetime(2026, 10, 25, 2, 30, tzinfo=ZONE, fold=1).timestamp()
        self.assertEqual(self.age(first, second + 10), 3610)
        self.assertFalse(self.healthy(self.age(first, second + 10)))

    def test_elapsed_time_across_both_clock_changes_and_midnight(self):
        for local in [dt.datetime(2026, 10, 25, 2, 59, 55, tzinfo=ZONE, fold=0),
                      dt.datetime(2026, 3, 29, 1, 59, 55, tzinfo=ZONE),
                      dt.datetime(2026, 10, 30, 23, 59, 55, tzinfo=ZONE)]:
            with self.subTest(time=local):
                stamp = local.timestamp()
                self.assertEqual(self.age(stamp, stamp + 10), 10)
                self.assertEqual(self.age(stamp, stamp + 31), 31)
                self.assertFalse(self.healthy(self.age(stamp, stamp + 31)))

    def test_threshold_still_allows_30_seconds_but_not_31(self):
        stamp = dt.datetime(2026, 10, 30, 12, tzinfo=ZONE).timestamp()
        self.assertTrue(self.healthy(self.age(stamp, stamp + 30)))
        self.assertFalse(self.healthy(self.age(stamp, stamp + 31)))

    def test_missing_invalid_and_nonfinite_timestamps_fail_closed(self):
        now = dt.datetime(2026, 10, 30, 12, tzinfo=ZONE).timestamp()
        for raw in [None, '', 'unknown', 'unavailable', 'nan', 'inf', '-inf', 0, -1]:
            with self.subTest(raw=raw):
                self.assertEqual(self.age(raw, now, '2026-10-30 12:00:00'), 999999)
                self.assertFalse(self.healthy(self.age(raw, now, '2026-10-30 12:00:00')))

    def test_unavailable_helper_cannot_reuse_a_fresh_attribute(self):
        now = dt.datetime(2026, 10, 30, 12, tzinfo=ZONE).timestamp()
        for state in ('unknown', 'unavailable', 'none', ''):
            self.assertEqual(self.age(now, now, state), 999999)

    def test_future_clock_tolerance_is_bounded(self):
        now = dt.datetime(2026, 10, 30, 12, tzinfo=ZONE).timestamp()
        self.assertEqual(self.age(now + 5, now), 0)
        for delta in (6, 3600, 86400):
            self.assertEqual(self.age(now + delta, now), 999999)

    def test_startup_requires_new_heartbeat_even_at_midnight_or_dst_fold(self):
        config = PACKAGE['input_datetime']['bender_nodered_heartbeat']
        stamp = dt.datetime.fromisoformat(config['initial']).replace(tzinfo=ZONE).timestamp()
        for now in [dt.datetime(2026, 10, 30, 0, 0, 5, tzinfo=ZONE),
                    dt.datetime(2026, 10, 25, 2, 30, tzinfo=ZONE, fold=1)]:
            self.assertFalse(self.healthy(self.age(stamp, now.timestamp())))
            self.assertTrue(self.healthy(self.age(now.timestamp(), now.timestamp() + 10)))

    def test_nodered_already_sends_epoch_without_local_date_conversion(self):
        nodes = {n['id']: n for n in json.loads((ROOT / 'NodeRed/bender_strategy_master.json').read_text())}
        service = nodes['bender_master_heartbeat_service']
        self.assertEqual(service['action'], 'input_datetime.set_datetime')
        self.assertEqual(json.loads(service['data']), {'timestamp': '{{heartbeat_timestamp}}'})
        self.assertIn('Date.now() / 1000', nodes['bender_master_heartbeat_timestamp']['func'])


class PersistentSettingsTests(unittest.TestCase):
    def test_user_settings_enable_native_ha_restore_without_resetting_ranges(self):
        for name, bounds in SETTINGS.items():
            with self.subTest(name=name):
                config = PACKAGE['input_number'][name]
                self.assertNotIn('initial', config)
                self.assertEqual((config['min'], config['max']), bounds)

    def test_user_pause_still_restores_and_transient_command_state_does_not(self):
        self.assertNotIn('initial', PACKAGE['input_number']['bender_manual_desired_current'])
        self.assertEqual(PACKAGE['input_number']['bender_commanded_current']['initial'], 0)
        self.assertEqual(PACKAGE['input_number']['bender_requested_current']['initial'], 0)


if __name__ == '__main__':
    unittest.main()
