"""

Stage 1: SAM.gov opportunities + contract awards -> Supabase (PostgreSQL)



Run from the rfp-agent folder with the venv active:

    python stage1_sam_ingest.py

"""



import os

import sys

from datetime import datetime, date, timedelta

from decimal import Decimal, InvalidOperation



import psycopg2

import psycopg2.extras

import requests

from dotenv import load_dotenv



# ============================================================

# SETTINGS (change these as needed)

# ============================================================



DAYS_BACK = 30                  # how far back to look for new opportunities

OPPORTUNITY_LIMIT = 100         # records per API page (SAM max is 1000)

MAX_DESCRIPTIONS_PER_RUN = 25   # description fetches cost 1 API call each

RUN_AWARDS = True               # set False to skip the awards step

# Notice types that are already awarded or closed, so not bid opportunities

SKIP_TYPES = {"Award Notice", "Justification", "Sale of Surplus Property"}

AWARD_LIMIT = 100               # award records per NAICS per run

AWARD_DATE_FROM = "01/01/2025"  # awards are searched from here...

AWARD_DAYS_DELAY = 91           # ...up to today minus this many days



OPPORTUNITIES_URL = "https://api.sam.gov/opportunities/v2/search"

AWARDS_URL = "https://api.sam.gov/contract-awards/v1/search"



# ============================================================

# SETUP

# ============================================================



if hasattr(sys.stdout, "reconfigure"):

    sys.stdout.reconfigure(encoding="utf-8")

if hasattr(sys.stderr, "reconfigure"):

    sys.stderr.reconfigure(encoding="utf-8")



load_dotenv()

SAM_API_KEY = os.getenv("SAM_API_KEY")

DATABASE_URL = os.getenv("DATABASE_URL")



if not SAM_API_KEY:

    sys.exit("ERROR: SAM_API_KEY not found in .env")

if not DATABASE_URL:

    sys.exit("ERROR: DATABASE_URL not found in .env")



today = date.today()

fmt = "%m/%d/%Y"

POSTED_FROM = (today - timedelta(days=DAYS_BACK)).strftime(fmt)

POSTED_TO = today.strftime(fmt)

AWARD_DATE_TO = (today - timedelta(days=AWARD_DAYS_DELAY)).strftime(fmt)





# ============================================================

# HELPER FUNCTIONS

# ============================================================



def safe_decimal(value):

    if value is None or value == "":

        return None

    try:

        return Decimal(str(value).replace(",", "").replace("$", ""))

    except (InvalidOperation, ValueError):

        return None





def safe_date(value):

    if not value:

        return None

    value = str(value).strip()

    for f in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",

              "%m/%d/%Y", "%m/%d/%Y %H:%M:%S"):

        try:

            return datetime.strptime(value, f).date()

        except ValueError:

            pass

    try:

        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()

    except Exception:

        return None





def get_nested(data, *keys):

    current = data

    for key in keys:

        if not isinstance(current, dict):

            return None

        current = current.get(key)

    return current





def get_first_nonempty(*values):

    for value in values:

        if value not in (None, "", [], {}):

            return value

    return None





def fetch_description(url):

    """Return the description text, or None if unavailable."""

    try:

        r = requests.get(url, params={"api_key": SAM_API_KEY}, timeout=30)

    except requests.RequestException:

        return None

    if r.status_code != 200:

        return None

    try:

        body = r.json()

        if isinstance(body, dict):

            return body.get("description") or None

    except ValueError:

        pass

    return r.text or None





# ============================================================

# DATABASE

# ============================================================



print("=" * 70)

print("SAM.GOV INGESTION")

print(f"Opportunities posted: {POSTED_FROM} to {POSTED_TO}")

print("=" * 70)



try:

    conn = psycopg2.connect(DATABASE_URL)

    conn.autocommit = False

    cur = conn.cursor()

    print("Database connection successful.")

except Exception as e:

    sys.exit(f"ERROR connecting to database: {e}")



# Make sure every column and table the script needs exists.

