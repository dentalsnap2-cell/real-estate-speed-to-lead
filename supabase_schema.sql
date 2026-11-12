-- Run this in Supabase SQL Editor. Use the service-role key only on trusted servers.
create extension if not exists pgcrypto;

create table if not exists public.agency_settings (
    agency_id text primary key,
    agency_name text not null default 'Northstar Realty',
    target_neighborhoods text[] not null default array['Downtown','Westside'],
    minimum_budget numeric(14,2) not null default 250000,
    email_signoff text not null default 'Best regards, Northstar Realty',
    system_instructions text not null default 'Be helpful, concise, accurate, and never invent property availability or pricing.',
    brochure_intro text not null default 'Thank you for your property enquiry. Our team will be in touch shortly.',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.leads (
    id uuid primary key default gen_random_uuid(),
    agency_id text not null references public.agency_settings(agency_id) on delete cascade,
    full_name text not null,
    email text not null,
    phone text,
    property_interest text,
    inquiry_message text,
    raw_payload jsonb not null default '{}'::jsonb,
    intent text,
    extracted_budget numeric(14,2),
    extracted_location text,
    lead_score integer check (lead_score between 1 and 10),
    agent_summary text[] not null default '{}',
    email_subject text,
    email_body text,
    status text not null default 'New' check (status in ('New','Contacted','Closed')),
    response_time_ms integer,
    email_status text not null default 'pending',
    alert_status text not null default 'not_required',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists leads_agency_created_idx on public.leads(agency_id, created_at desc);
create index if not exists leads_agency_score_idx on public.leads(agency_id, lead_score desc);
create index if not exists leads_agency_status_idx on public.leads(agency_id, status);

insert into public.agency_settings
(agency_id, agency_name, target_neighborhoods, minimum_budget, email_signoff, system_instructions, brochure_intro)
values
('default-agency', 'Northstar Realty', array['Downtown','Westside','Riverside'], 250000,
 'Best regards, Northstar Realty',
 'Be helpful, concise, accurate, and never invent property availability, prices, amenities, or guarantees. Ask one useful follow-up question when key information is missing.',
 'Thank you for reaching out to Northstar Realty. We have received your enquiry and a property specialist will contact you shortly.')
on conflict (agency_id) do nothing;

-- For a production multi-tenant deployment, enable RLS and add policies scoped to
-- authenticated dashboard users. This starter uses the service-role key only in
-- trusted server processes and does not expose it to browsers or Streamlit clients.
