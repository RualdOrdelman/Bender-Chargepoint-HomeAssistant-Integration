"""Exercise real YAML paths with controlled asynchronous Modbus completions.
Models HA restart/single and detached script.turn_on, without contacting HA.
This is a scheduling model, not a substitute for validation in HA itself.
"""
import asyncio
import unittest
from dataclasses import dataclass
from test_bender_stop_safety import PACKAGE, Stop
from test_bender_manual_memory import ManualSimulation, INTENT, CMD, REQUEST, STRATEGY

ZERO='bender_write_hems_zero'
WRITER='set_bender_hems_limit'

@dataclass
class Write:
    value: int
    future: asyncio.Future
    state: str='pending'

class AsyncYaml:
    def __init__(self, package=PACKAGE, commanded=12):
        self.h=ManualSimulation(commanded=commanded)
        self.package=package
        self.active={};self.tasks=set();self.errors=[];self.writes=[]
        self.new_write=asyncio.Queue()
        self.trigger_intent=False
        self.wait_for_automatic_stop=False
        self.after_detach=None
        self.dropped=[]
    def launch(self,name,**variables):
        active=self.active.setdefault(name,set())
        active.difference_update(t for t in list(active) if t.done())
        mode=self.package['script'][name].get('mode','single')
        if active and mode=='single':self.dropped.append(name);return None
        cancelled=list(active) if mode=='restart' else []
        for t in cancelled:t.cancel()
        async def execute():
            try:
                if cancelled:await asyncio.gather(*cancelled,return_exceptions=True)
                await self.sequence(self.package['script'][name]['sequence'],variables)
            except Stop:pass
            finally:
                active.discard(asyncio.current_task())
                self.h.states.set('script.'+name,'on' if active else 'off')
        task=asyncio.create_task(execute(),name=name)
        active.add(task);self.tasks.add(task);self.h.states.set('script.'+name,'on')
        def done(t):
            if not t.cancelled() and t.exception():self.errors.append(t.exception())
        task.add_done_callback(done)
        return task
    async def invoke(self,name,**variables):
        t=self.launch(name,**variables)
        if t:await t
    async def sequence(self,actions,v):
        for a in actions:
            if 'variables' in a:
                v.update(self.h.variables(a['variables'],v))
            elif 'if' in a:
                await self.sequence(a.get('then',[]) if self.h.conditions(a['if'],v) else a.get('else',[]),v)
            elif 'choose' in a:
                for option in a['choose']:
                    if self.h.conditions(option['conditions'],v):
                        await self.sequence(option['sequence'],v);break
                else:await self.sequence(a.get('default',[]),v)
            elif 'stop' in a:raise Stop()
            elif 'service' in a or 'action' in a:
                service=a.get('service',a.get('action'))
                data={k:self.h.render(x,v) for k,x in a.get('data',{}).items()}
                target=a.get('target',{}).get('entity_id')
                if service=='input_number.set_value':
                    old=self.h.states(target)
                    self.h.states.set(target,str(float(data['value'])))
                    if self.trigger_intent and target==INTENT and old!=self.h.states(target):
                        self.launch('bender_manual_reconcile')
                        if self.wait_for_automatic_stop:
                            # Recorded ordering: automatic path reaches Modbus before
                            # the explicit pause script calls the dispatcher again.
                            for _ in range(100):
                                if any(w.value==0 and w.state=='pending' for w in self.writes):break
                                await asyncio.sleep(0)
                            else:raise AssertionError('Automatic stop did not reach Modbus')
                elif service=='input_text.set_value':self.h.states.set(target,data['value'])
                elif service=='modbus.write_register':
                    if int(data['address'])!=1000:raise AssertionError('Unexpected Modbus register')
                    op=Write(int(data['value']),asyncio.get_running_loop().create_future())
                    self.writes.append(op);self.new_write.put_nowait(op)
                    try:await op.future;op.state='completed'
                    except asyncio.CancelledError:op.state='cancelled';raise
                    except Exception:op.state='failed';raise
                elif service=='script.turn_on':
                    self.launch(target.split('.',1)[1],**data.get('variables',{}))
                    if target=='script.'+ZERO and self.after_detach is not None:await self.after_detach.wait()
                elif service.startswith('script.'):
                    await self.invoke(service.split('.',1)[1],**data)
                elif service!='logbook.log':raise AssertionError(service)
            else:raise AssertionError(a)
            await asyncio.sleep(0)
    async def next_write(self):return await asyncio.wait_for(self.new_write.get(),1)
    async def pump(self):
        for _ in range(25):await asyncio.sleep(0)
    def release(self,op,error=None):
        if error:op.future.set_exception(error)
        else:op.future.set_result(None)
    async def close(self):
        for t in self.tasks:
            if not t.done():t.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)

class PauseConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):self.engines=[]
    async def asyncTearDown(self):
        for e in self.engines:await e.close()
    def engine(self,**kwargs):
        e=AsyncYaml(**kwargs);self.engines.append(e);return e
    async def test_recorded_auto_then_explicit_pause_has_one_uninterrupted_zero(self):
        e=self.engine();e.trigger_intent=True;e.wait_for_automatic_stop=True
        pause=e.launch('bender_stop_charging');zero=await e.next_write()
        await asyncio.wait_for(pause,1);await e.pump()
        self.assertEqual([w.value for w in e.writes],[0])
        self.assertEqual(zero.state,'pending');self.assertIn(ZERO,e.dropped)
        self.assertEqual(float(e.h.states(INTENT)),0);self.assertEqual(float(e.h.states(CMD)),0)
        e.release(zero);await e.pump();self.assertEqual(zero.state,'completed')
        self.assertEqual(e.errors,[])
    async def test_old_dispatch_behavior_reproduces_cancelled_zero_in_the_same_schedule(self):
        # Restore only the pre-fix dispatch action to isolate the recorded cause.
        # All other guards remain identical for this comparison.
        import copy
        old=copy.deepcopy(PACKAGE)
        seq=old['script'][WRITER]['sequence']
        for i,a in enumerate(seq):
            if a.get('then',[{}])[0].get('service')=='script.turn_on':
                seq[i]={'service':'modbus.write_register','data':{'hub':'modbus_hub','slave':1,'address':1000,'value':'{{ applied_current }}'}}
                break
        else:self.fail('Zero dispatch action not located')
        e=self.engine(package=old);e.trigger_intent=True;e.wait_for_automatic_stop=True
        pause=e.launch('bender_stop_charging');first=await e.next_write();second=await e.next_write()
        self.assertEqual(first.state,'cancelled');self.assertEqual([w.value for w in e.writes],[0,0])
        e.release(second);await asyncio.wait_for(pause,1)
    async def test_burst_of_duplicate_stops_does_not_cancel_or_queue_zero(self):
        e=self.engine();await e.invoke(WRITER,current=0);zero=await e.next_write()
        tasks=[e.launch(WRITER,current=0) for _ in range(30)]
        await asyncio.gather(*(t for t in tasks if t),return_exceptions=True);await e.pump()
        self.assertEqual(len(e.writes),1);self.assertEqual(zero.state,'pending')
        e.release(zero);await e.pump();self.assertEqual(zero.state,'completed')
    async def test_parent_cancellation_does_not_cancel_detached_zero(self):
        e=self.engine();e.after_detach=asyncio.Event()
        dispatcher=e.launch(WRITER,current=0);zero=await e.next_write()
        dispatcher.cancel();await asyncio.gather(dispatcher,return_exceptions=True)
        self.assertEqual(zero.state,'pending')
        e.release(zero);await e.pump();self.assertEqual(zero.state,'completed')
    async def test_stop_preempts_positive_write_without_positive_credit(self):
        e=self.engine();e.h.states.set('binary_sensor.bender_manual_increase_ready','on')
        positive=e.launch(WRITER,current=16);op=await e.next_write();self.assertEqual(op.value,13)
        await e.invoke('bender_stop_charging');zero=await e.next_write()
        self.assertEqual(op.state,'cancelled');self.assertEqual(zero.value,0)
        self.assertEqual(float(e.h.states(CMD)),0);self.assertEqual(float(e.h.states(INTENT)),0)
        e.release(zero);await e.pump();self.assertEqual(zero.state,'completed')
        self.assertFalse(any(w.value>0 and w.state=='completed' for w in e.writes))
    async def test_positive_request_cannot_overtake_zero_even_with_matching_feedback(self):
        e=self.engine();await e.invoke(WRITER,current=0);zero=await e.next_write()
        e.h.states.set(STRATEGY,'ChargePV');e.h.states.set('sensor.bender_hems_limit',0)
        await e.invoke(WRITER,current=16);await e.pump()
        self.assertEqual(len(e.writes),1);self.assertEqual(zero.state,'pending')
        e.release(zero);await e.pump()
        later=e.launch(WRITER,current=6);op=await e.next_write();self.assertEqual(op.value,6)
        e.release(op);await asyncio.wait_for(later,1)
    async def test_finished_zero_still_requires_real_feedback_before_positive_write(self):
        e=self.engine();await e.invoke(WRITER,current=0);zero=await e.next_write();e.release(zero);await e.pump()
        e.h.states.set(STRATEGY,'ChargePV')
        await e.invoke(WRITER,current=16);retry=await e.next_write()
        self.assertEqual(retry.value,0)
        self.assertEqual(e.h.template('bender_hems_command_confirmed'),'False')
        e.release(retry);await e.pump()
    async def test_failed_detached_zero_keeps_deadline_and_allows_retry(self):
        e=self.engine();await e.invoke(WRITER,current=0);zero=await e.next_write()
        deadline=e.h.states('input_number.bender_hems_unconfirmed_since')
        e.release(zero,RuntimeError('simulated write failure'));await e.pump()
        self.assertEqual(zero.state,'failed');self.assertEqual(e.h.states('script.'+ZERO),'off')
        self.assertEqual(e.h.template('bender_hems_command_confirmed'),'False')
        await e.invoke(WRITER,current=0);retry=await e.next_write()
        self.assertEqual(retry.value,0)
        self.assertEqual(e.h.states('input_number.bender_hems_unconfirmed_since'),deadline)
        self.assertEqual(float(e.h.states(CMD)),0)
        e.release(retry);await e.pump();self.assertEqual(retry.state,'completed')
    async def test_explicit_zero_choice_uses_same_pause_path_with_automatic_trigger(self):
        e=self.engine();e.trigger_intent=True;e.wait_for_automatic_stop=True
        await e.invoke('bender_manual_set_current',current=0);zero=await e.next_write()
        self.assertEqual([w.value for w in e.writes],[0]);self.assertEqual(zero.state,'pending')
        e.release(zero);await e.pump();self.assertEqual(float(e.h.states(INTENT)),0)
    async def test_zero_worker_cannot_be_used_to_send_a_positive_value(self):
        e=self.engine();task=e.launch(ZERO,current=16);zero=await e.next_write()
        self.assertEqual(zero.value,0);e.release(zero);await asyncio.wait_for(task,1)

    async def test_pause_caller_finishes_when_dispatcher_is_replaced(self):
        e=self.engine();e.after_detach=asyncio.Event()
        pause=e.launch('bender_stop_charging');zero=await e.next_write()
        await asyncio.wait_for(asyncio.shield(pause),1)
        replacement=e.launch(WRITER,current=0);await e.pump()
        self.assertFalse(pause.cancelled());self.assertEqual(zero.state,'pending')
        self.assertEqual(float(e.h.states(INTENT)),0)
        e.after_detach.set();await asyncio.wait_for(replacement,1)
        e.release(zero);await e.pump();self.assertEqual(zero.state,'completed')
    async def test_old_synchronous_pause_propagates_child_cancellation_to_caller(self):
        import copy
        old=copy.deepcopy(PACKAGE)
        old['script']['bender_stop_charging']['sequence'][1]={
            'service':'script.'+WRITER,'data':{'current':0}}
        e=self.engine(package=old);e.after_detach=asyncio.Event()
        pause=e.launch('bender_stop_charging');zero=await e.next_write()
        replacement=e.launch(WRITER,current=0);await e.pump()
        self.assertTrue(pause.cancelled());self.assertEqual(zero.state,'pending')
        e.after_detach.set();await asyncio.wait_for(replacement,1)
        e.release(zero);await e.pump()
    async def test_zero_choice_caller_also_survives_replaced_dispatcher(self):
        e=self.engine();e.after_detach=asyncio.Event()
        choose=e.launch('bender_manual_set_current',current=0);zero=await e.next_write()
        await asyncio.wait_for(asyncio.shield(choose),1)
        replacement=e.launch(WRITER,current=0);await e.pump()
        self.assertFalse(choose.cancelled());self.assertEqual(float(e.h.states(INTENT)),0)
        e.after_detach.set();await asyncio.wait_for(replacement,1)
        e.release(zero);await e.pump();self.assertEqual(zero.state,'completed')

if __name__=='__main__':unittest.main()