try:

    cur.execute("""

        ALTER TABLE opportunities

            ADD COLUMN IF NOT EXISTS contact_phone TEXT,

            ADD COLUMN IF NOT EXISTS description   TEXT,

            ADD COLUMN IF NOT EXISTS psc_code      TEXT,

            ADD COLUMN IF NOT EXISTS contract_type TEXT,

            ADD COLUMN IF NOT EXISTS inactive_date TEXT;



        CREATE TABLE IF NOT EXISTS contract_awards (
            id                    BIGSERIAL PRIMARY KEY,
            piid                  TEXT,
            modification_number   TEXT,
            transaction_number    TEXT,
            naics_code            TEXT,
            awardee_name          TEXT,
            awardee_uei           TEXT,
            awardee_cage          TEXT,
            award_date            DATE,
            action_obligation     NUMERIC,
            contract_type         TEXT,
            competition_type      TEXT,
            referenced_idv_piid   TEXT,
            agency_name           TEXT,
            contracting_office   TEXT,
            place_of_performance TEXT,
            awardee_phone         TEXT,
            awardee_city          TEXT,
            awardee_state         TEXT,
            awardee_country       TEXT,
            pricing_type          TEXT,
            set_aside_type        TEXT,
            psc_code              TEXT,
            psc_name              TEXT,
            raw                   JSONB,
            first_seen_at         TIMESTAMPTZ DEFAULT NOW(),
            updated_at            TIMESTAMPTZ DEFAULT NOW()
        );

        ALTER TABLE contract_awards
            ADD COLUMN IF NOT EXISTS agency_name TEXT,
            ADD COLUMN IF NOT EXISTS contracting_office TEXT,
            ADD COLUMN IF NOT EXISTS place_of_performance TEXT,
            ADD COLUMN IF NOT EXISTS awardee_phone TEXT,
            ADD COLUMN IF NOT EXISTS awardee_city TEXT,
            ADD COLUMN IF NOT EXISTS awardee_state TEXT,
            ADD COLUMN IF NOT EXISTS awardee_country TEXT,
            ADD COLUMN IF NOT EXISTS pricing_type TEXT,
            ADD COLUMN IF NOT EXISTS set_aside_type TEXT,
            ADD COLUMN IF NOT EXISTS psc_code TEXT,
            ADD COLUMN IF NOT EXISTS psc_name TEXT;

        CREATE UNIQUE INDEX IF NOT EXISTS contract_awards_unique_idx
            ON contract_awards (piid, modification_number, transaction_number);

    """)

    conn.commit()

    print("Tables and columns ready.")

except Exception as e:

    conn.rollback()

    sys.exit(f"ERROR preparing tables: {e}")



cur.execute("SELECT naics_code FROM naics_config WHERE active = TRUE ORDER BY naics_code;")

naics_codes = [r[0] for r in cur.fetchall()]

print(f"Active NAICS codes: {', '.join(naics_codes) or 'none'}")



stats = {

    "found": 0, "new": 0, "updated": 0, "errors": 0, "skipped": 0,

    "desc_fetched": 0, "desc_failed": 0,

    "award_calls": 0, "award_returned": 0, "award_saved": 0, "award_errors": 0,

}



# ============================================================

# STEP 1: OPPORTUNITIES

# ============================================================



UPSERT_OPP = """

    INSERT INTO opportunities (

        notice_id, posted_date, notice_type, title, solicitation_number,

        agency, naics_code, set_aside, response_deadline,

        place_of_performance, contact_name, contact_email, contact_phone,

        sam_link, status, description, psc_code, contract_type,

        inactive_date, attachments, raw

    ) VALUES (

        %(notice_id)s, %(posted_date)s, %(notice_type)s, %(title)s,

        %(solicitation_number)s, %(agency)s, %(naics_code)s, %(set_aside)s,

        %(response_deadline)s, %(place)s, %(contact_name)s, %(contact_email)s,

        %(contact_phone)s, %(sam_link)s, 'New', %(description)s, %(psc_code)s,

        %(contract_type)s, %(inactive_date)s, %(attachments)s, %(raw)s

    )

    ON CONFLICT (notice_id) DO UPDATE SET

        posted_date          = EXCLUDED.posted_date,

        notice_type          = EXCLUDED.notice_type,

        title                = EXCLUDED.title,

        solicitation_number  = EXCLUDED.solicitation_number,

        agency               = EXCLUDED.agency,

        naics_code           = EXCLUDED.naics_code,

        set_aside            = EXCLUDED.set_aside,

        response_deadline    = EXCLUDED.response_deadline,

        place_of_performance = EXCLUDED.place_of_performance,

        contact_name         = EXCLUDED.contact_name,

        contact_email        = EXCLUDED.contact_email,

        contact_phone        = EXCLUDED.contact_phone,

        sam_link             = EXCLUDED.sam_link,

        description          = COALESCE(EXCLUDED.description, opportunities.description),

        psc_code             = EXCLUDED.psc_code,

        contract_type        = EXCLUDED.contract_type,

        inactive_date        = EXCLUDED.inactive_date,

        attachments          = EXCLUDED.attachments,

        raw                  = EXCLUDED.raw,

        updated_at           = NOW()

    RETURNING (xmax = 0);

"""

