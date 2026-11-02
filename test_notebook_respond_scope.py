from pathlib import Path
import re
import unittest

QMD = Path(__file__).with_name('xochitl')/'herdRespond.qmd'


def _block(source, start):
    """Text inside the braces that open at or after start."""
    i = source.index('{', start)+1
    depth, j = 1, i
    while depth:
        depth += {'{': 1, '}': -1}.get(source[j], 0)
        j += 1
    return i, j-1


class RespondScopeTests(unittest.TestCase):
    def test_timer_handlers_reach_button_functions_through_its_id(self):
        # A Timer is not the component root, so a bare call to a herdButton function is a ReferenceError at run
        # time (2026-10-30: herdLaterArm dropped every pending step and no reply reached the page).
        source = QMD.read_text()
        start, end = _block(source, source.rindex('{', 0, source.index('id: herdButton')))
        depth, own = 0, set()
        for m in re.finditer(r'[{}]|function (herd\w+)\(', source[start:end]):
            if m.group(1) and depth == 0:
                own.add(m.group(1))
            elif not m.group(1):
                depth += 1 if m.group() == '{' else -1
        self.assertIn('herdLaterArm', own)
        for m in re.finditer(r'onTriggered:\s*(\{)?', source):
            body = source[slice(*_block(source, m.start()))] if m.group(1) else source[m.end():source.index('\n', m.end())]
            bare = [c for c in re.findall(r'(?<![\w.])(herd\w+)\(', body) if c in own]
            self.assertEqual(bare, [], f'line {source.count(chr(10), 0, m.start())+1}')


if __name__ == '__main__':
    unittest.main()
