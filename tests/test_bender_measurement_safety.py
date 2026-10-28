"""Reject bad meter data using the shipped HA templates, without network access."""
import unittest,datetime as dt
from test_bender_stop_safety import Harness,TEMPLATES,NOW
class MeasurementSafetyTests(unittest.TestCase):
    def harness(self):
        h=Harness();h.states.set('input_select.bender_charging_strategy','Manual')
        h.states.set('input_number.bender_requested_current','10',changed=NOW-60);h.states.set('sensor.bender_hems_limit','10');h.states.set('input_number.bender_commanded_current','10')
        return h
    def assert_rejected(self,h):
        self.assertEqual(h.template('bender_dsmr_data_healthy'),'False')
        self.assertEqual(float(h.template('bender_loadbalancer_available_current')),0)
        # Cached LB and health still say 16A/on: central writer must check sources itself.
        h.run('set_bender_hems_limit',current=16)
        self.assertEqual(h.calls[-1][1],0)
    def test_voltage_bounds_all_phases(self):
        for phase in (1,2,3):
            for value in ('0','-1','179.9','260.1','unknown','unavailable','nan','inf',''):
                with self.subTest(phase=phase,value=value):
                    h=self.harness();h.states.set(f'sensor.dsmr_reading_phase_voltage_l{phase}',value)
                    self.assert_rejected(h)
                    self.assertEqual(float(h.template(f'bender_lb_available_current_l{phase}')),0)
    def test_valid_voltages_and_zero_meter_power_remain_valid(self):
        for voltage in (180,207,230,253,260):
            h=self.harness()
            for phase in (1,2,3):
                h.states.set(f'sensor.dsmr_reading_phase_voltage_l{phase}',voltage)
                for direction in ('delivered','returned'):h.states.set(f'sensor.dsmr_reading_phase_currently_{direction}_l{phase}',0,changed=NOW-86400)
            h.states.set('sensor.p1_meter_power','0',changed=NOW-86400)
            self.assertEqual(h.template('bender_dsmr_data_healthy'),'True')
    def test_timestamp_boundaries_and_reasons(self):
        for age,valid in [(-6,False),(-5,True),(0,True),(30,True),(30.1,False),(10000,False)]:
            h=self.harness();h.states.set('sensor.dsmr_reading_timestamp',dt.datetime.fromtimestamp(NOW-age,dt.timezone.utc).isoformat())
            with self.subTest(age=age):
                self.assertEqual(h.template('bender_dsmr_data_healthy'),str(valid))
                if not valid:self.assert_rejected(h)
                reason=h.render(TEMPLATES['bender_dsmr_data_healthy']['attributes']['invalid_entities'])
                if age< -5:self.assertIn('toekomst',reason)
    def test_missing_and_nonfinite_fields_are_rejected(self):
        for entity in ['sensor.p1_meter_power','sensor.dsmr_reading_phase_currently_delivered_l1','sensor.dsmr_reading_phase_currently_returned_l3','sensor.dsmr_reading_timestamp']:
            for value in ('unknown','unavailable','NaN','Infinity'):
                with self.subTest(entity=entity,value=value):
                    h=self.harness();h.states.set(entity,value);self.assert_rejected(h)
            h=self.harness();h.states.items.pop(entity);self.assert_rejected(h)
    def test_negative_phase_import_or_export_rejected_but_signed_p1_allowed(self):
        for direction in ('delivered','returned'):
            h=self.harness();h.states.set(f'sensor.dsmr_reading_phase_currently_{direction}_l2','-0.1');self.assert_rejected(h)
        for signed in ('-5000','0','5000'):
            h=self.harness();h.states.set('sensor.p1_meter_power',signed);self.assertEqual(h.template('bender_dsmr_data_healthy'),'True')
    def test_manual_invalid_lb_never_falls_back_to_16A(self):
        for value in ('unknown','unavailable','nan','inf','','-1','5.9'):
            for entry in ('set_bender_hems_limit','bender_set_charging_current'):
                with self.subTest(value=value,entry=entry):
                    h=self.harness();h.states.set('sensor.bender_loadbalancer_available_current',value)
                    h.run(entry,current=16);self.assertEqual(h.calls[-1][1],0)
    def test_manual_valid_limit_caps_requested_current(self):
        for limit,expected in [('6',6),('10.9',10),('16',16)]:
            h=self.harness();h.states.set('sensor.bender_loadbalancer_available_current',limit)
            h.run('set_bender_hems_limit',current=16)
            if expected==10:self.assertFalse(h.calls) # already confirmed 10A
            else:self.assertEqual(h.calls[-1][1],expected)
    def test_disabled_lb_preserves_explicit_control_but_not_active_failsafe(self):
        h=self.harness();h.states.set('input_boolean.bender_loadbalancer_enabled','off');h.states.set('sensor.bender_loadbalancer_available_current','unknown')
        h.run('bender_set_charging_current',current=16);self.assertEqual(h.calls[-1][1],16)
        h.states.set('input_boolean.bender_failsafe_active','on');h.run('bender_set_charging_current',current=16);self.assertEqual(h.calls[-1][1],0)
if __name__=='__main__':unittest.main()
