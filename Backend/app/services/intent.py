"""Deterministic intent detection for routing chat messages.

This intentionally runs without a model call. It covers the common categories
that can be handled safely before retrieval, and leaves ambiguous questions as
general information requests.
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
    r"bye|goodbye|see you|cya|that(?:'|’)s all)"
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

PROJECT_REQUEST = re.compile(
    r"\b(?:build|develop|create|make|need|want|looking for|start|hire|"
    r"mvp|product|startup|project|app|website|store|platform|system)\b",
    re.I,
)

PRICING = re.compile(
    r"\b(?:price|prices|pricing|cost|costs|budget|quote|quotes|rate|rates|hourly)\b",
    re.I,
)


def detect_intent(message: str) -> Intent:
    text = message.strip()
    if not text:
        return "information"
    if GREETING_OR_CLOSE.search(text):
        return "smalltalk"
    if HUMAN_HANDOFF.search(text) and HUMAN_HANDOFF_ACTION.search(text):
        return "human_handoff"
    if PRICING.search(text):
        return "pricing"
    if PROJECT_REQUEST.search(text):
        return "project_request"
    return "information"