# Note: status is never overwritten, so your Bid / No-bid choices are kept.





def save_opportunity(opp):

    notice_id = opp.get("noticeId")

    if not notice_id:

        return None



    place = opp.get("placeOfPerformance") or {}

    place_text = ", ".join(x for x in [

        get_nested(place, "city", "name"),

        get_nested(place, "state", "name"),

        get_nested(place, "country", "name"),

    ] if x)



    contacts = opp.get("pointOfContact") or []

    contact = contacts[0] if contacts else {}



    # Fetch the description only if we don't already have it

    description = None

    cur.execute(

        "SELECT description IS NOT NULL AND description <> '' "

        "FROM opportunities WHERE notice_id = %s;", (notice_id,))

    row = cur.fetchone()

    have_description = bool(row and row[0])

    url = opp.get("description")

    if (url and not have_description

            and stats["desc_fetched"] < MAX_DESCRIPTIONS_PER_RUN):

        description = fetch_description(url)

        if description:

            stats["desc_fetched"] += 1

        else:

            stats["desc_failed"] += 1



    cur.execute(UPSERT_OPP, {

        "notice_id": notice_id,

        "posted_date": safe_date(opp.get("postedDate")),

        "notice_type": opp.get("type"),

        "title": opp.get("title") or "(no title)",

        "solicitation_number": opp.get("solicitationNumber"),

        "agency": opp.get("fullParentPathName"),

        "naics_code": opp.get("naicsCode"),

        "set_aside": opp.get("typeOfSetAsideDescription"),

        "response_deadline": opp.get("responseDeadLine") or None,

        "place": place_text,

        "contact_name": contact.get("fullName"),

        "contact_email": contact.get("email"),

        "contact_phone": contact.get("phone"),

        "sam_link": opp.get("uiLink"),

        "description": description,

        "psc_code": opp.get("classificationCode"),

        "contract_type": opp.get("baseType"),

        "inactive_date": opp.get("archiveDate"),

        "attachments": psycopg2.extras.Json(opp.get("resourceLinks") or []),

        "raw": psycopg2.extras.Json(opp),

    })

    return "new" if cur.fetchone()[0] else "updated"





print("\n" + "=" * 70)

print("STEP 1: OPPORTUNITIES")

print("=" * 70)



for naics in naics_codes:

    print(f"\nNAICS {naics}")

    offset = 0

    while True:

        try:

            resp = requests.get(OPPORTUNITIES_URL, params={

                "api_key": SAM_API_KEY,

                "postedFrom": POSTED_FROM,

                "postedTo": POSTED_TO,

                "ncode": naics,

                "limit": OPPORTUNITY_LIMIT,

                "offset": offset,

            }, timeout=30)

        except requests.RequestException as e:

            print(f"  Request failed: {e}")

            stats["errors"] += 1

            break



        if resp.status_code != 200:

            print(f"  API returned {resp.status_code}: {resp.text[:300]}")

            stats["errors"] += 1

            break



        data = resp.json()

        opps = data.get("opportunitiesData") or []

        total = data.get("totalRecords", 0)

        stats["found"] += len(opps)



        for opp in opps:

            if (opp.get("type") in SKIP_TYPES) or (opp.get("baseType") in SKIP_TYPES):

                stats["skipped"] += 1

                continue

            try:

                result = save_opportunity(opp)

                conn.commit()  # commit each record so one error can't undo the rest

                if result:

                    stats[result] += 1

            except Exception as e:

                conn.rollback()

                stats["errors"] += 1

                print(f"  ERROR on {opp.get('noticeId')}: {e}")



        offset += OPPORTUNITY_LIMIT

        if not opps or offset >= total:

            break



    print(f"  Done. Running totals: {stats['new']} new, {stats['updated']} updated")



# ============================================================

# STEP 2: CONTRACT AWARDS

# ============================================================



