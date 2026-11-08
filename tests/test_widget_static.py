import os
os.environ.setdefault("AI_API_KEY", "local-test-placeholder")
os.environ.setdefault("AI_BASE_URL", "https://example.invalid/v1")
os.environ.setdefault("AI_MODEL_NAME", "local-test-model")

import tempfile
import unittest
from unittest.mock import patch
import httpx
from app.main import app


class WidgetStaticTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_widget_assets_and_content_types(self):
        for filename, content_type in [
            ("widget.html", "text/html"), ("demo.html", "text/html"), ("draft-preview.html", "text/html"),
            ("widget.css", "text/css"), ("loader.js", "javascript"),
            ("widget.js", "javascript"), ("api.js", "javascript"),
            ("workflow.js", "javascript"), ("workflow-api.js", "javascript"),
            ("workflow-demo.js", "javascript"), ("assets/template-almas.webp", "image/webp"),
            ("assets/Vazirmatn.woff2", "font/woff2"), ("assets/OFL.txt", "text/plain"),
        ]:
            with self.subTest(filename=filename):
                result = await self.client.get("/widget/" + filename)
                self.assertEqual(result.status_code, 200)
                self.assertIn(content_type, result.headers["content-type"])
                self.assertTrue(result.content)
        font = await self.client.get("/widget/assets/Vazirmatn.woff2")
        self.assertEqual(font.content[:4], b"wOF2")

    async def test_static_is_independent_of_working_directory(self):
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                response = await self.client.get("/widget/widget.html")
                self.assertEqual(response.status_code, 200)
            finally:
                os.chdir(previous)

    async def test_health_and_chat_preserved(self):
        self.assertEqual((await self.client.get("/")).json()["status"], "ok")
        with patch("app.api.routes.get_ai_response", return_value="پاسخ آزمایشی") as model:
            response = await self.client.post("/api/chat", json={"message": "  سلام  "})
            self.assertEqual(response.json(), {"reply": "پاسخ آزمایشی"})
            model.assert_called_once_with("سلام")

    async def test_unknown_files_and_traversal_are_not_exposed(self):
        for path in ["/widget/not-found.js", "/widget/%2e%2e/.env", "/widget/%2e%2e/app/main.py"]:
            self.assertEqual((await self.client.get(path)).status_code, 404)

    async def test_unexpected_chat_failure_is_safe(self):
        with patch("app.api.routes.get_ai_response", side_effect=RuntimeError("private-detail")):
            response = await self.client.post("/api/chat", json={"message": "hello"})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private-detail", response.text)

    async def test_legacy_static_mount_is_preserved(self):
        response = await self.client.get("/static/.gitkeep")
        self.assertEqual(response.status_code, 200)

    async def test_length_is_checked_after_trimming(self):
        with patch("app.api.routes.get_ai_response", return_value="ok") as model:
            response = await self.client.post("/api/chat", json={"message": "  " + "a" * 5000 + "  "})
            self.assertEqual(response.status_code, 200)
            model.assert_called_once_with("a" * 5000)
        with patch("app.api.routes.get_ai_response") as model:
            for value in [None, 123, " " * 5001, "a" * 5001]:
                self.assertEqual((await self.client.post("/api/chat", json={"message": value})).status_code, 422)
            model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
