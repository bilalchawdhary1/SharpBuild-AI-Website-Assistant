from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse, ChatSource
from app.services.ai_service import make_gemini_answerer
from app.services.embeddings import make_gemini_embedder, with_retries
from app.services.knowledge_service import retrieve

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="AI service is not configured")

    embed_query = with_retries(make_gemini_embedder(
        settings.gemini_api_key, settings.embedding_model, "RETRIEVAL_QUERY"))
    hits = retrieve(db, request.message, embed_query)
    answer = make_gemini_answerer(
        settings.gemini_api_key, settings.generation_model)(request.message, hits)
    sources = [
        ChatSource(url=hit.url, title=hit.title, section=hit.section)
        for hit in hits
    ]
    return ChatResponse(answer=answer, sources=sources)