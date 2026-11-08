import os
os.environ.setdefault('AI_API_KEY','test-placeholder')
os.environ.setdefault('AI_BASE_URL','https://example.invalid/v1')
os.environ.setdefault('AI_MODEL_NAME','test-model')
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from app.services import ai_service as service


class ToolTests(unittest.TestCase):
    def test_writing_tool_removed(self):
        self.assertNotIn('create_signup_draft',[x['function']['name'] for x in service.tools])

    def test_unexpected_tool_has_no_side_effect(self):
        response=NS(choices=[NS(message=NS(content=None,tool_calls=[NS(function=NS(name='create_signup_draft',arguments='{}'))]))])
        with patch.object(service.client.chat.completions,'create',return_value=response):
            self.assertTrue(service.get_ai_response('بله بساز'))

    def test_temperature_optional(self):
        with patch.object(service.settings,'AI_TEMPERATURE',None),patch.object(service.client.chat.completions,'create',return_value=NS(choices=[])) as call:
            service.get_ai_response('hello')
            self.assertNotIn('temperature',call.call_args.kwargs)
