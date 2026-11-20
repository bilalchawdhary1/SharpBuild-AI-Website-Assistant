import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes.chat import router as chat_router
from app.api.routes.admin import router as admin_router
from app.api.routes.lead import router as lead_router
from app.core.config import get_settings
from app.core.observability import RequestLogMiddleware, configure_logging
from app.core.security import SecurityMiddleware
from app.db.session import get_db

settings = get_settings()
configure_logging(settings.log_format, settings.log_level)
app = FastAPI(
    title=settings.app_name,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)
app.include_router(chat_router)
app.include_router(lead_router)
app.include_router(admin_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex or None,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.add_middleware(SecurityMiddleware, max_body_bytes=settings.max_body_bytes)
app.add_middleware(RequestLogMiddleware)                                           # added last = outermost


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """A crash returns JSON with the request id (also in the logs) instead of a bare text page."""
    request_id = getattr(request.state, "request_id", "-")
    logging.getLogger("sharpbuild.app").error("unhandled error request_id=%s", request_id, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong. Please try again, or email hello@sharpbuild.io.",
                 "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


@app.get("/")
def root():
    return {"message": f"{settings.app_name} is running!"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok"}