UPSERT_AWARD = """
    INSERT INTO contract_awards (
        piid, modification_number, transaction_number, naics_code,
        awardee_name, awardee_uei, awardee_cage, award_date,
        action_obligation, contract_type, competition_type,
        referenced_idv_piid,
        agency_name, contracting_office, place_of_performance,
        awardee_phone, awardee_city, awardee_state, awardee_country,
        pricing_type, set_aside_type, psc_code, psc_name,
        raw
    ) VALUES (
        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
    )
    ON CONFLICT (piid, modification_number, transaction_number)
    DO UPDATE SET
        naics_code            = EXCLUDED.naics_code,
        awardee_name          = EXCLUDED.awardee_name,
        awardee_uei           = EXCLUDED.awardee_uei,
        awardee_cage          = EXCLUDED.awardee_cage,
        award_date            = COALESCE(EXCLUDED.award_date, contract_awards.award_date),
        action_obligation     = COALESCE(EXCLUDED.action_obligation, contract_awards.action_obligation),
        contract_type         = COALESCE(EXCLUDED.contract_type, contract_awards.contract_type),
        competition_type      = COALESCE(EXCLUDED.competition_type, contract_awards.competition_type),
        referenced_idv_piid   = COALESCE(EXCLUDED.referenced_idv_piid, contract_awards.referenced_idv_piid),
        agency_name           = COALESCE(EXCLUDED.agency_name, contract_awards.agency_name),
        contracting_office    = COALESCE(EXCLUDED.contracting_office, contract_awards.contracting_office),
        place_of_performance  = COALESCE(EXCLUDED.place_of_performance, contract_awards.place_of_performance),
        awardee_phone         = COALESCE(EXCLUDED.awardee_phone, contract_awards.awardee_phone),
        awardee_city          = COALESCE(EXCLUDED.awardee_city, contract_awards.awardee_city),
        awardee_state         = COALESCE(EXCLUDED.awardee_state, contract_awards.awardee_state),
        awardee_country       = COALESCE(EXCLUDED.awardee_country, contract_awards.awardee_country),
        pricing_type          = COALESCE(EXCLUDED.pricing_type, contract_awards.pricing_type),
        set_aside_type        = COALESCE(EXCLUDED.set_aside_type, contract_awards.set_aside_type),
        psc_code              = COALESCE(EXCLUDED.psc_code, contract_awards.psc_code),
        psc_name              = COALESCE(EXCLUDED.psc_name, contract_awards.psc_name),
        raw                   = EXCLUDED.raw,
        updated_at            = NOW();
"""


def save_award(award, naics):
    contract_id = award.get("contractId") or {}
    details = award.get("awardDetails") or {}
    core = award.get("coreData") or {}

    piid = contract_id.get("piid")
    if not piid:
        return False

    awardee = details.get("awardeeData") or {}
    header = awardee.get("awardeeHeader") or {}
    uei_info = awardee.get("awardeeUEIInformation") or {}
    awardee_location = awardee.get("awardeeLocation") or {}

    dates = details.get("dates") or {}
    dollars = details.get("dollars") or {}

    awardee_name = get_first_nonempty(
        header.get("awardeeName"),
        header.get("legalBusinessName")
    )

    award_date = safe_date(get_first_nonempty(
        dates.get("dateSigned"),
        award.get("dateSigned"),
        core.get("dateSigned")
    ))

    obligation = safe_decimal(get_first_nonempty(
        dollars.get("actionObligation"),
        award.get("actionObligation"),
        core.get("actionObligation")
    ))

    acquisition = core.get("acquisitionData") or {}
    pricing = acquisition.get("typeOfContractPricing") or {}

    contract_type = get_first_nonempty(
        pricing.get("name"),
        pricing.get("code"),
        core.get("typeOfContractPricingName"),
        core.get("typeOfContractPricingCode")
    )

    competition = core.get("competitionInformation") or {}
    extent = competition.get("extentCompeted") or {}
    procedures = competition.get("solicitationProcedures") or {}
    set_aside = competition.get("typeOfSetAside") or {}

    competition_type = get_first_nonempty(
        extent.get("name"),
        extent.get("code"),
        procedures.get("name"),
        procedures.get("code")
    )

    set_aside_type = get_first_nonempty(
        set_aside.get("name"),
        set_aside.get("code")
    )

    federal_org = core.get("federalOrganization") or {}
    funding_info = federal_org.get("fundingInformation") or {}
    contracting_info = federal_org.get("contractingInformation") or {}

    funding_department = funding_info.get("fundingDepartment") or {}
    contracting_department = contracting_info.get("contractingDepartment") or {}
    contracting_office_data = contracting_info.get("contractingOffice") or {}

    agency_name = get_first_nonempty(
        contracting_department.get("name"),
        funding_department.get("name"),
        contracting_department.get("code"),
        funding_department.get("code")
    )

    contracting_office = get_first_nonempty(
        contracting_office_data.get("name"),
        contracting_office_data.get("code")
    )

    place_data = core.get("principalPlaceOfPerformance") or {}
    place_city = get_nested(place_data, "city", "name")
    place_state = get_nested(place_data, "state", "name")
    place_country = get_nested(place_data, "country", "name")

    place_of_performance = ", ".join(
        x for x in [place_city, place_state, place_country] if x
    ) or None

    awardee_state_data = awardee_location.get("state") or {}
    awardee_country_data = awardee_location.get("country") or {}

    product_info = core.get("productOrServiceInformation") or {}
    product_service = product_info.get("productOrService") or {}

    psc_code = product_service.get("code")
    psc_name = product_service.get("name")

    cur.execute(UPSERT_AWARD, (
        piid,
        contract_id.get("modificationNumber"),
        contract_id.get("transactionNumber"),
        naics,
        awardee_name,
        uei_info.get("uniqueEntityId"),
        uei_info.get("cageCode"),
        award_date,
        obligation,
        contract_type,
        competition_type,
        contract_id.get("referencedIDVPiid"),
        agency_name,
        contracting_office,
        place_of_performance,
        awardee_location.get("phoneNumber"),
        awardee_location.get("city"),
        awardee_state_data.get("name") or awardee_state_data.get("code"),
        awardee_country_data.get("name") or awardee_country_data.get("code"),
        contract_type,
        set_aside_type,
        psc_code,
        psc_name,
        psycopg2.extras.Json(award),
    ))

    return True



