"""The committed replay corpus (replay/*.json, real model replies) must all still reach the page offline."""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.realpath(__file__))


class ReplayCorpusTest(unittest.TestCase):
    def test_every_captured_reply_still_reaches_the_page(self):
        run = subprocess.run([sys.executable, os.path.join(HERE, 'herd-board-replay')], capture_output=True, text=True, timeout=300)
        lines = [l for l in run.stdout.splitlines() if l[:4] in ('ok  ', 'HELD')]
        self.assertTrue(lines, run.stdout + run.stderr[-2000:])
        self.assertEqual(run.returncode, 0, '\n'.join(l for l in lines if l.startswith('HELD')))


if __name__ == '__main__':
    unittest.main()
