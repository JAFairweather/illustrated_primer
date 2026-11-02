import unittest
from unittest.mock import patch

from notebook_media_return import return_image


class ReturnImageTest(unittest.TestCase):
    def test_checks_pending_identity_before_upload_and_preserves_exact_callback(self):
        request = 'notebook-' + 'a'*32
        with patch('notebook_media_return.call', side_effect=[
            {'jobs': [{'request': request, 'page': 'doc/page.rm'}]},
            {'request': request, 'state': 'waiting', 'media_pending': True},
            {'asset': 'b'*64}, {'state': 'ready'}]) as call:
            receipt = return_image(request, {'png': 'bytes', 'kind': 'illustration'}, 'A dog.')
            self.assertEqual(receipt['state'], 'ready')
            self.assertEqual(call.call_args.args, ('/notebook-reply', {
                'request': request, 'text': 'A dog.\n[[notebook-asset:' + 'b'*64 + ']]'}))

    def test_stale_or_completed_request_never_uploads(self):
        request = 'notebook-' + 'a'*32
        for status in ({'request': 'other', 'state': 'waiting', 'media_pending': True},
                       {'request': request, 'state': 'written', 'media_pending': False},
                       {'request': request, 'state': 'waiting', 'media_pending': False}):
            with patch('notebook_media_return.call', side_effect=[
                {'jobs': [{'request': request, 'page': 'doc/page.rm'}]}, status]) as call:
                with self.assertRaises(ValueError):
                    return_image(request, {'png': 'bytes', 'kind': 'illustration'}, 'A dog.')
                self.assertEqual(call.call_count, 2)


if __name__ == '__main__':
    unittest.main()
