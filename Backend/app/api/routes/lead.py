import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.rate_limit import lead_rate_limit
from app.db.session import get_db
from app.schemas.lead import LeadRequest, LeadResponse
from app.services.lead_notify import notify_lead
from app.services.lead_service import save_lead

logger = logging.getLogger("sharpbuild.lead")
router = APIRouter()


@router.post("/lead", response_model=LeadResponse, dependencies=[Depends(lead_rate_limit)])
def create_lead(request: LeadRequest, db: Session = Depends(get_db),
                settings: Settings = Depends(get_settings)) -> LeadResponse:
    if request.website:                    # honeypot filled: a bot. Pretend success, store nothing.
        logger.info("lead honeypot hit")
        return LeadResponse()
    try:
        record = save_lead(db, request)    # a duplicate is also reported as success (idempotent)
    except Exception:
        db.rollback()
        logger.exception("lead save failed")
        raise HTTPException(status_code=503, detail="We couldn't save your details. Please email hello@sharpbuild.io.")
    if record is not None:
        notify_lead(db, record, settings)  # never raises; a failure is retried later
    return LeadResponse()
