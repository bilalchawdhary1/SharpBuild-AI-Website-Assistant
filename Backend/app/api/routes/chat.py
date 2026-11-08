import json
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.ai_service import make_gemini_answerer, make_gemini_streamer
from app.services.chat_service import Ready, answer_question, done_event, prepare, stream_answer
from app.services.embeddings import make_gemini_embedder, with_retries

router = APIRouter()
# One quick retry only: a visitor is waiting, so don't sleep through long back-offs.
RETRY = {"attempts": 2, "base_delay": 1.0}


def require_ai(settings: Settings = Depends(get_settings)) -> Settings:
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="AI service is not configured")
    return settings


@lru_cache      # build each Gemini client once, not on every request
def _embedder(api_key: str, model: str):
    return with_retries(make_gemini_embedder(api_key, model, "RETRIEVAL_QUERY"), **RETRY)


@lru_cache
def _answerer(api_key: str, model: str, fallbacks: tuple[str, ...]):
    # No with_retries here: the fallback-model chain is the retry, and stacking both
    # would keep a waiting visitor for minutes.
    return make_gemini_answerer(api_key, model, fallbacks=fallbacks)


@lru_cache
def _streamer(api_key: str, model: str, fallbacks: tuple[str, ...]):
    return make_gemini_streamer(api_key, model, fallbacks=fallbacks)


def get_embed_query(settings: Settings = Depends(require_ai)):
    return _embedder(settings.gemini_api_key, settings.embedding_model)


def get_answerer(settings: Settings = Depends(require_ai)):
    return _answerer(settings.gemini_api_key, settings.generation_model, tuple(settings.fallback_models))


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit)])
def chat(request: ChatRequest,
         db: Session = Depends(get_db),
         settings: Settings = Depends(require_ai),
         embed_query=Depends(get_embed_query),
         answerer=Depends(get_answerer)) -> ChatResponse:
    return answer_question(db, request.message, embed_query, answerer,
                           min_similarity=settings.min_similarity, k=settings.retrieval_k)


def get_streamer(settings: Settings = Depends(require_ai)):
    return _streamer(settings.gemini_api_key, settings.generation_model, tuple(settings.fallback_models))


def sse(event: dict) -> str:
    """One server-sent event: a JSON line followed by a blank line."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat/stream", dependencies=[Depends(rate_limit)])
def chat_stream(request: ChatRequest,
                db: Session = Depends(get_db),
                settings: Settings = Depends(require_ai),
                embed_query=Depends(get_embed_query),
                streamer=Depends(get_streamer)) -> StreamingResponse:
    # Retrieval uses the database session, so it finishes HERE, before streaming starts:
    # the session is closed once this function returns.
    prepared = prepare(db, request.message, embed_query,
                       min_similarity=settings.min_similarity, k=settings.retrieval_k)

    def events():
        yield sse({"type": "start"})
        if isinstance(prepared, Ready):
            yield sse(done_event(prepared.response))
            return
        for event in stream_answer(prepared, streamer):
            yield sse(event)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
