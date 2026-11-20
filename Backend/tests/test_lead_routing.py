"""Lead info flowing through chat_service (pytest; needs the project's dependencies)."""
from app.schemas.chat import ChatTurn
from app.services import chat_service
from app.services.chat_service import Generate, Ready, done_event, prepare, stream_answer
from app.services.knowledge_service import Hit

HIT = Hit(chunk_id="c1", url="https://sharpbuild.io/services", title="Services", section="",
          page_type="services", content="SharpBuild builds web and mobile apps.", similarity=0.9)


def _prepare(monkeypatch, message, history=None, hits=(HIT,)):
    monkeypatch.setattr(chat_service, "retrieve", lambda *a, **k: list(hits))
    return prepare(None, message, lambda t: [0.0], min_similarity=0.58, k=4, history=history or [])


def test_plain_question_has_no_lead(monkeypatch):
    prepared = _prepare(monkeypatch, "What services does SharpBuild offer?")
    assert isinstance(prepared, Generate) and prepared.lead is None


def test_hot_lead_from_message_and_history(monkeypatch):
    history = [ChatTurn(role="user", text="I need a fintech app by March"),
               ChatTurn(role="assistant", text="Email hello@sharpbuild.io any time.")]
    prepared = _prepare(monkeypatch, "my budget is $20k, mail me at a@b.com", history)
    assert isinstance(prepared, Generate)
    assert prepared.lead.score == "hot"
    assert prepared.lead.contact and prepared.lead.budget and prepared.lead.timeline


def test_assistant_email_alone_never_makes_a_lead(monkeypatch):
    history = [ChatTurn(role="assistant", text="Email hello@sharpbuild.io")]
    assert _prepare(monkeypatch, "What is your process?", history).lead is None


def test_below_threshold_sales_message_still_carries_lead(monkeypatch):
    prepared = _prepare(monkeypatch, "I want to build a quantum app", hits=[])
    assert isinstance(prepared, Ready) and prepared.response.fallback is True
    assert prepared.response.lead is not None and prepared.response.lead.score == "warm"


def test_handoff_has_no_lead(monkeypatch):
    prepared = _prepare(monkeypatch, "I want to talk to a human")
    assert isinstance(prepared, Ready) and prepared.response.lead is None
    assert "lead" not in done_event(prepared.response)


def test_stream_done_event_carries_lead_only_for_sales(monkeypatch):
    streamer = lambda q, h, history: iter(["SharpBuild builds apps [1]."])
    sales = _prepare(monkeypatch, "I need an app in 3 months")
    done = list(stream_answer(sales, streamer))[-1]
    assert done["type"] == "done" and done["lead"]["score"] == "warm" and done["lead"]["next_field"] == "budget"

    plain = _prepare(monkeypatch, "What services does SharpBuild offer?")
    done = list(stream_answer(plain, streamer))[-1]
    assert done["type"] == "done" and "lead" not in done
