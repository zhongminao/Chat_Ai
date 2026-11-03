"""Real loopback HTTP lifecycle test with fake vision, no screenshots persisted."""
import base64
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import sys
from threading import Thread
import unittest
from urllib.request import Request, urlopen

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import task_service as ts


class HttpTest(unittest.TestCase):
    def test_lifecycle(self):
        manager = ts.TaskManager(describer=lambda *_: 'Save is visible',
                                 vision=lambda *_args, **_kwargs:(42,30,None))
        class Handler(ts.TaskHandler): pass
        Handler.manager = manager
        with ThreadingHTTPServer(('127.0.0.1',0), Handler) as server:
            thread=Thread(target=server.serve_forever,daemon=True);thread.start()
            def post(path,obj):
                body=json.dumps(obj).encode()
                with urlopen(Request(f'http://127.0.0.1:{server.server_port}{path}',body,
                                     {'Content-Type':'application/json'}),timeout=3) as r:return json.load(r)
            try:
                task=post('/start_task',{'goal':'Save','window':'demo','allowed_actions':['observe','move']})['task_id']
                b=BytesIO();Image.new('RGB',(100,80),'white').save(b,'PNG')
                obs=post(f'/task/{task}/observe',{'window':'demo','target':'Save',
                                                  'screenshot_base64':base64.b64encode(b.getvalue()).decode()})
                self.assertEqual(obs['observation']['coordinate']['x'],42)
                self.assertEqual(post(f'/task/{task}/plan',{})['recommendation'],'review_target')
                self.assertFalse(post(f'/task/{task}/verify',{'expected':'saved','new_screenshot_token':obs['observation']['screenshot_token']})['verified'])
                self.assertEqual(post(f'/task/{task}/finish',{})['cleared_observations'],1)
                self.assertEqual(manager.tasks,{})
            finally:server.shutdown();thread.join(timeout=2)

if __name__ == '__main__':unittest.main()
