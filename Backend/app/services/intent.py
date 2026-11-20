"""Deterministic intent detection for routing chat messages.

This intentionally runs without a model call. It covers the common categories
that can be handled safely before retrieval, and leaves ambiguous questions as
general information requests.

Rules of thumb (see tests/test_intent.py):
  - "project_request" needs the visitor to state their own need ("I want to build...",
    "we need..."). Questions about SharpBuild ("Do you make apps?") are "information".
  - "pricing" matches money words only; a bare "rate" is not one ("rate of delivery").
"""
import re
from typing import Literal

Intent = Literal[
    "smalltalk",
    "human_handoff",
    "project_request",
    "pricing",
    "information",
]


GREETING_OR_CLOSE = re.compile(
    r"^\s*(?:hi|hello|hey(?: there)?|thanks?|thank you|thx|cheers|"
    r"bye|goodbye|see you|cya|that(?:'|\u2019)s all)"
    r"(?:\s+(?:there|team|everyone|sharpbuild))?[!.?,]*\s*$",
    re.I,
)

HUMAN_HANDOFF = re.compile(
    r"\b(?:human|person|agent|specialist|support|representative|team)\b",
    re.I,
)

HUMAN_HANDOFF_ACTION = re.compile(
    r"\b(?:talk|speak|chat|contact|reach|get in touch|hand(?:\s+)?off)\b",
    re.I,
)

# Asking for a way to reach the company, without naming a "human/team" word.
CONTACT_REQUEST = re.compile(
    r"\b(?:(?:contact|reach|email|call|phone|message)\s+(?:you|us|sharpbuild|someone|somebody)"
    r"|get\s+in\s+touch"
    r"|(?:talk|speak)\s+(?:to|with)\s+(?:someone|somebody|anyone)"
    r"|real\s+person|live\s+agent"
    r"|(?:your|the)\s+(?:contact|email|phone)\b)",
    re.I,
)

# The visitor states their own need ("I need", "we want", "I'd like", "I'm looking for")...
FIRST_PERSON_NEED = re.compile(
    r"\b(?:i|we)(?:'d\s+like|\s+would\s+like|\s+need|\s+want|\s+plan\s+to"
    r"|(?:'m|\s+am|'re|\s+are)\s+(?:looking|planning|trying))\b"
    r"|\blooking\s+for\s+(?:a|an)\s+(?:\w+\s+){0,2}(?:developer|agency|team|partner|studio)\b",
    re.I,
)

# ...about something SharpBuild builds.
PROJECT_TOPIC = re.compile(
    r"\b(?:build|built|develop|developed|create|made|make|mvp|product|startup|project|"
    r"app|apps|website|store|platform|system|software|saas|e-?commerce|shopify|portal|"
    r"dashboard|redesign)\b",
    re.I,
)
HIRE = re.compile(r"\b(?:hire|start\s+a\s+project\s+with)\s+(?:you|sharpbuild|your)\b", re.I)

PRICING = re.compile(
    r"\b(?:price|prices|pricing|cost(?!-effective)|costs|budget|quote|quotes|estimate|"
    r"charge|charges|fee|fees|hourly|day\s+rate|(?:your|an?)\s+rates?|rate\s+card)\b",
    re.I,
)


def detect_intent(message: str) -> Intent:
    text = message.replace("\u2019", "'").strip()      # curly apostrophe -> straight
    if not text:
        return "information"
    if GREETING_OR_CLOSE.search(text):
        return "smalltalk"
    if (HUMAN_HANDOFF.search(text) and HUMAN_HANDOFF_ACTION.search(text)) or CONTACT_REQUEST.search(text):
        return "human_handoff"
    if PRICING.search(text):
        return "pricing"
    if HIRE.search(text) or (FIRST_PERSON_NEED.search(text) and PROJECT_TOPIC.search(text)):
        return "project_request"
    return "information"
