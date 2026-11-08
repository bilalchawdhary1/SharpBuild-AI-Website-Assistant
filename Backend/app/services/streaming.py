"""Cleans the model's text while it streams to the browser.

The model writes citation markers like "[1]". The chat window shows sources as links under
the answer instead, so the markers are removed from the visible text. The text arrives in
arbitrary pieces ("[", "1", "]" can come separately), so removal needs a small state machine.
"""
import re
from typing import Iterable, Iterator

from app.schemas.chat import ChatSource
from app.services.ai_service import NO_ANSWER_MARKER
from app.services.knowledge_service import Hit

_CITATION = re.compile(r"[ \t]*\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\]")
_COULD_STILL_BE_CITATION = re.compile(r"[ \t]*\[[\d\s,]*")        # "[", "[1", "[1, 2" ...


class CitationStripper:
    """Removes [n] markers (and the space before them) from text that arrives in pieces,
    and remembers which source numbers were cited, in order."""

    def __init__(self) -> None:
        self._buf = ""
        self._after_citation = False       # a marker was just removed: a "," before the next marker must go too
        self.cited: list[int] = []

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        out: list[str] = []
        while True:
            if self._after_citation:
                comma = re.match(r"[ \t]*,[ \t]*", self._buf)
                if comma:
                    tail = self._buf[comma.end():]
                    if tail == "":
                        break                                  # cannot tell yet whether another marker follows
                    if tail.startswith("["):
                        self._buf = tail                       # "[1], [2]" -> drop the comma between the markers
                    self._after_citation = False
                elif re.fullmatch(r"[ \t]*", self._buf):
                    break                                      # only spaces so far: a comma might still follow
                else:
                    self._after_citation = False
            i = self._buf.find("[")
            if i == -1:
                # Hold back trailing spaces: they may belong to a marker that starts in the next piece.
                keep = self._buf.rstrip(" \t")
                out.append(keep)
                self._buf = self._buf[len(keep):]
                break
            j = i
            while j > 0 and self._buf[j - 1] in " \t":
                j -= 1
            out.append(self._buf[:j])
            rest = self._buf[j:]
            match = _CITATION.match(rest)
            if match:
                self.cited.extend(int(n) for n in re.split(r"\s*,\s*", match.group(1)))
                self._buf = rest[match.end():]
                self._after_citation = True
                continue
            if _COULD_STILL_BE_CITATION.fullmatch(rest):          # incomplete: wait for more text
                self._buf = rest
                break
            k = rest.index("[")                                   # an ordinary bracket: let it through
            out.append(rest[:k + 1])
            self._buf = rest[k + 1:]
        return "".join(out)

    def finish(self) -> str:
        rest, self._buf = self._buf.rstrip(" \t"), ""
        return rest


class NoAnswerGate:
    """Holds back the first characters until we know whether the model replied [[NO_ANSWER]]
    (nothing may be shown to the visitor in that case)."""

    def __init__(self) -> None:
        self._buf = ""
        self._open = False

    def feed(self, chunk: str) -> tuple[str, bool]:
        """Returns (text that may be shown now, whether the model said NO_ANSWER)."""
        if self._open:
            return chunk, False
        self._buf += chunk
        probe = self._buf.lstrip()
        if NO_ANSWER_MARKER in probe:
            return "", True
        if NO_ANSWER_MARKER.startswith(probe):                    # still could become the marker
            return "", False
        self._open = True
        released, self._buf = self._buf, ""
        return released, False

    def flush(self) -> str:
        released, self._buf = self._buf, ""
        self._open = True
        return released


def sources_from_citations(cited: list[int], hits: list[Hit]) -> list[ChatSource]:
    """One source per page, in the order they were first cited. Invalid numbers are ignored."""
    seen: set[str] = set()
    sources: list[ChatSource] = []
    for n in cited:
        if 1 <= n <= len(hits) and hits[n - 1].url not in seen:
            hit = hits[n - 1]
            seen.add(hit.url)
            sources.append(ChatSource(url=hit.url, title=hit.title, section=hit.section))
    return sources


def stream_events(chunks: Iterable[str], hits: list[Hit]) -> Iterator[dict]:
    """Raw model chunks in; browser events out: {"type": "delta"|"done"|"no_answer", ...}.
    Raises if the model produced no text at all."""
    gate, stripper = NoAnswerGate(), CitationStripper()
    parts: list[str] = []

    def clean(text: str) -> dict | None:
        out = stripper.feed(text)
        if not parts:
            out = out.lstrip()                                    # never start the answer with blank space
        if not out:
            return None
        parts.append(out)
        return {"type": "delta", "text": out}

    for raw in chunks:
        released, no_answer = gate.feed(raw)
        if no_answer:
            yield {"type": "no_answer"}
            return
        if released and (event := clean(released)):
            yield event
    held = gate.flush()
    if held and (event := clean(held)):
        yield event
    tail = stripper.finish()
    if tail:
        parts.append(tail)
        yield {"type": "delta", "text": tail}

    answer = "".join(parts).strip()
    if not answer:
        raise RuntimeError("the model returned no text")
    sources = sources_from_citations(stripper.cited, hits)
    yield {"type": "done", "answer": answer, "sources": [s.model_dump() for s in sources], "fallback": False}
