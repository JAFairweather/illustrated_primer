"""herd-board-scorecard offline: timings from the trace, replays skipped, one topic per run."""
import importlib.machinery
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader('herd_board_scorecard', str(HERE/'herd-board-scorecard'))
spec = importlib.util.spec_from_loader(loader.name, loader)
scorecard = importlib.util.module_from_spec(spec)
loader.exec_module(scorecard)


def run(request, t, picture_ms=20000, finished=True):
	stages = [{'request': request, 't': t, 'stage': 'press', 'outcome': 'ok'},
			  {'request': request, 't': t, 'stage': 'picture', 'outcome': 'ok', 'ms': picture_ms, 'frames': 3},
			  {'request': request, 't': t, 'stage': 'picture', 'outcome': 'drawn',
			   'stages': [{'points': 400}, {'points': 600}]}]
	if finished:
		stages.append({'request': request, 't': t, 'stage': 'acknowledged', 'outcome': 'ok',
					   'timing': {'write_started': 30500, 'written': 140000, 'reply_ready': 20000}})
	else:
		stages.append({'request': request, 't': t, 'stage': 'cleared', 'outcome': 'failed', 'reason': 'Timed out'})
	return {'request': request, 'stages': stages}


class ScorecardTest(unittest.TestCase):
	def test_measure_reads_timings_and_ink(self):
		m = scorecard.measure(run('a', '2026-10-31T09:00:00'))
		self.assertEqual((m['end'], m['first_ink_s'], m['first_word_s'], m['written_s']), ('acknowledged', 30.5, 31.5, 140))
		self.assertEqual((m['picture'], m['points'], m['picture_s'], m['replay']), ('drawn', 1000, 20, False))

	def test_unfinished_run_keeps_its_reason(self):
		m = scorecard.measure(run('a', '2026-10-31T09:00:00', finished=False))
		self.assertEqual((m['end'], m['reason']), ('cleared', 'Timed out'))
		self.assertNotIn('first_ink_s', m)

	def test_benchmark_skips_replays_and_prefers_finished_runs(self):
		with tempfile.TemporaryDirectory() as tmp:
			def save(request, text):
				lesson = {'mode': 'lesson', 'intent': text, 'steps': [], 'takeaway': ''}
				Path(tmp, f'{request}.json').write_text(json.dumps({'text': json.dumps(lesson)}))
			save('old', 'A lever lifts a rock.')
			save('stuck', 'A lever and a fulcrum.')
			save('replay', 'The lever again.')
			save('band', 'Who is the band Slightly Stoopid, by the ocean?')
			runs = {'old': run('old', '2026-10-30T09:00'), 'stuck': run('stuck', '2026-10-31T08:00', finished=False),
					'replay': run('replay', '2026-10-31T09:00', picture_ms=3),
					'band': run('band', '2026-10-31T07:00')}
			scorecard.REPLIES, saved = tmp, scorecard.REPLIES
			try:
				picked = scorecard.benchmark(runs)
			finally:
				scorecard.REPLIES = saved
		self.assertEqual(picked, {'lever': 'old', 'slightly stoopid': 'band'})


if __name__ == '__main__':
	unittest.main()
