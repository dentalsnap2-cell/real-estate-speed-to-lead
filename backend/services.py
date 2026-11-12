import base64
import os
import sqlite3
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
import requests
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

load_dotenv()
DB_PATH = Path(os.getenv("LOCAL_DB_PATH", "speed_to_lead_local.db"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _supabase():
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    from supabase import create_client
    return create_client(url, key)


def _sqlite():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        create table if not exists agency_settings (
          agency_id text primary key, agency_name text not null,
          target_neighborhoods text not null, minimum_budget real not null,
          email_signoff text not null, system_instructions text not null,
          brochure_intro text not null, updated_at text not null
        )
    """)
    conn.execute("""
        create table if not exists leads (
          id text primary key, agency_id text not null, full_name text not null,
          email text not null, phone text, property_interest text, inquiry_message text,
          raw_payload text, intent text, extracted_budget real, extracted_location text,
          lead_score integer, agent_summary text, email_subject text, email_body text,
          status text not null default 'New', response_time_ms integer,
          email_status text, alert_status text, created_at text, updated_at text
        )
    """)
    conn.execute("""
        insert or ignore into agency_settings values
        ('default-agency','Northstar Realty','Downtown,Westside,Riverside',250000,
         'Best regards, Northstar Realty',
         'Be helpful, concise, accurate, and never invent property availability or pricing.',
         'Thank you for reaching out. Our team will contact you shortly.',?)
    """, (_now(),))
    conn.commit()
    return conn


def get_settings(agency_id: str) -> dict:
    sb = _supabase()
    if sb:
        result = sb.table("agency_settings").select("*").eq("agency_id", agency_id).limit(1).execute()
        if result.data:
            return result.data[0]
        default = {
            "agency_id": agency_id, "agency_name": "Your Real Estate Agency",
            "target_neighborhoods": [], "minimum_budget": 0,
            "email_signoff": "Best regards, Your Real Estate Team",
            "system_instructions": "Be helpful, concise, and truthful.",
            "brochure_intro": "Thank you for your enquiry."
        }
        sb.table("agency_settings").insert(default).execute()
        return default
    conn = _sqlite()
    row = conn.execute("select * from agency_settings where agency_id=?", (agency_id,)).fetchone()
    data = dict(row)
    data["target_neighborhoods"] = [x for x in data["target_neighborhoods"].split(",") if x]
    conn.close()
    return data


def update_settings(agency_id: str, values: dict) -> dict:
    payload = {
        "agency_id": agency_id,
        "agency_name": values["agency_name"].strip(),
        "target_neighborhoods": values["target_neighborhoods"],
        "minimum_budget": float(values["minimum_budget"]),
        "email_signoff": values["email_signoff"].strip(),
        "system_instructions": values["system_instructions"].strip(),
        "brochure_intro": values["brochure_intro"].strip(),
        "updated_at": _now(),
    }
    sb = _supabase()
    if sb:
        result = sb.table("agency_settings").upsert(payload).execute()
        return result.data[0] if result.data else payload
    conn = _sqlite()
    payload_local = dict(payload)
    payload_local["target_neighborhoods"] = ",".join(payload["target_neighborhoods"])
    conn.execute("""
      insert into agency_settings values
      (:agency_id,:agency_name,:target_neighborhoods,:minimum_budget,:email_signoff,
       :system_instructions,:brochure_intro,:updated_at)
      on conflict(agency_id) do update set agency_name=excluded.agency_name,
       target_neighborhoods=excluded.target_neighborhoods, minimum_budget=excluded.minimum_budget,
       email_signoff=excluded.email_signoff, system_instructions=excluded.system_instructions,
       brochure_intro=excluded.brochure_intro, updated_at=excluded.updated_at
    """, payload_local)
    conn.commit()
    conn.close()
    return payload


def save_lead(lead: dict, analysis: Any, agency_id: str, elapsed_ms: int) -> str:
    import json, uuid
    lead_id = str(uuid.uuid4())
    row = {
        "id": lead_id, "agency_id": agency_id, "full_name": lead["full_name"],
        "email": lead["email"], "phone": lead.get("phone"),
        "property_interest": lead.get("property_interest"),
        "inquiry_message": lead.get("inquiry_message"),
        "raw_payload": lead, "intent": analysis.intent,
        "extracted_budget": analysis.extracted_budget,
        "extracted_location": analysis.extracted_location,
        "lead_score": analysis.lead_score, "agent_summary": analysis.agent_summary,
        "email_subject": analysis.email_subject, "email_body": analysis.email_body,
        "status": "New", "response_time_ms": elapsed_ms,
        "email_status": "pending", "alert_status": "not_required",
        "created_at": _now(), "updated_at": _now()
    }
    sb = _supabase()
    if sb:
        sb.table("leads").insert(row).execute()
    else:
        local = dict(row)
        local["raw_payload"] = json.dumps(row["raw_payload"])
        local["agent_summary"] = json.dumps(row["agent_summary"])
        conn = _sqlite()
        conn.execute("""
          insert into leads(id,agency_id,full_name,email,phone,property_interest,inquiry_message,
          raw_payload,intent,extracted_budget,extracted_location,lead_score,agent_summary,
          email_subject,email_body,status,response_time_ms,email_status,alert_status,created_at,updated_at)
          values(:id,:agency_id,:full_name,:email,:phone,:property_interest,:inquiry_message,
          :raw_payload,:intent,:extracted_budget,:extracted_location,:lead_score,:agent_summary,
          :email_subject,:email_body,:status,:response_time_ms,:email_status,:alert_status,:created_at,:updated_at)
        """, local)
        conn.commit()
        conn.close()
    return lead_id


def update_lead_delivery(lead_id: str, email_status: str, alert_status: str):
    sb = _supabase()
    values = {"email_status": email_status, "alert_status": alert_status, "updated_at": _now()}
    if sb:
        sb.table("leads").update(values).eq("id", lead_id).execute()
    else:
        conn = _sqlite()
        conn.execute("update leads set email_status=?, alert_status=?, updated_at=? where id=?",
                     (email_status, alert_status, _now(), lead_id))
        conn.commit()
        conn.close()


def list_leads(agency_id: str) -> list[dict]:
    sb = _supabase()
    if sb:
        result = sb.table("leads").select("*").eq("agency_id", agency_id).order("created_at", desc=True).limit(1000).execute()
        return result.data or []
    import json
    conn = _sqlite()
    rows = [dict(r) for r in conn.execute("select * from leads where agency_id=? order by created_at desc limit 1000", (agency_id,)).fetchall()]
    conn.close()
    for row in rows:
        for key in ("raw_payload", "agent_summary"):
            try: row[key] = json.loads(row[key] or ("[]" if key == "agent_summary" else "{}"))
            except Exception: pass
    return rows


def set_lead_status(agency_id: str, lead_id: str, status: str):
    sb = _supabase()
    values = {"status": status, "updated_at": _now()}
    if sb:
        sb.table("leads").update(values).eq("id", lead_id).eq("agency_id", agency_id).execute()
    else:
        conn = _sqlite()
        conn.execute("update leads set status=?, updated_at=? where id=? and agency_id=?",
                     (status, _now(), lead_id, agency_id))
        conn.commit()
        conn.close()


def generate_brochure_pdf(lead: dict, settings: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=22*mm, leftMargin=22*mm,
                            topMargin=22*mm, bottomMargin=22*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BrandTitle", parent=styles["Title"], textColor=colors.HexColor("#123B5D"), fontSize=23, leading=28))
    styles.add(ParagraphStyle(name="Accent", parent=styles["Heading2"], textColor=colors.HexColor("#D18B35")))
    story = [
        Paragraph(settings.get("agency_name", "Real Estate Agency"), styles["BrandTitle"]),
        Paragraph("PROPERTY ENQUIRY BRIEF", styles["Accent"]),
        Spacer(1, 12),
        Paragraph(f"Prepared for: <b>{lead['full_name']}</b>", styles["BodyText"]),
        Spacer(1, 8),
        Paragraph(settings.get("brochure_intro", "Thank you for your enquiry."), styles["BodyText"]),
        Spacer(1, 18),
        Paragraph("Your enquiry details", styles["Heading2"]),
    ]
    details = [
        ["Property interest", lead.get("property_interest") or "Not specified"],
        ["Preferred contact", lead.get("email") or ""],
        ["Phone", lead.get("phone") or "Not provided"],
    ]
    table = Table(details, colWidths=[45*mm, 110*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#EEF3F7")),
        ("TEXTCOLOR", (0,0), (0,-1), colors.HexColor("#123B5D")),
        ("GRID", (0,0), (-1,-1), .4, colors.HexColor("#D5DEE6")),
        ("PADDING", (0,0), (-1,-1), 9),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.extend([table, Spacer(1, 20),
                  Paragraph("A member of our team will follow up to understand your requirements and discuss suitable next steps.", styles["BodyText"]),
                  Spacer(1, 30),
                  Paragraph(settings.get("email_signoff", "Your Real Estate Team"), styles["BodyText"])])
    doc.build(story)
    return buffer.getvalue()


def send_lead_email(lead: dict, analysis: Any, settings: dict) -> str:
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        print(f"[MOCK EMAIL] To: {lead['email']} | Subject: {analysis.email_subject}")
        return "mocked"
    pdf = generate_brochure_pdf(lead, settings)
    from_email = os.getenv("RESEND_FROM_EMAIL", "Real Estate Team <onboarding@resend.dev>")
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "from": from_email, "to": [lead["email"]],
            "subject": analysis.email_subject,
            "html": "<div style='font-family:Arial,sans-serif;line-height:1.6;max-width:620px'>"
                    + analysis.email_body.replace("\n", "<br>")
                    + "</div>",
            "attachments": [{"filename": "property-enquiry-brief.pdf",
                             "content": base64.b64encode(pdf).decode("ascii")}],
        }, timeout=15
    )
    response.raise_for_status()
    return "sent"


def send_hot_lead_alert(lead: dict, analysis: Any, agency_id: str) -> str:
    message = (
        f":fire: *HOT REAL ESTATE LEAD — score {analysis.lead_score}/10*\n"
        f"*Name:* {lead['full_name']}\n*Email:* {lead['email']}\n"
        f"*Phone:* {lead.get('phone') or 'Not supplied'}\n"
        f"*Intent:* {analysis.intent}\n*Interest:* {lead.get('property_interest') or 'Not specified'}\n"
        f"*Summary:* {' | '.join(analysis.agent_summary)}\n*Agency:* {agency_id}"
    )
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if webhook:
        response = requests.post(webhook, json={"text": message}, timeout=10)
        response.raise_for_status()
        return "sent"
    print("[MOCK SLACK ALERT]\n" + message)
    return "mocked"
