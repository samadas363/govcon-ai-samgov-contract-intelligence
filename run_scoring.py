import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env")


SCORING_SQL = """
INSERT INTO public.opportunity_scores (
    notice_id,
    naics_score,
    capability_score,
    requirement_score,
    set_aside_score,
    past_performance_score,
    agency_score,
    deadline_score,
    total_score,
    classification,
    updated_at
)
SELECT
    o.notice_id,

    CASE
        WHEN o.naics_code = ANY(c.naics_codes)
        THEN 20
        ELSE 0
    END,

    CASE
        WHEN LOWER(
            COALESCE(o.title, '') || ' ' ||
            COALESCE(o.description, '')
        ) ~ 'management|administrative|logistics|janitorial|food service|training|consulting|professional services|equipment|supplies'
        THEN 20

        WHEN LOWER(
            COALESCE(o.title, '') || ' ' ||
            COALESCE(o.description, '')
        ) ~ 'support|operations|services'
        THEN 10

        ELSE 0
    END,

    CASE
        WHEN EXISTS (
            SELECT 1
            FROM public.solicitation_requirements r
            WHERE r.notice_id = o.notice_id
            AND LOWER(r.requirement_text)
            ~ 'management|administrative|logistics|janitorial|food service|training|consulting|professional services|equipment|supplies'
        )
        THEN 20

        WHEN EXISTS (
            SELECT 1
            FROM public.solicitation_requirements r
            WHERE r.notice_id = o.notice_id
        )
        THEN 10

        ELSE 0
    END,

    CASE
        WHEN o.set_aside IS NULL
             OR LOWER(o.set_aside) = ''
             OR LOWER(o.set_aside) LIKE '%no set aside%'
        THEN 15
        ELSE 0
    END,

    CASE
        WHEN LOWER(
            COALESCE(o.title, '') || ' ' ||
            COALESCE(o.description, '')
        ) ~ 'education|training|instruction|curriculum|management|administrative'
        THEN 10

        WHEN LOWER(
            COALESCE(o.title, '') || ' ' ||
            COALESCE(o.description, '')
        ) ~ 'support|consulting|services'
        THEN 5

        ELSE 0
    END,

    CASE
        WHEN (
            SELECT COUNT(DISTINCT ca.piid)
            FROM public.contract_awards ca
            WHERE ca.naics_code = o.naics_code
        ) >= 5
        THEN 10

        WHEN (
            SELECT COUNT(DISTINCT ca.piid)
            FROM public.contract_awards ca
            WHERE ca.naics_code = o.naics_code
        ) >= 1
        THEN 5

        ELSE 0
    END,

    CASE
        WHEN o.response_deadline IS NOT NULL
             AND o.response_deadline >= NOW()
        THEN 5
        ELSE 0
    END,

    0,
    NULL,
    NOW()

FROM public.opportunities o
CROSS JOIN LATERAL (
    SELECT naics_codes
    FROM public.company_capability_profile
    ORDER BY id
    LIMIT 1
) c

ON CONFLICT (notice_id)
DO UPDATE SET
    naics_score = EXCLUDED.naics_score,
    capability_score = EXCLUDED.capability_score,
    requirement_score = EXCLUDED.requirement_score,
    set_aside_score = EXCLUDED.set_aside_score,
    past_performance_score = EXCLUDED.past_performance_score,
    agency_score = EXCLUDED.agency_score,
    deadline_score = EXCLUDED.deadline_score,
    updated_at = NOW();


UPDATE public.opportunity_scores
SET total_score =
      COALESCE(naics_score, 0)
    + COALESCE(capability_score, 0)
    + COALESCE(requirement_score, 0)
    + COALESCE(set_aside_score, 0)
    + COALESCE(past_performance_score, 0)
    + COALESCE(agency_score, 0)
    + COALESCE(deadline_score, 0),
    updated_at = NOW();


UPDATE public.opportunity_scores
SET classification =
    CASE
        WHEN total_score >= 60 THEN 'HIGH FIT'
        WHEN total_score >= 40 THEN 'MEDIUM FIT'
        ELSE 'LOW FIT'
    END,
    updated_at = NOW();


UPDATE public.opportunity_scores os
SET historical_competition_score =
    CASE
        WHEN h.historical_contracts = 0 THEN 10
        WHEN h.historical_contracts <= 5 THEN 10
        WHEN h.historical_contracts <= 15 THEN 8
        WHEN h.historical_contracts <= 30 THEN 6
        WHEN h.historical_contracts <= 50 THEN 4
        ELSE 2
    END,
    updated_at = NOW()
FROM (
    SELECT
        o.notice_id,
        COUNT(DISTINCT ca.piid) AS historical_contracts
    FROM public.opportunities o
    LEFT JOIN public.contract_awards ca
        ON ca.naics_code = o.naics_code
    GROUP BY o.notice_id
) h
WHERE os.notice_id = h.notice_id;


UPDATE public.opportunity_scores
SET
    classification =
        CASE
            WHEN total_score >= 60
                 AND deadline_score = 5
                 AND naics_score = 20
            THEN 'BID'

            WHEN total_score >= 60
            THEN 'REVIEW'

            WHEN total_score >= 40
            THEN 'REVIEW'

            ELSE 'NO-BID'
        END,

    bid_no_bid_reason =
        CASE
            WHEN total_score >= 60
                 AND deadline_score = 5
                 AND naics_score = 20
            THEN 'Strong fit with exact NAICS match and active deadline.'

            WHEN total_score >= 60
                 AND deadline_score = 5
                 AND naics_score < 20
            THEN 'Strong overall fit but exact NAICS match is not established.'

            WHEN total_score >= 40
                 AND deadline_score = 5
            THEN 'Moderate fit; solicitation requirements and eligibility require review.'

            WHEN deadline_score = 0
            THEN 'Opportunity deadline has passed or is inactive.'

            ELSE
                'Low overall fit based on current scoring criteria.'
        END,

    updated_at = NOW();
"""


def main():
    print("=" * 70)
    print("GOVCON AI — AUTOMATIC SCORING")
    print("=" * 70)

    print("\nConnecting to Supabase...")

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    try:
        cursor = conn.cursor()

        print("Database connection successful.")
        print("Running Stage 5 scoring engine...")

        cursor.execute(SCORING_SQL)

        conn.commit()

        cursor.execute("""
            SELECT
                COUNT(*) AS total_opportunities,
                COUNT(*) FILTER (WHERE classification = 'BID') AS bid_count,
                COUNT(*) FILTER (WHERE classification = 'REVIEW') AS review_count,
                COUNT(*) FILTER (WHERE classification = 'NO-BID') AS no_bid_count,
                ROUND(AVG(total_score), 2) AS average_score
            FROM public.opportunity_scores;
        """)

        result = cursor.fetchone()

        print("\n" + "=" * 70)
        print("SCORING COMPLETE")
        print("=" * 70)

        print(f"Total opportunities : {result[0]}")
        print(f"BID                 : {result[1]}")
        print(f"REVIEW              : {result[2]}")
        print(f"NO-BID              : {result[3]}")
        print(f"Average score       : {result[4]}")

        cursor.close()

    except Exception as e:
        conn.rollback()
        print("\nERROR:")
        print(e)
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()