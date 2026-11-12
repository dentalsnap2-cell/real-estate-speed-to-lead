import os
from typing import Literal
from pydantic import BaseModel, Field
from openai import OpenAI


class LeadAnalysis(BaseModel):
    intent: Literal["Buyer", "Seller", "Renter", "Investor"]
    extracted_budget: float | None = Field(default=None, ge=0)
    extracted_location: str | None = None
    lead_score: int = Field(ge=1, le=10)
    agent_summary: list[str] = Field(min_length=2, max_length=2)
    email_subject: str
    email_body: str


def _mock_analysis(lead: dict, settings: dict) -> LeadAnalysis:
    message = (lead.get("inquiry_message") or "").lower()
    interest = (lead.get("property_interest") or "").lower()
    combined = message + " " + interest
    if any(x in combined for x in ("invest", "rental yield", "roi", "investment")):
        intent = "Investor"
    elif any(x in combined for x in ("sell", "selling", "valuation", "list my")):
        intent = "Seller"
    elif any(x in combined for x in ("rent", "lease", "tenant", "rental")):
        intent = "Renter"
    else:
        intent = "Buyer"

    score = 7 if lead.get("phone") else 5
    if any(x in combined for x in ("urgent", "asap", "this week", "ready to")):
        score += 2
    score = min(score, 10)
    name = lead.get("full_name", "there").split()[0]
    agency = settings.get("agency_name", "our team")
    signoff = settings.get("email_signoff", f"Best regards, {agency}")
    body = (
        f"Hi {name},\n\n"
        f"Thank you for contacting {agency} about {lead.get('property_interest') or 'your property enquiry'}. "
        "We have received your message and a property specialist will review your requirements. "
        "Could you share your preferred timeline and any must-have features so we can guide you accurately?\n\n"
        f"{signoff}"
    )
    return LeadAnalysis(
        intent=intent,
        extracted_budget=None,
        extracted_location=None,
        lead_score=score,
        agent_summary=[
            f"{intent} enquiry: {lead.get('property_interest') or 'property requirements not specified'}.",
            "Confirm budget, preferred location, and timeline during first contact."
        ],
        email_subject=f"Thanks for your property enquiry, {name}",
        email_body=body,
    )


def qualify_lead(lead: dict, settings: dict) -> LeadAnalysis:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[MOCK AI] OPENAI_API_KEY missing; using local deterministic qualification.")
        return _mock_analysis(lead, settings)

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    instructions = settings.get("system_instructions", "")
    neighborhoods = settings.get("target_neighborhoods", [])
    prompt = f"""
Agency: {settings.get('agency_name', 'Real Estate Agency')}
Target neighborhoods: {neighborhoods}
Minimum budget threshold: {settings.get('minimum_budget', 0)}
Agency instructions: {instructions}

Analyze this inbound real-estate enquiry. Score urgency and commercial fit from 1 to 10.
Do not assume facts not stated. Extract a numeric budget only when clearly provided.
Use the closest intent category. Write exactly two concise agent-summary bullets.
Draft a warm, personalized, truthful email. Do not claim a property is available.
Lead data:
{lead}
"""
    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": "You are a careful real-estate lead qualification assistant."},
            {"role": "user", "content": prompt},
        ],
        response_format=LeadAnalysis,
        temperature=0.2,
    )
    parsed = completion.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("OpenAI returned no parsed lead analysis.")
    return parsed
