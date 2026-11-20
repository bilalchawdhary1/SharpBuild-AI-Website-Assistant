"""Deterministic lead qualification: no model call, no database, no stored personal data.

Reads ONLY the visitor's own messages (never assistant replies, which contain SharpBuild's
own email address) and reports which qualification signals are present:

    need      the visitor described something they want built
    budget    the visitor stated an amount ("$5k", "budget is 5000"), not just asked about cost
    timeline  the visitor gave timing ("ASAP", "in 3 months", "by March")
    contact   the visitor shared an email address or phone number

Only booleans leave this module: the email address / phone number themselves are never
returned or logged. Collecting and storing them (with consent) is a later step.
"""
import re
from dataclasses import dataclass
from typing import Iterable, Literal

from app.services.intent import FIRST_PERSON_NEED, HIRE, PROJECT_TOPIC

Score = Literal["hot", "warm", "cold"]
SALES_INTENTS = {"pricing", "project_request"}

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{7,}\d(?![\w])")

_CURRENCY = r"(?:\$|usd|rs\.?|pkr|eur|\u20ac|\u00a3|gbp)"
_AMOUNT = r"\d[\d,]*(?:\.\d+)?\s*(?:k|m|million|thousand)?"
BUDGET = re.compile(
    rf"(?:{_CURRENCY}\s*{_AMOUNT}\b)"
    rf"|(?:\b{_AMOUNT}\s*(?:usd|dollars?|pkr|rupees?|eur|euros?|gbp|pounds?)\b)"
    r"|(?:\bbudget\b[^\d\n]{0,25}\d)",
    re.I,
)

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
TIMELINE = re.compile(
    r"\b(?:asap|urgent(?:ly)?|immediately|right\s+away"
    r"|(?:this|next)\s+(?:week|month|quarter|year)"
    r"|(?:within|in)\s+(?:the\s+next\s+)?\d+\s*(?:-\s*\d+\s*)?(?:days?|weeks?|months?)"
    rf"|by\s+(?:the\s+)?(?:end\s+of\s+)?(?:q[1-4]|{_MONTH}|next\s+\w+|\d{{4}})"
    r"|(?:launch|go[- ]live|deadline)\s+(?:in|by|on|date))\b",
    re.I,
)

# "quote for a website", "estimate for our app": a project mentioned while asking for a price.
PRICE_FOR_PROJECT = re.compile(
    r"\b(?:quote|estimate|price|pricing|cost)\s+for\s+(?:a|an|my|our|the)\b", re.I
)

QUESTIONS = {
    "need": "What kind of product are you looking to build?",
    "timeline": "When are you hoping to launch?",
    "budget": "Do you have a budget range in mind?",
    "contact": None,     # asked only after the visitor consents (lead collection step)
}
FIELD_ORDER = ("need", "timeline", "budget", "contact")


@dataclass(frozen=True)
class Lead:
    score: Score
    need: bool
    budget: bool
    timeline: bool
    contact: bool
    next_field: str | None
    next_question: str | None


def visitor_text(message: str, history: Iterable = ()) -> str:
    """The visitor's own words: earlier user turns plus the current message."""
    turns = [t.text for t in history if getattr(t, "role", None) == "user"]
    return "\n".join([*turns, message])


def _has_phone(text: str) -> bool:
    return any(9 <= sum(c.isdigit() for c in m.group()) <= 15 for m in PHONE.finditer(text))


def assess_lead(message: str, history: Iterable = (), intent: str = "information") -> Lead | None:
    """Returns the lead picture, or None when there is no sales signal at all."""
    text = visitor_text(message, history)
    need = bool(
        HIRE.search(text)
        or (FIRST_PERSON_NEED.search(text) and PROJECT_TOPIC.search(text))
        or (PRICE_FOR_PROJECT.search(text) and PROJECT_TOPIC.search(text))
    )
    budget = bool(BUDGET.search(text))
    timeline = bool(TIMELINE.search(text))
    contact = bool(EMAIL.search(text)) or _has_phone(text)

    qualifying = need + budget + timeline
    if intent not in SALES_INTENTS and not qualifying and not contact:
        return None

    if contact and qualifying >= 2:
        score: Score = "hot"
    elif qualifying >= 1 or contact:
        score = "warm"
    else:
        score = "cold"

    present = {"need": need, "budget": budget, "timeline": timeline, "contact": contact}
    next_field = next((f for f in FIELD_ORDER if not present[f]), None)
    return Lead(score, need, budget, timeline, contact, next_field, QUESTIONS.get(next_field))
