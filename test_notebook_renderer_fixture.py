"""Model-free fixture dispatch on the existing authenticated test route."""
import contextlib
import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from notebook_delivery import semantic_delivery, delivery_options
import test_notebook_lesson_server as legacy

DOC, PAGE, PATH = legacy.DOC, legacy.PAGE, legacy.PATH
PARENT = 'a7a7e181-7b6b-4a84-a169-3bc7e5fe35da'


class RendererFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        legacy.LessonServerTest.setUpClass()
        cls.s = legacy.LessonServerTest.s

    @contextlib.contextmanager
    def environment(self, folder='Storyboard tests (Codex)'):
        s=self.s
        context=dict(fresh=True,active=True,doc=DOC,page=PAGE,surface='fixture-surface',
                     content_revision=1,ink_revision=2,view=[1,0,0,1,-702,0])
        def tablet(command):
            return json.dumps(dict(visibleName='To pidog',parent=PARENT) if DOC in command
                              else dict(visibleName=folder)).encode()
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            values=dict(CACHE=directory,PENDING=directory+'/pending.json',notebook_replay=None,
                        ready={},answers={},notebook_jobs={},notebook_names={},reply_errors={},
                        reply_timings={},media_tests={},LESSON_NOTEBOOKS=DOC,letters=[])
            for name,value in values.items():stack.enter_context(patch.object(s,name,value))
            stack.enter_context(patch.object(s.device_context,'snapshot',side_effect=lambda:copy.deepcopy(context)))
            stack.enter_context(patch.object(s,'tablet',side_effect=tablet))
            stack.enter_context(patch.object(s,'agent_list',return_value=[{'name':'pidog','pane_id':'pane'}]))
            capture=stack.enter_context(patch.object(s,'live_capture',return_value='frame'))
            stack.enter_context(patch.object(s,'live_baseline',return_value=directory+'/missing.png'))
            stack.enter_context(patch.object(s,'notebook_crop',return_value='crop'))
            stack.enter_context(patch.object(s,'live_png',return_value=b'test image'))
            send=stack.enter_context(patch.object(s,'send',side_effect=AssertionError('real agent dispatch')))
            reader=stack.enter_context(patch.object(s,'read_letter',side_effect=AssertionError('OCR call')))
            thread=stack.enter_context(patch.object(s.threading,'Thread',side_effect=AssertionError('answer worker')))
            yield context,capture,send,reader,thread

    def arm(self):return self.s.arm_notebook_test(dict(doc=DOC,page=PAGE,fixture='integral'))

    def test_named_fixture_is_one_shot_semantic_and_honestly_labelled(self):
        s=self.s
        with self.environment() as (_,capture,send,reader,thread):
            result=self.arm()
            self.assertEqual(result,dict(armed=True,expires_in=30,renderer_fixture='integral'))
            prepared=s.notebook_replay['response']
            s.media_tests[PATH]={'asset':'reserved-for-real-request','expires':float('inf')}
            result=s.respond(DOC,PAGE,live=True)
            self.assertEqual(result['to'],'Renderer Test')
            self.assertEqual(result['renderer_fixture'],'integral')
            self.assertIsNone(s.notebook_replay)
            self.assertEqual(s.notebook_names[result['request']],'Renderer Test')
            self.assertEqual(s.ready[PATH],prepared)
            self.assertEqual(s.answers[PATH],'ready')
            self.assertTrue(semantic_delivery(s.pend('')[PATH]))
            self.assertTrue(delivery_options(s.pend('')[PATH])['renderer_fixture'])
            self.assertEqual(s.letters,[])
            self.assertIn(PATH,s.media_tests,'fixture must not consume unrelated armed media')
            self.assertIn('fixture_ready',s.reply_timings[PATH])
            self.assertNotIn('submitted',s.reply_timings[PATH])
            capture.assert_called_once();send.assert_not_called();reader.assert_not_called();thread.assert_not_called()

    def test_expired_or_nonlive_fixture_never_falls_back_to_model(self):
        for expired,live in ((True,True),(False,False)):
            with self.subTest(expired=expired,live=live),self.environment() as (_,capture,send,reader,thread):
                self.arm()
                if expired:self.s.notebook_replay['expires']=0
                with self.assertRaisesRegex(ValueError,'expired or requires'):
                    self.s.respond(DOC,PAGE,live=live)
                self.assertIsNone(self.s.notebook_replay)
                capture.assert_not_called();send.assert_not_called();reader.assert_not_called();thread.assert_not_called()

    def test_page_view_input_or_surface_change_stops_before_capture(self):
        for key,value in (('page',DOC),('surface','other'),('ink_revision',3),('content_revision',2),
                          ('view',[1,0,0,1,-702,1]),('fresh',False),('active',False)):
            with self.subTest(key=key),self.environment() as (context,capture,send,reader,thread):
                self.arm();context[key]=value
                with self.assertRaisesRegex(ValueError,'changed'):self.s.respond(DOC,PAGE,live=True)
                capture.assert_not_called();send.assert_not_called();reader.assert_not_called();thread.assert_not_called()
                self.assertEqual(self.s.pend(''),{})

    def test_change_during_capture_stops_before_job_publication(self):
        with self.environment() as (context,capture,send,reader,thread):
            self.arm()
            def changed(*args):
                context['ink_revision']+=1
                return 'frame'
            capture.side_effect=changed
            with self.assertRaisesRegex(ValueError,'changed'):self.s.respond(DOC,PAGE,live=True)
            self.assertEqual(self.s.notebook_jobs,{})
            self.assertEqual(self.s.pend(''),{})
            send.assert_not_called();reader.assert_not_called();thread.assert_not_called()

    def test_fixture_scope_and_existing_work_cannot_be_overridden(self):
        with self.environment(folder='Correspondence'):
            with self.assertRaisesRegex(ValueError,'isolated'):self.arm()
            self.assertIsNone(self.s.notebook_replay)
        with self.environment():
            self.s.pend(PATH,['existing'])
            with self.assertRaisesRegex(ValueError,'pending'):self.arm()
            self.assertEqual(self.s.pend('')[PATH],['existing'])
        with self.environment():
            self.arm();original=copy.deepcopy(self.s.notebook_replay)
            with self.assertRaisesRegex(ValueError,'pending'):self.arm()
            self.assertEqual(self.s.notebook_replay,original)
        with self.environment():
            for body in (dict(doc=DOC,page=PAGE,fixture='../../payload'),
                         dict(doc=DOC,page=PAGE,fixture='integral',response='arbitrary'),
                         dict(doc='x'*36,page=PAGE),dict(doc=DOC,page=PAGE,fixture=True)):
                with self.assertRaises(ValueError):self.s.arm_notebook_test(body)
            self.assertIsNone(self.s.notebook_replay)

    def test_legacy_replay_arm_remains_available_without_fixture(self):
        with self.environment():
            self.assertEqual(self.s.arm_notebook_test(dict(doc=DOC,page=PAGE)),dict(armed=True,expires_in=30))
            self.assertNotIn('fixture',self.s.notebook_replay)


if __name__=='__main__':unittest.main()
