"""Canned replies for greetings, thanks and personal chatter.

Why: these messages have nothing to retrieve. Without this, a short message like
"my name is Bilal" can slip past the similarity threshold and get an answer built
around an unrelated page (it once cited a client case study). A fixed reply is
cheaper (no embedding or LLM call), deterministic and safe.

Only SHORT, whole-message patterns match, so "Hello, do you build Shopify stores?"
or "My name is Bilal and I need a Shopify store" still go through the normal pipeline.
"""
import re

CONTACT_EMAIL = "hello@sharpbuild.io"

_END = r"\s*[!.?,]*\s*$"
_NAME = r"[A-Za-z][\w'\-]*(?:\s+[A-Za-z][\w'\-]*){0,2}"        # one to three words

RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:what(?:'s|\s+is)\s+my\s+name|tell\s+me\s+my\s+name|do\s+you\s+(?:remember|know)\s+(?:me|my\s+name)|who\s+am\s+i)\b", re.I),
     "I don't keep personal details between messages, so I can't recall your name. "
     "I can answer questions about SharpBuild's services, process and work."),
    (re.compile(rf"^\s*(?:my\s+name\s+is|call\s+me)\s+{_NAME}{_END}", re.I),
     "Nice to meet you! I don't store personal details, so please don't share any. "
     "What would you like to know about SharpBuild?"),
    (re.compile(rf"^\s*(?:hi|hello|hey|hiya|howdy|yo|good\s+(?:morning|afternoon|evening)|greetings)(?:\s+(?:there|team|everyone|sharpbuild))?{_END}", re.I),
     "Hello! I can answer questions about SharpBuild's services, process and work. What would you like to know?"),
    (re.compile(rf"^\s*(?:thanks|thank\s+you|thx|ty|cheers|much\s+appreciated)(?:\s+(?:a\s+lot|so\s+much|very\s+much))?{_END}", re.I),
     f"You're welcome! Ask me anything else about SharpBuild, or email {CONTACT_EMAIL} to reach the team."),
    (re.compile(rf"^\s*(?:bye|good\s*bye|see\s+you|see\s+ya|cya|that's\s+all){_END}", re.I),
     f"Thanks for stopping by! If you need the team, email {CONTACT_EMAIL}."),
]


def smalltalk_reply(message: str) -> str | None:
    text = message.replace("\u2019", "'")          # curly apostrophe -> straight
    for pattern, reply in RULES:
        if pattern.search(text):
            return reply
    return None
