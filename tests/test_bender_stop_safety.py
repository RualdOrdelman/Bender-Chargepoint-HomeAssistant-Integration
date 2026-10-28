"""Offline tests of the actual HA YAML templates and service ordering.
No HA API, Modbus, network or production writes. Requires PyYAML and Jinja2.
"""
import unittest, math, datetime as dt, ast
from pathlib import Path
from types import SimpleNamespace
import yaml,jinja2
ROOT=Path(__file__).resolve().parents[1]
PACKAGE=yaml.safe_load((ROOT/'HomeAssistant/packages/bender_chargepoint_integration.yaml').read_text())
TEMPLATES={x['unique_id']:x for group in PACKAGE['template'] for kind in ['sensor','binary_sensor'] for x in group.get(kind,[]) if 'unique_id' in x}
NOW=1803816000.0
def number(value):
    try:return math.isfinite(float(value))
    except (ValueError,TypeError):return False
def numeric(value,default=0):
    try:return float(value)
    except (ValueError,TypeError):return default
def integer(value,default=0):
    try:return int(float(value))
    except (ValueError,TypeError,OverflowError):return default
def timestamp(value,default=0):
    if isinstance(value,dt.datetime):return value.timestamp()
    if isinstance(value,(int,float)):return value
    try:return dt.datetime.fromisoformat(value).timestamp()
    except (TypeError,ValueError):return default
class Domain:
    def __init__(self,states,domain):self.states,self.domain=states,domain
    def __getattr__(self,name):return self.states.items.get(self.domain+'.'+name,SimpleNamespace(state='unknown',last_changed=None,last_reported=None))
class States:
    def __init__(self):self.items={}
    def __call__(self,name):return self.items.get(name,SimpleNamespace(state='unknown')).state
    def __getattr__(self,domain):return Domain(self,domain)
    def set(self,name,value,changed=None,reported=None):
        old=self.items.get(name);value=str(value)
        when=NOW if changed is None else changed
        self.items[name]=SimpleNamespace(entity_id=name,state=value,
            last_changed=dt.datetime.fromtimestamp(old.last_changed.timestamp() if old and old.state==value and changed is None else when,dt.timezone.utc),
            last_reported=dt.datetime.fromtimestamp(NOW if reported is None else reported,dt.timezone.utc))
class Stop(Exception):pass
class Harness:
    def __init__(self):
        self.states=States();self.calls=[];self.fail_write=False
        self.env=jinja2.Environment(undefined=jinja2.StrictUndefined)
        self.env.filters.update(float=numeric,int=integer)
        self.env.globals.update(states=self.states,is_state=lambda e,s:self.states(e)==s,
            is_number=number,as_timestamp=timestamp,now=lambda:dt.datetime.fromtimestamp(NOW,dt.timezone.utc),
            expand=lambda ids:[self.states.items[e] for e in ids if e in self.states.items],state_attr=lambda *a:None)
        for e,v in {'input_select.bender_charging_strategy':'Direct','input_boolean.bender_failsafe_active':'off',
            'input_boolean.bender_loadbalancer_enabled':'on','binary_sensor.bender_charging_control_healthy':'on',
            'binary_sensor.bender_direct_resume_ready':'off','binary_sensor.bender_charger_stopped_fresh':'off',
            'input_number.bender_commanded_current':'0.0','input_number.bender_strategy_max_current':'6',
            'sensor.bender_loadbalancer_available_current':'16','sensor.bender_hems_limit':'0',
            'input_number.bender_house_max_power':'5000','input_number.bender_loadbalancer_margin':'5000',
            'input_select.bender_failsafe_mode':'Actief','binary_sensor.bender_dsmr_data_healthy':'on',
            'sensor.bender_totalpower':'0'}.items():self.states.set(e,v,changed=NOW-60)
        for phase in [1,2,3]:
            self.states.set(f'sensor.bender_current_l{phase}','0',changed=NOW-60)
            self.states.set(f'sensor.dsmr_reading_phase_currently_delivered_l{phase}','0')
            self.states.set(f'sensor.dsmr_reading_phase_currently_returned_l{phase}',{1:'2.060',2:'1.871',3:'.106'}[phase])
            self.states.set(f'sensor.dsmr_reading_phase_voltage_l{phase}','239.8')
    def render(self,value,variables=None):
        if not isinstance(value,str):return value
        return self.env.from_string(value).render(**(variables or {})).strip()
    def truth(self,value,variables):return self.render(value,variables).lower() in ('true','on','1')
    def template(self,name):return self.render(TEMPLATES[name]['state'])
    def conditions(self,items,variables):
        return all(self.truth(x['value_template'],variables) if x['condition']=='template' else self.states(x['entity_id'])==x['state'] for x in items)
    def run(self,name,**variables):
        try:self.sequence(PACKAGE['script'][name]['sequence'],dict(variables))
        except Stop:pass
    def sequence(self,sequence,variables):
        for action in sequence:
            if 'variables' in action:
                for k,v in action['variables'].items():
                    value=self.render(v,variables)
                    try: value=ast.literal_eval(value)
                    except (ValueError,SyntaxError,TypeError): pass
                    variables[k]=value
            elif 'if' in action:
                self.sequence(action.get('then',[]) if self.conditions(action['if'],variables) else action.get('else',[]),variables)
            elif 'stop' in action:raise Stop()
            elif 'service' in action:
                service=action['service'];data={k:self.render(v,variables) for k,v in action.get('data',{}).items()}
                target=action.get('target',{}).get('entity_id')
                if service=='input_number.set_value':self.states.set(target,str(float(data['value'])))
                elif service=='input_text.set_value':self.states.set(target,data['value'])
                elif service=='modbus.write_register':
                    self.calls.append((service,int(data['value']),self.states('input_number.bender_commanded_current')))
                    if self.fail_write:raise RuntimeError('simulated Modbus failure')
                elif service.startswith('script.'):self.run(service.split('.',1)[1],**data)
                elif service!='logbook.log':raise AssertionError(service)
            else:raise AssertionError(action)
