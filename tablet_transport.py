"""Tablet-only SSH options: existing host identity, short-lived local reuse.

No SSH configuration, keys, network settings, or remote services are changed.
The control socket is private to this user's SSH client and expires after 120s
without an active session. OpenSSH auto mode reconnects if no master is alive.
"""
import os

# The agent harness has a different HOME from launchd. Use the project's
# explicitly granted owner paths, as the existing tablet test client does.
OWNER = os.environ.get('HERD_BOARD_OWNER', os.path.expanduser('~'))


def tablet_ssh(host):
    options = ['ssh', '-F', '/dev/null', '-o', 'BatchMode=yes',
               '-o', 'ConnectTimeout=6', '-o', 'StrictHostKeyChecking=yes',
               '-o', 'UserKnownHostsFile=' + OWNER + '/.ssh/known_hosts']
    if host == 'root@remarkable.local':
        options += ['-o', 'HostKeyAlias=remarkable.lan']
    # Scope reuse to this project tablet, never R1/Yoga or other SSH targets.
    if host in ('root@remarkable.lan', 'root@remarkable.local'):
        # Both spellings are pinned to the SAME existing host identity above.
        # Share a project-only socket so a native pen test/capture also warms
        # the backend's connection; separate %C sockets cost ~0.4s per cold hop.
        options += ['-o', 'ControlMaster=auto', '-o', 'ControlPersist=120',
                    '-o', 'ControlPath=' + OWNER + '/.buzz/OUTBOX/.rm-tablet-root']
    return options + [host]
