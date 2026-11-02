"""Private bearer capabilities for notebook HTTP controls; never log credentials.

The tablet can operate its notebook, not upload replies or arm diagnostic tests.
Trusted local helpers use a separate capability. Existing read-only dashboard
routes and legacy letter UI routes are outside this notebook-specific policy.
"""
import hmac
import json
import os
import re
import secrets
import stat


TABLET_ROUTES = {
    ('GET', '/answer'), ('POST', '/respond'), ('POST', '/write'),
    ('POST', '/write-live'), ('POST', '/native-text'),
    ('POST', '/native-text-done'), ('POST', '/notebook-media-proof'),
    ('POST', '/native-text-failed'),
    ('POST', '/native-context'),
    ('POST', '/native-probe-result'),
    ('POST', '/native-probe-claim'),
    ('POST', '/native-ink-claim'), ('POST', '/native-ink-done'),
    ('POST', '/notebook-ink-proof'),
    ('POST', '/notebook-answer-stream'),
}


def credential_path():
    return os.environ.get('HERD_BOARD_AUTH_FILE') or os.path.join(
        os.path.dirname(os.path.realpath(__file__)), '.notebook-auth.json')


def load_credentials(path=None, create=False):
    path = path or credential_path()
    if create:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w') as stream:
                json.dump({'version': 1, 'local': secrets.token_urlsafe(32),
                           'tablet': secrets.token_urlsafe(32)}, stream)
                stream.flush()
                os.fsync(stream.fileno())
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('notebook credentials must be owner-only regular files')
        raw = stream.read(2049)
    if len(raw) > 2048:
        raise ValueError('invalid notebook credential file')
    try:
        data = json.loads(raw)
        valid = (set(data) == {'version', 'local', 'tablet'} and type(data['version']) is int and data['version'] == 1
                 and all(isinstance(data[k], str) and re.fullmatch(r'[A-Za-z0-9_-]{43}', data[k])
                         for k in ('local', 'tablet')) and data['local'] != data['tablet'])
    except (ValueError, TypeError, KeyError):
        valid = False
    if not valid:
        raise ValueError('invalid notebook credential file')
    return data


def protected_route(path):
    return (path.startswith(('/notebook-', '/native-'))
            or path in ('/respond', '/write', '/write-live', '/answer', '/restart'))


class NotebookAuth:
    def __init__(self, credentials):
        self.credentials = credentials

    def rejection(self, method, path, headers):
        if not protected_route(path):
            return None
        # No browser-origin requests, cookies or query-string credentials.
        if headers.get('Origin') is not None:
            return 403
        value = headers.get('Authorization', '')
        if not isinstance(value, str) or not value.startswith('Bearer '):
            return 401
        token = value[7:]
        # compare_digest on ASCII bytes also rejects malformed Unicode safely.
        supplied = token.encode('utf-8')
        if hmac.compare_digest(supplied, self.credentials['local'].encode('ascii')):
            return None
        if hmac.compare_digest(supplied, self.credentials['tablet'].encode('ascii')):
            return None if (method, path) in TABLET_ROUTES else 403
        return 401


def local_headers(path=None):
    return {'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + load_credentials(path)['local']}


def preservation_key(path=None):
    """Domain-separated journal HMAC key, never stored beside the journal.

    Rotating the existing local credential deliberately invalidates old keyed
    text baselines; they remain held, never silently re-baselined.
    """
    return hmac.digest(load_credentials(path)['local'].encode('ascii'),
                       b'herd-board/native-text-preservation/v1', 'sha256')


def tablet_patch(source, path=None):
    """Return a private deployment payload, never a credential-bearing repo file."""
    placeholder = '__HERD_TABLET_AUTH__'
    if source.count(placeholder) != 1:
        raise ValueError('tablet patch must contain exactly one authentication placeholder')
    return source.replace(placeholder, load_credentials(path)['tablet'])
