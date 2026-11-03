"""Run with project Python; no live model or mouse activity."""
import base64
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import task_service as ts


def image():
    data = BytesIO(); Image.new('RGB',(240,120),'white').save(data,'PNG')
    return base64.b64encode(data.getvalue()).decode()


class TaskTest(unittest.TestCase):
    def setUp(self):
        self.calls = 0
        def describe(im, context):
            self.calls += 1
            return 'A window with a Save button.'
        self.m = ts.TaskManager(describer=describe, vision=lambda target, im, **kw: (100, 50, None))
        self.started = self.m.start({'goal':'Review Save button','window':'demo-window',
                                     'allowed_actions':['observe','move','click']})
        self.id = self.started['task_id']
        self.payload = {'window':'demo-window', 'target':'Save button', 'screenshot_base64':image()}

    def test_lifecycle_memory_and_verification_fail_closed(self):
        first = self.m.observe(self.id,self.payload)['observation']
        self.assertEqual((first['coordinate']['x'],first['coordinate']['y']), (100,50))
        self.assertEqual(self.m.plan(self.id,{})['recommendation'],'review_target')
        permit = self.m.action(self.id, {'action':'move', 'screenshot_token':first['screenshot_token'],
                        'confirmed':True, 'reviewed_region':{'left':80,'top':30,'right':130,'bottom':70}})
        self.assertEqual(permit['reviewed_region']['left'],80)
        with self.assertRaisesRegex(ts.TaskError, 'user-reviewed target region'):
            self.m.action(self.id, {'action':'click','screenshot_token':first['screenshot_token'], 'confirmed':True})
        v = self.m.plan(self.id,{'expected':'saved','new_screenshot_token':first['screenshot_token']},verify=True)
        self.assertFalse(v['verified'])
        self.assertEqual(self.m.close(self.id, 'finish')['cleared_observations'], 1)
        self.assertEqual(self.m.tasks,{})
        with self.assertRaises(ts.TaskError):self.m.plan(self.id,{})

    def test_ax_unique_and_context_limit(self):
        ax = self.payload | {'selector':{'name':'Save','role':'button'},
                             'nodes':[{'name':'Save','role':'button','bbox':{'x':40,'y':30,'width':50,'height':30}}]}
        r=self.m.observe(self.id,ax)['observation']
        self.assertEqual((r['coordinate']['x'],r['coordinate']['y']),(65,45))
        with self.assertRaisesRegex(ts.TaskError,'confirmation'):
            self.m.action(self.id,{'action':'click','screenshot_token':r['screenshot_token'],'confirmed':False})
        handoff = self.m.action(self.id,{'action':'click','screenshot_token':r['screenshot_token'],'confirmed':True})
        self.assertEqual(handoff['status'], 'requires_windows_bridge')
        with patch.object(ts,'MAX_CONTEXT_TOKENS',50):
            with self.assertRaisesRegex(ts.TaskError, 'context_limit_exceeded'):self.m.observe(self.id,ax)
        self.assertEqual(len(self.m.tasks[self.id].observations),1)
        self.m.close(self.id,'cancel')

    def test_parallel_sessions_serial_model(self):
        active=0; peak=0; lock=threading.Lock()
        def serial(im,context):
            nonlocal active,peak
            with lock:active+=1;peak=max(active,peak)
            time.sleep(.025)
            with lock:active-=1
            return 'A window with Save.'
        m=ts.TaskManager(describer=serial, vision=lambda target,im,**kw:(100,50,None))
        ids=[m.start({'goal':str(i),'window':'demo-window','allowed_actions':['observe']})['task_id'] for i in range(6)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            records=list(pool.map(lambda id:m.observe(id,self.payload),ids))
        self.assertEqual(len(records),6)
        self.assertEqual(peak,1)
        for id in ids:m.close(id,'finish')
        self.assertFalse(m.tasks)

    def test_window_mismatch_and_repeated_target_fail_closed(self):
        with self.assertRaises(ts.TaskError):self.m.observe(self.id,self.payload|{'window':'other'})
        ax=self.payload|{'selector':{'name':'Save','role':'button'},'nodes':[
            {'name':'Save','role':'button','bbox':{'x':0,'y':0,'width':20,'height':20}}]*2}
        with self.assertRaises(ts.locator.LocatorError):self.m.observe(self.id,ax)
        self.assertEqual(len(self.m.tasks[self.id].observations),0)
        self.m.close(self.id,'cancel')

if __name__ == '__main__':unittest.main()
