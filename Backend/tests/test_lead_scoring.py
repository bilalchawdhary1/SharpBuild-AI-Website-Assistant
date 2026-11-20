"""Deterministic lead scoring (services/lead_scoring.py). Pure Python; runs under pytest or unittest."""
import unittest
from types import SimpleNamespace as Turn

from app.services.lead_scoring import assess_lead


def user(text):
    return Turn(role="user", text=text)


def assistant(text):
    return Turn(role="assistant", text=text)


class SignalTest(unittest.TestCase):
    def signals(self, message, history=(), intent="project_request"):
        lead = assess_lead(message, history, intent)
        return None if lead is None else (lead.need, lead.budget, lead.timeline, lead.contact)

    def test_need(self):
        self.assertEqual(self.signals("I need a Shopify store built")[0], True)
        self.assertEqual(self.signals("Can I get a quote for a website?", intent="pricing")[0], True)
        self.assertEqual(self.signals("How much does an MVP cost?", intent="pricing")[0], False)

    def test_budget_needs_a_stated_amount_not_a_question(self):
        for text in ["my budget is $5k", "budget around 5000", "we have 20,000 USD", "PKR 500000", "\u00a38k"]:
            with self.subTest(text=text):
                self.assertTrue(self.signals(text)[1])
        for text in ["How much does an MVP cost?", "what is your budget policy", "we are 5 people"]:
            with self.subTest(text=text):
                self.assertFalse(self.signals(text, intent="pricing")[1])

    def test_timeline(self):
        for text in ["we need it ASAP", "launch in 3 months", "within 6-8 weeks", "by March", "by end of Q3",
                     "next quarter", "go live by 2027"]:
            with self.subTest(text=text):
                self.assertTrue(self.signals(text)[2])
        for text in ["How long does a project take?", "I need an app", "what is your process?"]:
            with self.subTest(text=text):
                self.assertFalse(self.signals(text)[2])

    def test_contact_email_and_phone(self):
        self.assertTrue(self.signals("reach me at ali.khan+x@example.co.uk")[3])
        self.assertTrue(self.signals("call 0300-1234567")[3])
        self.assertTrue(self.signals("my number is +92 300 1234567")[3])
        self.assertTrue(self.signals("(415) 555-0132")[3])

    def test_dates_and_amounts_are_not_phone_numbers(self):
        for text in ["deadline 2026-11-19", "budget $1,000,000", "we are building since 2019 with 45 staff"]:
            with self.subTest(text=text):
                self.assertFalse(self.signals(text)[3])


class HistoryTest(unittest.TestCase):
    def test_assistant_turns_are_ignored(self):
        history = [user("hi"), assistant("Email hello@sharpbuild.io or call +1 415 555 0132 in 3 months, budget $5k")]
        lead = assess_lead("what services do you offer?", history, "information")
        self.assertIsNone(lead)

    def test_signals_accumulate_across_user_turns(self):
        history = [user("I want to build a fintech app"), assistant("Great! When do you plan to launch?"),
                   user("in 4 months")]
        lead = assess_lead("what is your process?", history, "information")
        self.assertIsNotNone(lead)                       # follow-up turn is not a sales intent, history is
        self.assertTrue(lead.need and lead.timeline)
        self.assertFalse(lead.budget or lead.contact)


class ScoreTest(unittest.TestCase):
    def test_none_without_sales_signal(self):
        self.assertIsNone(assess_lead("What services does SharpBuild offer?", [], "information"))
        self.assertIsNone(assess_lead("Where are you located?", [], "information"))

    def test_cold_pricing_question_only(self):
        lead = assess_lead("How much does an MVP cost?", [], "pricing")
        self.assertEqual(lead.score, "cold")
        self.assertEqual(lead.next_field, "need")

    def test_warm_with_need_only(self):
        self.assertEqual(assess_lead("I need a Shopify store built", [], "project_request").score, "warm")

    def test_warm_with_two_signals_but_no_contact(self):
        lead = assess_lead("I want to build an app, budget is $10k, launch in 3 months", [], "project_request")
        self.assertEqual(lead.score, "warm")
        self.assertEqual(lead.next_field, "contact")
        self.assertIsNone(lead.next_question)            # contact is asked only after consent

    def test_hot_with_contact_and_two_signals(self):
        lead = assess_lead("I need an app by March, email me at a@b.com", [], "project_request")
        self.assertEqual(lead.score, "hot")

    def test_contact_only_is_warm(self):
        self.assertEqual(assess_lead("write to me at a@b.com", [], "information").score, "warm")

    def test_next_question_order_need_timeline_budget(self):
        lead = assess_lead("I need an app", [], "project_request")
        self.assertEqual(lead.next_field, "timeline")
        self.assertEqual(lead.next_question, "When are you hoping to launch?")
        lead = assess_lead("I need an app in 3 months", [], "project_request")
        self.assertEqual(lead.next_field, "budget")

    def test_lead_carries_no_personal_values(self):
        lead = assess_lead("I need an app, mail me at secret.person@example.com", [], "project_request")
        blob = repr(lead)
        self.assertNotIn("secret.person", blob)


if __name__ == "__main__":
    unittest.main()
