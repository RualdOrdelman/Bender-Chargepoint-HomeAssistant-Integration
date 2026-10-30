"""Exercise the shipped SOC template offline, including startup and recovery."""
import ast
import unittest
from test_bender_stop_safety import Harness

SOURCE = "sensor.bender_ev_battery_soc"

class EvSocTests(unittest.TestCase):
    def value(self, h):
        # Numeric HA templates accept a number or None, never literal unknown text.
        return ast.literal_eval(h.template("bender_ev_soc"))

    def test_missing_source_at_startup_is_none(self):
        self.assertIsNone(self.value(Harness()))

    def test_invalid_values_are_none_not_zero_or_text(self):
        for raw in ("unknown", "unavailable", "", "None", "abc", "65535",
                    "101", "100.9", "-1", "-0.1", "nan", "NaN", "inf", "-inf", "Infinity"):
            with self.subTest(raw=raw):
                h = Harness()
                h.states.set(SOURCE, raw)
                self.assertIsNone(self.value(h))

    def test_valid_percentages_including_empty_and_full_battery(self):
        for raw in ("0", "1", "50", "99", "100", "50.5", "100.0"):
            with self.subTest(raw=raw):
                h = Harness()
                h.states.set(SOURCE, raw)
                self.assertEqual(self.value(h), float(raw))

    def test_startup_loss_and_recovery_do_not_reuse_old_soc(self):
        h = Harness()
        for raw, expected in (("unknown", None), ("65535", None), ("72", 72),
                              ("unavailable", None), ("65535", None), ("0", 0), ("85", 85)):
            with self.subTest(raw=raw):
                h.states.set(SOURCE, raw)
                self.assertEqual(self.value(h), expected)

if __name__ == "__main__":
    unittest.main()
