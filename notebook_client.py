"""Authenticated localhost notebook helper and private tablet-patch deployment.

Set HERD_BOARD_AUTH_FILE when invoking from a worktree rather than the launchd
copy. Credentials are read from an owner-only file, never arguments or stdout.
Deploy only installs a patch; it does not close notes or restart xochitl.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

from notebook_auth import load_credentials, local_headers, tablet_patch
from tablet_transport import OWNER, tablet_ssh


def call(route, body=None):
    if not route.startswith('/') or route.startswith('//') or any(c in route for c in '\r\n'):
        raise ValueError('localhost notebook route required')
    request = urllib.request.Request('http://127.0.0.1:8791' + route,
                                    data=json.dumps(body).encode() if body is not None else None,
                                    headers=local_headers())
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def deploy_tablet():
    source = Path(__file__).with_name('xochitl').joinpath('herdRespond.qmd').read_text()
    payload = tablet_patch(source).encode()
    target = '/home/root/xovi/exthome/qt-resource-rebuilder/herdRespond.qmd'
    backup = target + '.before-auth-' + time.strftime('%Y%m%d-%H%M%S', time.gmtime())
    command = (f'umask 077; cp {target} {backup} && chmod 600 {backup} && '
               f'cat > {target}.new && chmod 600 {target}.new && mv {target}.new {target}')
    # Never log payload, Request headers or the private rendered patch.
    result = subprocess.run([*tablet_ssh('root@remarkable.local'), command], input=payload,
                            capture_output=True, timeout=30,
                            env=dict(os.environ, SSH_AUTH_SOCK=OWNER + '/.ssh/s/r1-agent.sock'))
    if result.returncode:
        raise RuntimeError('tablet patch installation failed; no interface restart performed')
    return {'installed': True, 'loaded': False, 'restart_required': True}


def maintain_awake(doc, minutes=30):
    """Renew a bounded native maintenance lease, without touching notebook input."""
    import uuid
    if str(uuid.UUID(doc)) != doc or type(minutes) is not int or not 1 <= minutes <= 720:
        raise ValueError('canonical document UUID and 1..720 minutes required')
    end = time.monotonic()+minutes*60
    renew = 0
    try:
        while time.monotonic() < end:
            if time.monotonic() >= renew:
                try:
                    call('/notebook-keep-awake', {'doc': doc, 'seconds': 180})
                except (OSError, ValueError):
                    # Brief server/UI reloads cannot silently terminate the
                    # maintenance helper. No stale page is granted a lease.
                    print('Keep-awake refresh deferred; last tablet lease still expires.', flush=True)
                    renew = time.monotonic()+10
                else:
                    print('Native keep-awake renewed for 180 seconds; no input sent.', flush=True)
                    renew = time.monotonic()+90
            time.sleep(min(10, max(0, end-time.monotonic())))
    finally:
        try:
            call('/notebook-keep-awake', {'doc': doc, 'seconds': 0})
        except (OSError, ValueError):
            pass  # The last lease still expires independently on the tablet.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init')
    commands.add_parser('deploy-tablet')
    awake = commands.add_parser('keep-awake')
    awake.add_argument('doc')
    awake.add_argument('--minutes', type=int, default=30)
    request = commands.add_parser('request')
    request.add_argument('route')
    request.add_argument('--json', dest='body')
    args = parser.parse_args()
    if args.command == 'init':
        load_credentials(create=True)
        print('Private notebook credentials ready; values are not displayed.')
    elif args.command == 'deploy-tablet':
        print(json.dumps(deploy_tablet()))
    elif args.command == 'keep-awake':
        maintain_awake(args.doc, args.minutes)
    else:
        try:
            print(json.dumps(call(args.route, json.loads(args.body) if args.body is not None else None)))
        except urllib.error.HTTPError as error:
            parser.exit(1, f'Notebook HTTP request rejected ({error.code}).\n')


if __name__ == '__main__':
    main()
