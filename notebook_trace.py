"""One dated line per stage of each notebook request, so a failed Respond can be explained from the log.

Stages, in order: press, page_read, new_ink, submitted, composed, rendered, placed, written, acknowledged.
Besides those: refused (respond() raised), state (the page's answer state changed), held (an error was recorded
against the page), and one line per native endpoint the tablet calls. Every line carries the request id when one is
known; a line that only knows the page takes the page's latest request.

The trace is append-only JSON lines at HERD_BOARD_TRACE (default ~/Library/Logs/herd-board-trace.jsonl).
`herd-board-trace` reads it back.
"""
import json
import os
import sys
import threading
import time

TRACE = os.path.expanduser(os.environ.get('HERD_BOARD_TRACE', '~/Library/Logs/herd-board-trace.jsonl'))
if 'unittest' in sys.modules and 'HERD_BOARD_TRACE' not in os.environ:
	# A test run never writes the live trace (or its evidence frames beside it).
	import tempfile
	TRACE = os.path.join(tempfile.mkdtemp(prefix='herd-board-test-trace-'), 'trace.jsonl')
_lock = threading.Lock()
_latest = {}  # page path -> its latest request id
_last = {}    # (request, stage) -> the last (outcome, evidence) written, so repeated polls log once


def now():
	t = time.time()
	return time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(t)) + '.%03d' % (t % 1 * 1000)


def bind(path, request):
	"""request is now the page's latest request."""
	with _lock:
		_latest[path] = request


def request_for(path):
	with _lock:
		return _latest.get(path)


def event(stage, outcome='ok', request=None, path=None, **evidence):
	"""Append one stage line; a line identical to the previous one for the same request and stage is skipped."""
	if not request and path:
		request = request_for(path)
	evidence = {k: (str(v)[:400] if isinstance(v, (str, Exception)) else v) for k, v in evidence.items() if v is not None}
	key, value = (request or path, stage), (outcome, json.dumps(evidence, sort_keys=True, default=str))
	line = dict(t=now(), request=request, path=path, stage=stage, outcome=outcome, **evidence)
	with _lock:
		if _last.get(key) == value:
			return
		_last[key] = value
		if len(_last) > 4000:
			_last.clear()
		try:
			os.makedirs(os.path.dirname(TRACE), exist_ok=True)
			with open(TRACE, 'a') as stream:
				stream.write(json.dumps(line, default=str) + '\n')
		except OSError as e:
			print(now(), 'trace unavailable:', e, file=sys.stderr, flush=True)
	if outcome != 'ok':
		print(now()[11:], 'trace', request or '-', stage, outcome, evidence.get('reason', ''), file=sys.stderr, flush=True)


class Traced(dict):
	"""A page-keyed dict whose every assignment is also a trace line (answers, reply_errors)."""

	def __init__(self, stage, failed=False):
		super().__init__()
		self.stage, self.failed = stage, failed

	def __setitem__(self, path, value):
		super().__setitem__(path, value)
		if self.failed:
			event(self.stage, 'failed', path=path, reason=value)
		else:
			event(self.stage, str(value), path=path)


class Dated:
	"""stderr with the date in front of every line (the server's own lines carry only the time)."""

	def __init__(self, stream):
		self.stream, self.start = stream, True

	def write(self, s):
		out = []
		for piece in s.splitlines(keepends=True):
			if self.start:
				out.append(time.strftime('%Y-%m-%d '))
			out.append(piece)
			self.start = piece.endswith('\n')
		self.stream.write(''.join(out))
		return len(s)

	def __getattr__(self, name):
		return getattr(self.stream, name)
