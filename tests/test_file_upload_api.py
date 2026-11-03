"""Focused tests for normal-file upload and same-message delivery."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from agent.web.files import file_router
from agent.storage.files import MAX_FILE_BYTES
from agent.storage.session import SessionStore
from agent.web import app as web


class FakeRuntime:
    def __init__(self):
        self.messages = []
        self.guidance = []

    def enqueue(self, value):
        self.messages.append(value)

    def send(self, value, message_id):
        self.guidance.append((value, message_id))


class UploadApiBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SessionStore(Path(self.temp.name))
        self.session = self.store.create()
        self.other = self.store.create()
        self.runtime = FakeRuntime()
        self.store_patch = patch.object(web, 'directory_for', self.store.path)
        self.runtime_patch = patch.object(web, 'runtime', return_value=self.runtime)
        self.store_patch.start()
        self.runtime_patch.start()
        app = FastAPI()
        app.include_router(file_router(self.store))
        app.post('/api/sessions/{session_id}/messages')(web.send)
        app.post('/api/sessions/{session_id}/guidance')(web.guide)
        app.add_exception_handler(FileNotFoundError, web.business_error)
        app.add_exception_handler(ValueError, web.business_error)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.runtime_patch.stop()
        self.store_patch.stop()
        self.store.database.close()
        self.temp.cleanup()

    def upload(self, name='报告.pdf', data=b'%PDF-1.4'):
        return self.client.post(f'/api/sessions/{self.session.id}/files',
                                files={'file': (name, data, 'application/octet-stream')})

class FileUploadApiTests(UploadApiBase):
    def test_upload_send_and_guidance_with_images_and_plain_text(self):
        response = self.upload()
        self.assertEqual(response.status_code, 200)
        file = response.json()['file']
        self.assertEqual(file['name'], '报告.pdf')
        self.assertEqual(file['filename'], '报告.pdf')
        self.assertEqual(file['size'], 8)
        self.assertRegex(file['id'], r'^[0-9a-f]{32}$')
        self.assertEqual(file['path'], str((self.session.directory / 'attachments' / f"{file['id']}.pdf").resolve()))
        self.assertEqual(Path(file['path']).read_bytes(), b'%PDF-1.4')
        url = f'/api/sessions/{self.session.id}/messages'
        self.assertEqual(self.client.post(url, json={'content': '请总结这个文件', 'files': [file['id']],
                                                'images': ['img1']}).status_code, 200)
        self.assertEqual(self.runtime.messages[-1].text, f"附件：报告.pdf，路径：{file['path']}\n\n请总结这个文件")
        self.assertEqual(self.runtime.messages[-1].images, ('img1',))
        self.assertEqual(self.client.post(url, json={'content': '  原文  ', 'images': ['img1']}).status_code, 200)
        self.assertEqual(self.runtime.messages[-1].text, '  原文  ')
        self.assertEqual(self.runtime.messages[-1].images, ('img1',))
        self.assertEqual(self.client.post(url, json={'images': ['img1']}).status_code, 200)
        self.assertEqual(self.runtime.messages[-1].text, '')
        self.assertEqual(self.runtime.messages[-1].images, ('img1',))
        self.assertEqual(self.client.post(f'/api/sessions/{self.session.id}/guidance',
                                          json={'content': '细读', 'files': [file['id']], 'images': ['img1'],
                                                'message_id': 'guidance1'}).status_code, 200)
        self.assertEqual(self.runtime.guidance[-1][0].text, f"附件：报告.pdf，路径：{file['path']}\n\n细读")
        self.assertEqual(self.runtime.guidance[-1][0].images, ('img1',))
        self.assertEqual(self.runtime.guidance[-1][1], 'guidance1')

    def test_multiple_files_cross_session_and_bad_references(self):
        a, b = self.upload().json()['file'], self.upload('note.txt', b'notes').json()['file']
        url = f'/api/sessions/{self.session.id}/messages'
        self.assertEqual(self.client.post(url, json={'files': [a['id'], b['id']], 'content': '比较'}).status_code, 200)
        self.assertEqual(self.runtime.messages[-1].text,
                         f"附件：报告.pdf，路径：{a['path']}\n附件：note.txt，路径：{b['path']}\n\n比较")
        for files in ([a['id'], a['id']], ['/etc/passwd'], ['x' * 32]):
            self.assertIn(self.client.post(url, json={'files': files, 'content': 'test'}).status_code, (400, 404))
        self.assertEqual(self.client.post(f'/api/sessions/{self.other.id}/messages',
                                          json={'files': [a['id']], 'content': 'test'}).status_code, 404)
        self.assertEqual(self.client.post(f'/api/sessions/{self.other.id}/guidance',
                                          json={'files': [a['id']], 'message_id': 'g'}).status_code, 404)
        self.assertEqual(len(self.runtime.messages), 1)
        self.assertFalse(self.runtime.guidance)

    def test_bad_session_filename_and_upload_limits_cleanup(self):
        self.assertEqual(self.client.post('/api/sessions/invalid/files',
                                          files={'file': ('x', b'x')}).status_code, 404)
        renamed = self.upload('../../../../evil\n.pdf').json()['file']
        self.assertEqual(renamed['filename'], 'evil%0A.pdf')
        self.assertEqual(Path(renamed['path']).parent, self.session.directory / 'attachments')
        self.assertEqual(self.upload(data=b'').status_code, 400)
        self.assertEqual(self.upload(data=b'x' * (MAX_FILE_BYTES + 1)).status_code, 413)
        folder = self.session.directory / 'attachments'
        self.assertEqual(len(list(folder.glob('*.file.json'))), 1)
        self.assertEqual(len(list(folder.iterdir())), 2)

    def test_missing_or_modified_attachment_is_not_sent(self):
        file = self.upload().json()['file']
        url = f'/api/sessions/{self.session.id}/messages'
        path = Path(file['path'])
        path.write_bytes(b'bad')
        self.assertEqual(self.client.post(url, json={'files': [file['id']]}).status_code, 404)
        path.unlink()
        path.symlink_to('/etc/hosts')
        self.assertEqual(self.client.post(url, json={'files': [file['id']]}).status_code, 404)
        self.assertFalse(self.runtime.messages)


class FolderUploadApiTests(UploadApiBase):
    def folder(self, paths=('src/main.py', 'docs/readme.md'), contents=(b'print(1)', b'hello'),
               name='project', session_id=None):
        return self.client.post(f'/api/sessions/{session_id or self.session.id}/files/folder',
                                data={'name': name, 'paths': list(paths)},
                                files=[('files', (path.rsplit('/', 1)[-1], body))
                                       for path, body in zip(paths, contents)])

    def test_folder_upload_single_reference_and_session_isolation(self):
        response = self.folder()
        self.assertEqual(response.status_code, 200, response.text)
        folder = response.json()['file']
        self.assertEqual(folder['kind'], 'folder')
        self.assertEqual(folder['count'], 2)
        self.assertEqual(folder['size'], 13)
        self.assertEqual(Path(folder['path']) / 'src/main.py',
                         self.session.directory / 'attachments' / f"{folder['id']}.folder" / 'src/main.py')
        self.assertEqual((Path(folder['path']) / 'src/main.py').read_bytes(), b'print(1)')
        self.assertEqual((Path(folder['path']) / 'docs/readme.md').read_bytes(), b'hello')
        url = f'/api/sessions/{self.session.id}/messages'
        self.assertEqual(self.client.post(url, json={'files': [folder['id']], 'content': 'inspect'}).status_code, 200)
        self.assertEqual(self.runtime.messages[-1].text,
                         f"文件夹附件：project，目录路径：{folder['path']}\n\ninspect")
        self.assertEqual(self.client.post(f'/api/sessions/{self.other.id}/messages',
                                          json={'files': [folder['id']]}).status_code, 404)
        self.assertEqual(self.folder(session_id='invalid').status_code, 404)

    def test_folder_bad_paths_and_collisions_no_leftovers(self):
        for paths in (('../escape',), ('/absolute',), ('a\\b',), ('a//b',),
                      ('a/./b',), ('a/../b',), ('a', 'a/b'), ('a/B', 'a/b'), ('a', 'a')):
            with self.subTest(paths=paths):
                result = self.folder(paths, tuple(b'x' for _ in paths))
                self.assertEqual(result.status_code, 400, result.text)
        self.assertEqual(self.folder(('a',), (b'',)).status_code, 400)
        self.assertEqual(self.folder(('a',), (b'x',), '../bad').status_code, 400)
        self.assertEqual(self.folder(('a',), (b'x' * (MAX_FILE_BYTES + 1),)).status_code, 413)
        attachments = self.session.directory / 'attachments'
        self.assertFalse(attachments.exists() and list(attachments.iterdir()))

    def test_folder_tamper_and_total_and_count_limits(self):
        from agent.storage.files import FileStore, MAX_FOLDER_FILES
        from io import BytesIO
        store = FileStore(self.session.directory)
        with patch('agent.storage.files.MAX_FOLDER_BYTES', 3):
            with self.assertRaises(ValueError):
                store.add_folder([BytesIO(b'12'), BytesIO(b'34')], ['a', 'b'], 'project')
        self.assertFalse(list(store.root.iterdir()))
        with self.assertRaises(ValueError):
            store.add_folder([BytesIO(b'x')] * (MAX_FOLDER_FILES + 1),
                             [f'{x}' for x in range(MAX_FOLDER_FILES + 1)], 'project')
        folder = self.folder().json()['file']
        url = f'/api/sessions/{self.session.id}/messages'
        child = Path(folder['path']) / 'docs/readme.md'
        child.unlink()
        child.symlink_to('/etc/hosts')
        self.assertEqual(self.client.post(url, json={'files': [folder['id']]}).status_code, 404)
        self.assertFalse(self.runtime.messages)


if __name__ == '__main__':
    unittest.main()