if RUN_AWARDS:

    print("\n" + "=" * 70)

    print("STEP 2: CONTRACT AWARDS")

    print(f"Date signed: {AWARD_DATE_FROM} to {AWARD_DATE_TO}")

    print("=" * 70)



    for naics in naics_codes:

        print(f"\nNAICS {naics}")

        try:

            resp = requests.get(AWARDS_URL, params={

                "api_key": SAM_API_KEY,

                "naicsCode": naics,

                "dateSigned": f"[{AWARD_DATE_FROM},{AWARD_DATE_TO}]",

                "awardOrIDV": "Award",

                "limit": AWARD_LIMIT,

                "includeSections": "contractId,coreData,awardDetails,awardeeData",

            }, timeout=60)

            stats["award_calls"] += 1

        except requests.RequestException as e:

            print(f"  Request failed: {e}")

            stats["award_errors"] += 1

            continue



        if resp.status_code != 200:

            print(f"  API returned {resp.status_code}: {resp.text[:300]}")

            stats["award_errors"] += 1

            continue



        body = resp.json()

        records = body.get("awardSummary") or []

        stats["award_returned"] += len(records)

        print(f"  Returned {len(records)} of {body.get('totalRecords', 0)} matching")



        saved_here = 0

        for award in records:

            try:

                if save_award(award, naics):

                    conn.commit()

                    saved_here += 1

            except Exception as e:

                conn.rollback()

                stats["award_errors"] += 1

                print(f"  ERROR saving award: {e}")

        stats["award_saved"] += saved_here

        print(f"  Saved {saved_here}")



# ============================================================

# SUMMARY

# ============================================================



print("\n" + "=" * 70)

print("FINAL SUMMARY")

print("=" * 70)

print(f"Opportunities found:      {stats['found']}")

print(f"Skipped (awarded/closed): {stats['skipped']}")

print(f"New saved:                {stats['new']}")

print(f"Existing updated:         {stats['updated']}")

print(f"Descriptions fetched:     {stats['desc_fetched']}")

print(f"Description failures:     {stats['desc_failed']}")

print(f"Opportunity errors:       {stats['errors']}")

if RUN_AWARDS:

    print(f"\nAward API calls:          {stats['award_calls']}")

    print(f"Award records returned:   {stats['award_returned']}")

    print(f"Award records saved:      {stats['award_saved']}")

    print(f"Award errors:             {stats['award_errors']}")

print("\nProcess completed.")



cur.close()

conn.close()
