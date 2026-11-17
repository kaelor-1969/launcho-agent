import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.ai_service import generate_turn


class CustomerGuidanceTests(unittest.TestCase):
    def test_common_questions_answer_directly_without_the_model(self):
        pricing = json.loads(Path('content/launcho-mock.json').read_text(encoding='utf-8'))['pricing']
        cases = [
            ('هزینهٔ ساخت سایت و اشتراک چقدر است و اقساط دارد؟',
             ['سایت ۵٬۰۰۰٬۰۰۰ تومان', 'اشتراک:', '۴ قسط ۱٬۲۵۰٬۰۰۰ تومانی']),
            ('برای اطلاع از تعرفه‌های لانچو از کجا اقدام کنم؟',
             ['سایت ۵٬۰۰۰٬۰۰۰', 'فروشگاه ۱۵٬۰۰۰٬۰۰۰']),
            ('لانچو چه امکاناتی دارد؟', ['صفحه‌ساز', 'مدیریت سفارش']),
            ('قالب‌های لانچو را از کجا ببینم و چطور انتخاب کنم؟',
             ['پیش‌نمایش', 'https://launcho.ir/#templates']),
        ]
        with patch('app.services.ai_service.client.chat.completions.create',
                   side_effect=AssertionError('unexpected model call')):
            for question, expected in cases:
                with self.subTest(question=question):
                    reply, update = generate_turn(question, pricing=pricing)
                    for phrase in expected:
                        self.assertIn(phrase, reply)
                    self.assertEqual(update, {})
                    if question.startswith('قالب'):
                        self.assertNotIn('کیف و کفش', reply)


    def test_open_question_gets_reviewed_knowledge_and_conversation_context(self):
        from types import SimpleNamespace

        history = [{'role': 'user', 'content': 'من یک آتلیه دارم و فقط سایت معرفی می‌خواهم.'}]
        answer = 'برای معرفی آتلیه، سایت‌ساز لانچو مناسب است.'
        response = SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content=answer, tool_calls=None))
        ])
        with patch('app.services.ai_service.client.chat.completions.create',
                   return_value=response) as model:
            reply, update = generate_turn('برای کار من چه انتخابی بهتره؟', history=history)
        self.assertEqual((reply, update), (answer, {}))
        request = model.call_args.kwargs
        messages = request['messages']
        self.assertEqual(messages[-2], history[0])
        self.assertIn('میزبانی', messages[0]['content'])
        self.assertIn('مالکیت دامنه', messages[0]['content'])
        self.assertNotIn('tools', request)

