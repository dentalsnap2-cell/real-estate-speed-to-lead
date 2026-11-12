import os
import time
import logging
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from backend.ai_engine import qualify_lead
from backend.services import (
    get_settings, save_lead, send_lead_email, send_hot_lead_alert,
    update_lead_delivery,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("speed-to-lead")
app = FastAPI(title="Real Estate Speed-to-Lead Engine", version="1.0.0")


class IncomingLead(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    property_interest: str | None = Field(default=None, max_length=250)
    inquiry_message: str = Field(min_length=3, max_length=5000)


def process_new_lead(lead_data: dict, agency_id: str):
    started = time.perf_counter()
    lead = dict(lead_data)
    try:
        settings = get_settings(agency_id)
        analysis = qualify_lead(lead, settings)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        lead_id = save_lead(lead, analysis, agency_id, elapsed_ms)
        try:
            email_status = send_lead_email(lead, analysis, settings)
        except Exception:
            logger.exception("Lead email delivery failed")
            email_status = "failed"
        alert_status = "not_required"
        if analysis.lead_score >= 8:
            try:
                alert_status = send_hot_lead_alert(lead, analysis, agency_id)
            except Exception:
                logger.exception("Hot lead alert failed")
                alert_status = "failed"
        update_lead_delivery(lead_id, email_status, alert_status)
        logger.info("Processed lead %s; score=%s; email=%s", lead_id, analysis.lead_score, email_status)
    except Exception:
        logger.exception("Background lead processing failed")


@app.get("/health")
def health():
    return {"status": "ok", "service": "real-estate-speed-to-lead"}


@app.post("/webhook/new-lead", status_code=status.HTTP_202_ACCEPTED)
def new_lead(
    payload: IncomingLead,
    background_tasks: BackgroundTasks,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    expected = os.getenv("AGENCY_API_KEY", "")
    if not expected or not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    agency_id = os.getenv("AGENCY_ID", "default-agency")
    background_tasks.add_task(process_new_lead, payload.model_dump(mode="json"), agency_id)
    return {"accepted": True, "message": "Lead received and queued for processing."}
