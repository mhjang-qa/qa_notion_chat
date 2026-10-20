import json
import unittest
from unittest.mock import patch

from app.api.routes import ChatRequest
from app.services.answerer import answer_question
from app.services.localization import answer_in_english


class LocalizationTests(unittest.TestCase):
    def test_default_is_korean(self):
        self.assertEqual(ChatRequest(question="hello").language, "ko")
        self.assertIn("안녕하세요", answer_question("hello")["answer"])

    def test_english_greeting_and_guide_need_no_provider(self):
        with patch("app.services.localization.generate_text", side_effect=AssertionError("No translation needed")):
            self.assertIn("Hello", answer_question("hello", language="en")["answer"])
            for question in ("help", "bug report guide", "how do I report a bug?"):
                result = answer_question(question, language="en")
                self.assertIn("lang=en", result["sources"][0]["url"])
                self.assertNotRegex(result["answer"], "[가-힣]")

    def test_query_translation_and_source_integrity(self):
        original = {"answer": "결함 3건", "mode": "extractive", "origin": "NOTION",
                    "sources": [{"title": "원문", "url": "https://notion.so/source", "id": "abc"}],
                    "items": [{"text": "결함 내용", "source": {"title": "원문", "url": "https://notion.so/item"}}]}
        def answerer(query, **kwargs):
            self.assertEqual(query, "5.20.0 결함 현황")
            self.assertFalse(kwargs["allow_llm"])
            return original
        with patch("app.services.localization.generate_text", side_effect=[
            "5.20.0 결함 현황", json.dumps(["3 bugs", "Source", "Bug details", "Source"])
        ]):
            result = answer_in_english("5.20.0 bug status", False, answerer)
        self.assertEqual(result["answer"], "3 bugs")
        self.assertEqual(result["sources"][0]["url"], original["sources"][0]["url"])
        self.assertEqual(result["sources"][0]["id"], "abc")
        self.assertEqual(result["items"][0]["source"]["url"], "https://notion.so/item")
        self.assertEqual(original["answer"], "결함 3건")

    def test_llm_confirmation_keeps_original_question(self):
        with patch("app.services.localization.generate_text", return_value="한패스 송금 질문"):
            result = answer_in_english("Hanpass remittance question", False,
                lambda *args, **kwargs: {"mode": "llm_offer", "answer": "동의", "pending_question": "번역된 질문", "sources": []})
        self.assertEqual(result["pending_question"], "Hanpass remittance question")
        self.assertIn("yes", result["answer"])

    def test_translation_failure_is_english_and_does_not_answer(self):
        with patch("app.services.localization.generate_text", side_effect=RuntimeError("offline")):
            result = answer_in_english("Find payment tests", False,
                lambda *args, **kwargs: self.fail("Search must not run with an invalid query"))
        self.assertEqual(result["mode"], "translation_error")
        self.assertNotRegex(result["answer"], "[가-힣]")

    def test_invalid_translation_shape_is_not_published(self):
        with patch("app.services.localization.generate_text", side_effect=["테스트", '["only one"]']):
            result = answer_in_english("Find tests", False, lambda *args, **kwargs: {
                "answer": "결과", "mode": "extractive", "sources": [{"title": "원문", "url": "https://notion.so/test"}]})
        self.assertEqual(result["mode"], "translation_error")

    def test_status_question_is_not_a_guide_or_report_command(self):
        from app.services.localization import _query_in_korean
        with patch("app.services.localization.generate_text", return_value="현재 결함 개수") as translate:
            self.assertEqual(_query_in_korean("How many bugs are open?"), "현재 결함 개수")
            self.assertTrue(translate.called)
        with patch("app.services.localization.generate_text", return_value="결함 제보 현황") as translate:
            self.assertEqual(_query_in_korean("bug report status"), "결함 제보 현황")
            self.assertTrue(translate.called)

    def test_invalid_language_is_rejected(self):
        with self.assertRaises(ValueError):
            ChatRequest(question="hello", language="fr")


if __name__ == "__main__":
    unittest.main()
