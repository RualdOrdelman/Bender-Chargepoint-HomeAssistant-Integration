import unittest,yaml
from test_bender_stop_safety import Harness,TEMPLATES,ROOT,NOW
class DashboardAvailabilityTests(unittest.TestCase):
    def available(self,h,name):return h.render(TEMPLATES[name]['availability'])=='True'
    def test_missing_invalid_and_nonfinite_power_are_not_zero(self):
        for name,entities in [('bender_charging_active',['sensor.bender_totalpower']),('bender_charging_power_total',[f'sensor.bender_power_l{i}' for i in (1,2,3)]),('bender_error_status',['sensor.bender_error_code'])]:
            for bad in ['unknown','unavailable','','nan','inf']:
                for entity in entities:
                    h=Harness()
                    for e in entities:h.states.set(e,0)
                    h.states.set(entity,bad)
                    self.assertFalse(self.available(h,name),(name,entity,bad))
            h=Harness()
            for e in entities:h.states.set(e,0,changed=NOW-86400)
            self.assertTrue(self.available(h,name),name)
            h.states.items.pop(entities[0]);self.assertFalse(self.available(h,name))
    def test_valid_power_sum_and_charging_status_still_work(self):
        h=Harness()
        for i,power in enumerate([1400,1410,1420],1):h.states.set(f'sensor.bender_power_l{i}',power)
        self.assertEqual(float(h.template('bender_charging_power_total')),4230)
        h.states.set('sensor.bender_totalpower',4230);self.assertEqual(h.template('bender_charging_active'),'True')
        h.states.set('sensor.bender_totalpower',0);self.assertEqual(h.template('bender_charging_active'),'False')
    def safe_harness(self):
        h=Harness();h.states.set('input_select.bender_charging_strategy','Uit');h.states.set('sensor.bender_vehicle_state','1');h.states.set('binary_sensor.bender_hems_command_confirmed','on');return h
    def test_safe_current_requires_disconnected_zero_confirmed_and_valid_whole_value(self):
        for value in [0,6,10,16]:
            h=self.safe_harness();h.run('set_bender_safe_current',current=value);self.assertEqual(h.calls[-1][1],value)
        for value in [-1,1,5,6.5,17,'unknown','nan','inf']:
            h=self.safe_harness();h.run('set_bender_safe_current',current=value);self.assertFalse(h.calls,value)
        for entity,value in [('sensor.bender_vehicle_state','2'),('sensor.bender_vehicle_state','unknown'),('input_select.bender_charging_strategy','Manual'),('sensor.bender_hems_limit','6'),('sensor.bender_hems_limit','unavailable'),('sensor.bender_totalpower','4000'),('sensor.bender_totalpower','unknown'),('binary_sensor.bender_hems_command_confirmed','off')]:
            h=self.safe_harness();h.states.set(entity,value);h.run('set_bender_safe_current',current=16);self.assertFalse(h.calls,(entity,value))
    def test_every_fallback_button_requires_confirmation(self):
        d=yaml.safe_load((ROOT/'HomeAssistant/dashboards/bender_chargepoint.yaml').read_text())
        def walk(x):
            if isinstance(x,dict):
                yield x
                for v in x.values():yield from walk(v)
            elif isinstance(x,list):
                for v in x:yield from walk(v)
        actions=[x for x in walk(d) if x.get('service')=='script.set_bender_safe_current']
        self.assertEqual({x['data']['current'] for x in actions},{0,6,10,16})
        for x in actions:self.assertIn('communicatieverlies',x['confirmation']['text'])
if __name__=='__main__':unittest.main()
