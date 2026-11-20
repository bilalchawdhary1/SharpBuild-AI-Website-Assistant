import json
import unittest

from scripts.log_report import percentile, render, summarize

TEXT = [
    "2026-11-20 10:00:00,001 INFO sharpbuild.chat [a1b2c3d4]: chat intent=information question_chars=40",
    "2026-11-20 10:00:01,001 INFO sharpbuild.chat [a1b2c3d4]: chat outcome=answered top_similarity=0.812 question_chars=40 retrieve_ms=120 answer_ms=900 ms=1050 first_token_ms=400",
    "2026-11-20 10:00:02,001 INFO sharpbuild.chat [b1b2c3d4]: chat outcome=answered top_similarity=0.700 question_chars=20 retrieve_ms=100 answer_ms=1800 ms=2000 first_token_ms=800",
    "2026-11-20 10:00:03,001 INFO sharpbuild.chat [c1b2c3d4]: chat outcome=below_threshold top_similarity=0.300 question_chars=15 retrieve_ms=90 answer_ms=0 ms=95",
    "2026-11-20 10:00:04,001 INFO sharpbuild.chat [d1b2c3d4]: chat outcome=model_no_answer top_similarity=0.600 question_chars=30 retrieve_ms=90 answer_ms=700 ms=800",
    "2026-11-20 10:00:05,001 INFO sharpbuild.chat [e1b2c3d4]: chat outcome=smalltalk question_chars=2",
    "2026-11-20 10:00:06,001 INFO sharpbuild.chat [f1b2c3d4]: chat outcome=error top_similarity=0.000 question_chars=10 retrieve_ms=0 answer_ms=0 ms=5",
    "2026-11-20 10:00:07,001 WARNING sharpbuild.chat [a1b2c3d4]: model gemini-2.5-flash failed after 800 ms (503); trying gemini-2.5-flash-lite",
    "2026-11-20 10:00:08,001 INFO sharpbuild.request [a1b2c3d4]: request method=POST path=/chat/stream status=200 ms=1100",
    "2026-11-20 10:00:09,001 INFO sharpbuild.request [a1b2c3d4]: request method=POST path=/chat/stream status=429 ms=3",
    "2026-11-20 10:00:10,001 ERROR sharpbuild.request [a1b2c3d4]: request method=POST path=/lead status=503 ms=40",
    "2026-11-20 10:00:11,001 INFO sharpbuild.lead [a1b2c3d4]: lead saved id=1 score=hot",
    "2026-11-20 10:00:12,001 INFO sharpbuild.lead [a1b2c3d4]: lead duplicate ignored",
    "2026-11-20 10:00:13,001 INFO sharpbuild.notify [a1b2c3d4]: lead notify id=1 webhook=ok email=failed",
    "2026-11-20 10:00:14,001 INFO sharpbuild.notify [a1b2c3d4]: lead notify id=2 webhook=ok",
    "some unrelated line",
]


class SummaryTest(unittest.TestCase):
    def setUp(self):
        self.s = summarize(TEXT)

    def test_outcomes_and_rates(self):
        self.assertEqual(self.s["chats"], 6)
        self.assertEqual(self.s["outcomes"], {"answered": 2, "below_threshold": 1, "model_no_answer": 1, "smalltalk": 1, "error": 1})
        self.assertAlmostEqual(self.s["unanswered_rate"], 2 / 6)
        self.assertAlmostEqual(self.s["error_rate"], 1 / 6)
        self.assertEqual(self.s["intents"], {"information": 1})

    def test_latency_only_counts_answered_requests(self):
        self.assertEqual(self.s["latency_ms"], {"p50": 1050, "p95": 2000})
        self.assertEqual(self.s["first_token_ms"], {"p50": 400, "p95": 800})

    def test_http_models_and_leads(self):
        self.assertEqual(self.s["http"], {"2xx": 1, "4xx": 1, "429": 1, "5xx": 1})
        self.assertEqual(self.s["model_failures"], {"gemini-2.5-flash": 1})
        self.assertEqual(self.s["leads"], {"saved": 1, "duplicate": 1, "notify_failed": 1, "notify_ok": 1})
        self.assertEqual(self.s["slowest_endpoints"][0]["endpoint"], "POST /chat/stream")

    def test_json_lines_give_the_same_result(self):
        as_json = [json.dumps({"ts": "x", "level": "INFO", "logger": "l", "request_id": "r", "message": line.split(": ", 1)[1].split("]: ", 1)[-1]})
                   if "]: " in line else line for line in TEXT]
        self.assertEqual(summarize(as_json)["outcomes"], self.s["outcomes"])
        self.assertEqual(summarize(as_json)["leads"], self.s["leads"])

    def test_empty_input_and_render(self):
        empty = summarize([])
        self.assertEqual((empty["chats"], empty["unanswered_rate"]), (0, 0.0))
        self.assertIn("Chat requests: 0", render(empty))
        text = render(self.s)
        self.assertIn("No grounded answer: 33.3%", text)
        self.assertIn("answered", text)

    def test_percentile(self):
        self.assertIsNone(percentile([], 95))
        self.assertEqual(percentile([5], 95), 5)
        self.assertEqual(percentile(list(range(1, 101)), 95), 95)


if __name__ == "__main__":
    unittest.main()
