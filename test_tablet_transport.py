import unittest
from tablet_transport import tablet_ssh


class TabletTransportTest(unittest.TestCase):
    def test_local_fallback_keeps_existing_trust_and_scoped_reuse(self):
        command = tablet_ssh('root@remarkable.local')
        self.assertEqual(command[:3], ['ssh', '-F', '/dev/null'])
        self.assertEqual(command[-1], 'root@remarkable.local')
        for option in ('StrictHostKeyChecking=yes', 'HostKeyAlias=remarkable.lan',
                       'ControlMaster=auto', 'ControlPersist=120'):
            self.assertIn(option, command)
        path = next(arg for arg in command if arg.startswith('ControlPath='))
        self.assertTrue(path.endswith('/.buzz/OUTBOX/.rm-tablet-root'))
        self.assertLess(len(path.removeprefix('ControlPath=')), 90)
        alternate = tablet_ssh('root@remarkable.lan')
        self.assertIn(path, alternate, 'two names of the same pinned tablet share the warm connection')

    def test_other_targets_never_share_project_tablet_connection(self):
        command = tablet_ssh('root@other-device')
        self.assertEqual(command[-1], 'root@other-device')
        self.assertFalse(any(arg.startswith(('ControlPath=', 'ControlPersist=',
                                              'HostKeyAlias=')) for arg in command))

    def test_lan_name_uses_its_own_known_host_identity(self):
        command = tablet_ssh('root@remarkable.lan')
        self.assertIn('StrictHostKeyChecking=yes', command)
        self.assertNotIn('HostKeyAlias=remarkable.lan', command)
