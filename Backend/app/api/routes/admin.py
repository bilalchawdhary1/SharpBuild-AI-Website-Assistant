import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.rate_limit import admin_rate_limit
from app.db.session import get_db
from app.services.lead_service import lead_stats, retry_pending

logger = logging.getLogger("sharpbuild.admin")
router = APIRouter()
MIN_ADMIN_TOKEN_CHARS = 32           # a short token can be guessed; generate a long random one


def require_admin(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """Token via `X-Admin-Token` or `Authorization: Bearer ...` (what Vercel Cron sends)."""
    token = settings.admin_token
    if not token:
        raise HTTPException(status_code=404)            # not configured: the endpoint does not exist
    if len(token) < MIN_ADMIN_TOKEN_CHARS:
        logger.error("ADMIN_TOKEN is shorter than %d characters: admin endpoint disabled", MIN_ADMIN_TOKEN_CHARS)
        raise HTTPException(status_code=404)
    supplied = request.headers.get("x-admin-token") or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(status_code=401, detail="unauthorized")


# GET as well as POST because Vercel Cron can only issue GET requests.
@router.api_route("/internal/retry-lead-notifications", methods=["GET", "POST"], dependencies=[Depends(admin_rate_limit), Depends(require_admin)])
def retry_lead_notifications(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    return retry_pending(db, settings)


@router.get("/internal/stats", dependencies=[Depends(admin_rate_limit), Depends(require_admin)])
def stats(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    """For a monitor or a quick look: lead volume and notifications that are stuck (gave_up > 0)."""
    return lead_stats(db, settings)