class SafetyTests(unittest.TestCase):
    def test_all_templates_parse(self):
        env=Harness().env
        def walk(x):
            if isinstance(x,dict):
                for v in x.values():walk(v)
            elif isinstance(x,list):
                for v in x:walk(v)
            elif isinstance(x,str) and ('{{' in x or '{%' in x):env.parse(x)
        walk(PACKAGE)
    def test_recorded_6310mA_after_stop_cannot_recreate_67A_headroom(self):
        h=Harness()
        for p in [1,2,3]:h.states.set(f'sensor.bender_current_l{p}','6301')
        self.assertEqual(float(h.template('bender_loadbalancer_available_current')),0.4)
        h.states.set('input_number.bender_commanded_current','16')
        self.assertEqual(float(h.template('bender_loadbalancer_available_current')),6.7)
    def test_direct_bounce_is_blocked_even_with_stale_67A_sensor(self):
        h=Harness();h.states.set('sensor.bender_loadbalancer_available_current','6.7');h.states.set('sensor.bender_hems_limit','6')
        h.run('set_bender_hems_limit',current=6)
        self.assertEqual(h.calls[-1][1],0)
    def test_zero_credit_is_recorded_before_write_and_stop_is_not_dropped(self):
        h=Harness();h.states.set('input_number.bender_commanded_current','6');h.states.set('sensor.bender_hems_limit','6')
        h.run('set_bender_hems_limit',current=0)
        self.assertEqual(h.calls[-1],('modbus.write_register',0,'0.0'))
        self.assertEqual(PACKAGE['script']['set_bender_hems_limit']['mode'],'restart')
    def ready(self,h):
        h.states.set('binary_sensor.bender_charger_stopped_fresh','on',changed=NOW-40)
        h.states.set('binary_sensor.bender_direct_resume_ready','on',changed=NOW-10)
    def test_verified_stable_restart_and_failed_write_keep_credit_safe(self):
        h=Harness();self.ready(h);h.run('set_bender_hems_limit',current=6)
        self.assertEqual(h.calls[-1],('modbus.write_register',6,'0.0'))
        self.assertEqual(h.states('input_number.bender_commanded_current'),'6.0')
        h=Harness();self.ready(h);h.fail_write=True
        with self.assertRaises(RuntimeError):h.run('set_bender_hems_limit',current=6)
        self.assertEqual(h.states('input_number.bender_commanded_current'),'0.0')
    def test_old_ready_state_cannot_authorize_new_stop_cycle(self):
        h=Harness();self.ready(h);h.states.set('input_number.bender_commanded_current','0.0',changed=NOW-1)
        h.run('set_bender_hems_limit',current=6);self.assertFalse(h.calls)
    def test_unchanged_zero_reports_can_be_fresh_but_old_future_or_invalid_cannot(self):
        h=Harness();self.assertEqual(h.template('bender_charger_stopped_fresh'),'True')
        for value,reported in [('0',NOW-26),('0',NOW+1),('unknown',NOW),('nan',NOW),('201',NOW)]:
            h.states.set('sensor.bender_current_l3',value,reported=reported)
            self.assertEqual(h.template('bender_charger_stopped_fresh'),'False',(value,reported))
    def test_measurements_from_before_stop_are_not_confirmation(self):
        h=Harness();h.states.set('sensor.bender_hems_limit','0',reported=NOW-61)
        self.assertEqual(h.template('bender_charger_stopped_fresh'),'False')
    def test_resume_requires_direct_health_capacity_and_continuous_30s(self):
        h=Harness();self.ready(h)
        self.assertEqual(TEMPLATES['bender_direct_resume_ready']['delay_on'],'00:00:30')
        self.assertEqual(h.template('bender_direct_resume_ready'),'True')
        for entity,value in [('sensor.bender_loadbalancer_available_current','5.9'),('binary_sensor.bender_charging_control_healthy','off'),('input_select.bender_charging_strategy','Uit')]:
            h=Harness();self.ready(h);h.states.set(entity,value)
            self.assertEqual(h.template('bender_direct_resume_ready'),'False')
    def test_off_failsafe_and_current_shortage_always_win(self):
        for entity,value in [('input_select.bender_charging_strategy','Uit'),('input_boolean.bender_failsafe_active','on'),('sensor.bender_loadbalancer_available_current','5.9'),('binary_sensor.bender_charging_control_healthy','off'),('sensor.bender_loadbalancer_available_current','nan')]:
            h=Harness();self.ready(h);h.states.set('input_number.bender_commanded_current','6');h.states.set('sensor.bender_hems_limit','6');h.states.set(entity,value)
            h.run('set_bender_hems_limit',current=16)
            self.assertEqual(h.calls[-1][1],0,(entity,value))
    def test_confirmed_commands_are_not_rewritten(self):
        h=Harness();h.run('set_bender_hems_limit',current=0);self.assertFalse(h.calls)
    def test_direct_script_waits_then_starts_and_manual_writer_keeps_explicit_control(self):
        h=Harness();h.run('bender_start_charging');self.assertFalse(h.calls)
        self.ready(h);h.run('bender_start_charging');self.assertEqual(h.calls[-1][1],6)
        h=Harness();h.states.set('input_select.bender_charging_strategy','Manual')
        h.run('set_bender_hems_limit',current=10);self.assertEqual(h.calls[-1][1],10)
        h.run('set_bender_hems_limit',current=0);self.assertEqual(h.calls[-1][1],0)
if __name__=='__main__':unittest.main()
