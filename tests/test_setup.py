import os
os.environ.setdefault("AI_API_KEY", "local-test-placeholder")
os.environ.setdefault("AI_BASE_URL", "https://example.invalid/v1")
os.environ.setdefault("AI_MODEL_NAME", "local-test-model")

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch
try:
    import httpx
except ImportError:
    import httpx2 as httpx
from openai import AuthenticationError, APITimeoutError, PermissionDeniedError, RateLimitError
from app.main import app
from app.services import ai_service

class SetupTests(unittest.TestCase):
    def test_reply_and_parameters(self):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=" answer "))])
        with patch.object(ai_service.client.chat.completions, "create", return_value=response) as call:
            self.assertEqual(ai_service.get_ai_response(" hello "), "answer")
            self.assertEqual(call.call_args.kwargs["temperature"], 0.3)
            self.assertEqual(call.call_args.kwargs["messages"][1]["content"], "hello")

    def test_blank_does_not_call_gateway(self):
        with patch.object(ai_service.client.chat.completions, "create") as call:
            self.assertTrue(ai_service.get_ai_response("   "))
            call.assert_not_called()

    def test_empty_responses(self):
        for response in [SimpleNamespace(choices=[]), SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None))])]:
            with self.subTest(response=response), patch.object(ai_service.client.chat.completions,"create",return_value=response):
                self.assertTrue(ai_service.get_ai_response("hello"))

    def test_api_errors_are_safe(self):
        request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        errors = [PermissionDeniedError("secret-error-detail", response=httpx.Response(403,request=request),body=None), APITimeoutError(request=request),
            AuthenticationError("secret-error-detail", response=httpx.Response(401,request=request),body=None),
            RateLimitError("secret-error-detail",response=httpx.Response(429,request=request),body=None)]
        for error in errors:
            with self.subTest(error=type(error).__name__), patch.object(ai_service.client.chat.completions,"create",side_effect=error):
                reply=ai_service.get_ai_response("hello")
                self.assertTrue(reply)
                self.assertNotIn("secret-error-detail",reply)

class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test")
    async def asyncTearDown(self):
        await self.client.aclose()
    async def test_health(self):
        result=await self.client.get("/")
        self.assertEqual(result.json(),{"status":"ok"})
    async def test_chat(self):
        with patch("app.api.routes.get_ai_response",return_value="test reply"):
            result=await self.client.post("/api/chat",json={"message":"hello"})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json(),{"reply":"test reply"})
    async def test_invalid_messages(self):
        with patch("app.api.routes.get_ai_response") as call:
            for data in [{},{"message":""},{"message":"   "},{"message":"a"*5001}]:
                result=await self.client.post("/api/chat",json=data)
                self.assertEqual(result.status_code,422)
            call.assert_not_called()
    async def test_cors(self):
        result=await self.client.options("/api/chat",headers={"Origin":"https://example.com","Access-Control-Request-Method":"POST"})
        self.assertEqual(result.headers.get("access-control-allow-origin"),"*")

if __name__ == "__main__":
    unittest.main()
