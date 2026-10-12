"""The optional provider only gets explicitly allowed private context."""
import json
import os
import unittest
from unittest import mock
import guru_provider

class ProviderTests(unittest.TestCase):
    def test_no_request_when_disabled_and_bounded_context_when_enabled(self):
        with mock.patch.dict(os.environ,{'DHASHU_GURU_AI_ENABLED':'0'}), mock.patch('guru_provider.urlopen') as call:
            self.assertIsNone(guru_provider.reply('hello','values',[],[],{}));call.assert_not_called()
        with mock.patch.dict(os.environ,{'DHASHU_GURU_AI_ENABLED':'1','OPENAI_API_KEY':'test-only','DHASHU_GURU_MODEL':'configured-model'}), mock.patch('guru_provider.urlopen') as call:
            call.return_value.__enter__.return_value.read.return_value=json.dumps({'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'What would feel fair to you?'}]}]}).encode()
            answer=guru_provider.reply('Hello','expenses',[{'role':'user','text':str(i)} for i in range(40)],[{'id':'private-id','text':'Quiet places'}],{'topic_stage':'relationship','headline':'Your next step','partner_secret':'NEVER_SEND'})
            self.assertEqual(answer,'What would feel fair to you?')
            payload=json.loads(call.call_args.args[0].data)
            self.assertFalse(payload['store']);self.assertNotIn('tools',payload)
            inputs=json.loads(payload['input']);self.assertEqual(len(inputs['private_history']),20)
            self.assertEqual(inputs['user_saved_memories'],['Quiet places']);self.assertNotIn('NEVER_SEND',payload['input'])

    def test_provider_failure_returns_fallback_without_error_body(self):
        with mock.patch.dict(os.environ,{'DHASHU_GURU_AI_ENABLED':'1','OPENAI_API_KEY':'test-only','DHASHU_GURU_MODEL':'configured-model'}),mock.patch('guru_provider.urlopen',side_effect=OSError('sensitive transport text')):
            self.assertIsNone(guru_provider.reply('hello','values',[],[],{}))
