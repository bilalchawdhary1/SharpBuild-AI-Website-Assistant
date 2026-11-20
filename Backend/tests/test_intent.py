"""Labeled messages for services/intent.py. Runs under pytest or `python -m unittest`."""
import unittest

from app.services.intent import detect_intent

CASES = [
    # smalltalk
    ("hi", "smalltalk"),
    ("Hello team!", "smalltalk"),
    ("thanks!", "smalltalk"),
    ("that\u2019s all", "smalltalk"),
    # human_handoff
    ("I want to talk to a human", "human_handoff"),
    ("can I speak with your team?", "human_handoff"),
    ("how can I contact you?", "human_handoff"),
    ("What's your contact email?", "human_handoff"),
    ("I'd like to get in touch with someone", "human_handoff"),
    ("connect me to a real person", "human_handoff"),
    # pricing
    ("How much does an MVP cost?", "pricing"),
    ("what is your hourly rate", "pricing"),
    ("What are your rates?", "pricing"),
    ("Can I get a quote for a website?", "pricing"),
    ("I want to build an app, what's the budget needed?", "pricing"),
    ("how much do you charge", "pricing"),
    # project_request
    ("I need a Shopify store built", "project_request"),
    ("I want to build a fintech app", "project_request"),
    ("We're looking for a development agency for our startup", "project_request"),
    ("I'd like to redesign our website", "project_request"),
    ("we plan to launch a SaaS platform", "project_request"),
    ("I want to hire you to build an MVP", "project_request"),
    # information (must NOT be routed as sales or handoff)
    ("What services does SharpBuild offer?", "information"),
    ("What is your website development process?", "information"),
    ("How long does a project take?", "information"),
    ("Do you make mobile apps?", "information"),
    ("What products have you built?", "information"),
    ("What technologies do you use for apps?", "information"),
    ("Do you provide support after launch?", "information"),
    ("Who is on your support team?", "information"),
    ("Tell me about your team", "information"),
    ("Where are you located?", "information"),
    ("What's the rate of your on-time delivery?", "information"),
    ("Is your process cost-effective?", "information"),
    ("Can you build Shopify stores?", "information"),
    ("   ", "information"),
]


class DetectIntentTest(unittest.TestCase):
    def test_labeled_messages(self):
        for text, expected in CASES:
            with self.subTest(text=text):
                self.assertEqual(detect_intent(text), expected)

    def test_accuracy_floor(self):
        correct = sum(detect_intent(t) == e for t, e in CASES)
        self.assertGreaterEqual(correct / len(CASES), 0.95)


if __name__ == "__main__":
    unittest.main()
