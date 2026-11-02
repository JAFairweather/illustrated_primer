import http.client
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from notebook_auth import NotebookAuth, TABLET_ROUTES, load_credentials, local_headers, tablet_patch, preservation_key
import notebook_client


class AuthenticationTest(unittest.TestCase):
    def test_text_fingerprint_key_is_external_domain_separated_and_rotation_sensitive(self):
        with patch('notebook_auth.load_credentials',return_value={'local':'l'*43,'tablet':'t'*43}):
            first=preservation_key()
            self.assertEqual(len(first),32)
            self.assertEqual(first,preservation_key())
            self.assertNotEqual(first,b'l'*43)
        with patch('notebook_auth.load_credentials',return_value={'local':'n'*43,'tablet':'t'*43}):
            self.assertNotEqual(first,preservation_key())
        with patch('notebook_auth.load_credentials',side_effect=OSError('unavailable')):
            with self.assertRaises(OSError):
                preservation_key()

    def test_overnight_wake_is_still_bounded_and_rejects_invalid_duration_before_http(self):
        for minutes in (True, 0, 721):
            with patch.object(notebook_client,'call') as request:
                with self.assertRaises(ValueError):
                    notebook_client.maintain_awake('905df7ae-ff54-46b9-a71e-45bb02bef638', minutes)
                request.assert_not_called()

    def test_keep_awake_retries_brief_reload_then_releases_without_input(self):
        now = [0]
        calls = []
        def request(route, body):
            calls.append((route, body))
            if len(calls) == 1:
                raise OSError('brief interface reload')
            return {'keep_awake_seconds': body['seconds']}
        with patch.object(notebook_client, 'call', side_effect=request), \
             patch.object(notebook_client.time, 'monotonic', side_effect=lambda: now[0]), \
             patch.object(notebook_client.time, 'sleep', side_effect=lambda seconds: now.__setitem__(0, now[0]+seconds)):
            notebook_client.maintain_awake('4ffe884f-a4d6-437d-8091-75bf63252c16', minutes=1)
        self.assertEqual([body['seconds'] for _, body in calls], [180, 180, 0])
        self.assertTrue(all(route == '/notebook-keep-awake' for route, _ in calls))
        self.assertEqual(now[0], 60)

    def test_local_client_uses_header_not_query_or_body_credentials(self):
        with patch.object(notebook_client, 'local_headers', return_value={'Authorization': 'Bearer test-only'}), \
             patch.object(notebook_client.urllib.request, 'urlopen', return_value=io.BytesIO(b'{"ok":true}')) as opened:
            self.assertEqual(notebook_client.call('/notebook-retry', {'request': 'notebook-test'}), {'ok': True})
            sent = opened.call_args.args[0]
            self.assertEqual(sent.get_header('Authorization'), 'Bearer test-only')
            self.assertNotIn('test-only', sent.full_url)
            self.assertNotIn(b'test-only', sent.data)

    def test_private_creation_is_stable_and_rejects_insecure_files_or_links(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'credentials.json'
            first = load_credentials(str(path), create=True)
            self.assertTrue(first == load_credentials(str(path), create=True))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(first['local'] != first['tablet'])
            self.assertTrue(local_headers(str(path))['Authorization'].endswith(first['local']))
            rendered = tablet_patch('credential=__HERD_TABLET_AUTH__', str(path))
            self.assertTrue(first['tablet'] in rendered)
            self.assertTrue(first['local'] not in rendered)
            with self.assertRaises(ValueError):
                tablet_patch('missing marker', str(path))
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                load_credentials(str(path))
            path.chmod(0o600)
            link = Path(directory) / 'link.json'
            link.symlink_to(path)
            with self.assertRaises(OSError):
                load_credentials(str(link))

    def test_roles_origins_and_missing_credentials(self):
        credentials = {'local': 'l'*43, 'tablet': 't'*43}
        policy = NotebookAuth(credentials)
        for method, route in TABLET_ROUTES:
            with self.subTest(method=method, route=route):
                self.assertIsNone(policy.rejection(method, route, {'Authorization': 'Bearer ' + credentials['tablet']}))
                self.assertEqual(policy.rejection(method, route, {}), 401)
        for route in ('/notebook-test', '/notebook-media-test', '/notebook-reply', '/notebook-media', '/notebook-audit-view',
                      '/notebook-revise', '/notebook-retry', '/notebook-response', '/notebook-status', '/notebook-device-context', '/notebook-keep-awake', '/notebook-native-probe', '/restart', '/native-future'):
            self.assertEqual(policy.rejection('POST', route, {'Authorization': 'Bearer ' + credentials['tablet']}), 403)
            self.assertIsNone(policy.rejection('POST', route, {'Authorization': 'Bearer ' + credentials['local']}))
        self.assertEqual(policy.rejection('POST', '/respond', {'Authorization': 'Bearer wrong'}), 401)
        self.assertEqual(policy.rejection('POST', '/respond', {'Authorization': 'Bearer ' + credentials['local'], 'Origin': 'null'}), 403)
        self.assertIsNone(policy.rejection('GET', '/herd.json', {}))

    def test_real_handler_rejects_before_body_or_side_effects(self):
        path = Path(__file__).with_name('herd-board-serve')
        loader = importlib.machinery.SourceFileLoader('herd_auth_test_server', str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        server_module = importlib.util.module_from_spec(spec)
        loader.exec_module(server_module)
        credentials = {'local': 'l'*43, 'tablet': 't'*43}
        with patch.object(server_module, 'notebook_auth', NotebookAuth(credentials)), \
             patch.object(server_module, 'respond', return_value={'accepted': True}) as respond, \
             patch.object(server_module, 'notebook_reply') as reply, \
             patch.object(server_module, 'retry_notebook_response', return_value={'retry_armed': True}) as retry, \
             patch.object(server_module, 'revise_notebook_response', return_value={'revised': True}) as revise:
            server = ThreadingHTTPServer(('127.0.0.1', 0), server_module.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def request(method, route, body='not valid JSON', headers=None):
                connection = http.client.HTTPConnection(*server.server_address, timeout=3)
                try:
                    connection.request(method, route, body=body, headers=headers or {})
                    response = connection.getresponse()
                    return response.status, response.read()
                finally:
                    connection.close()
            try:
                for route in ('/respond', '/notebook-reply', '/notebook-test', '/notebook-media',
                              '/notebook-media-test', '/notebook-retry', '/notebook-revise', '/write', '/write-live',
                              '/native-text', '/native-text-done', '/native-context', '/native-probe-result', '/native-ink-claim', '/native-ink-done', '/notebook-ink-proof', '/notebook-native-probe', '/notebook-media-proof', '/notebook-keep-awake', '/notebook-answer-stream', '/restart'):
                    self.assertEqual(request('POST', route)[0], 401)
                for route in ('/answer', '/notebook-response', '/notebook-status', '/notebook-device-context'):
                    self.assertEqual(request('GET', route, body=None)[0], 401)
                self.assertEqual(request('GET', '/answer?token=' + credentials['local'], body=None)[0], 401)
                self.assertEqual(request('POST', '/respond', '{}',
                                        {'Authorization': 'Bearer ' + credentials['local'], 'Origin': 'null'})[0], 403)
                respond.assert_not_called(); reply.assert_not_called(); retry.assert_not_called()
                self.assertEqual(request('POST', '/notebook-retry', '{}',
                                        {'Authorization': 'Bearer ' + credentials['tablet']})[0], 403)
                retry.assert_not_called()
                self.assertEqual(request('POST', '/notebook-revise', '{}',
                                        {'Authorization': 'Bearer ' + credentials['tablet']})[0], 403)
                revise.assert_not_called()
                revision = dict(request='notebook-test', expected_sha256='0'*64, text='correction')
                self.assertEqual(request('POST', '/notebook-revise', json.dumps(revision),
                                        {'Authorization': 'Bearer ' + credentials['local']})[0], 200)
                revise.assert_called_once_with(revision['request'], revision['expected_sha256'], revision['text'])
                self.assertEqual(request('POST', '/respond', '{}',
                                        {'Authorization': 'Bearer ' + credentials['tablet']})[0], 200)
                respond.assert_called_once()
                self.assertEqual(request('POST', '/notebook-retry', '{}',
                                        {'Authorization': 'Bearer ' + credentials['local']})[0], 200)
                retry.assert_called_once()
                with patch.object(server_module, 'notebook_auth', None):
                    self.assertEqual(request('POST', '/respond')[0], 503)
                self.assertEqual(respond.call_count, 1)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
