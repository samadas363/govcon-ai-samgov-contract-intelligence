import os
import json
import re
import requests
import psycopg2
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv
from PyPDF2 import PdfReader
from docx import Document

load_dotenv()

SAM_API_KEY = os.getenv("SAM_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if not SAM_API_KEY:
    raise ValueError("SAM_API_KEY not found in .env")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in .env")


def download_document(url):
    try:
        response = requests.get(
            url,
            headers={"X-Api-Key": SAM_API_KEY},
            timeout=60
        )

        if response.status_code != 200:
            return None, f"HTTP {response.status_code}"

        return response.content, None

    except Exception as e:
        return None, str(e)


def extract_pdf_text(content):
    try:
        reader = PdfReader(BytesIO(content))
        pages = []

        for page in reader.pages:
            text = page.extract_text()

            if text:
                pages.append(text)

        return "\n".join(pages).strip()

    except Exception as e:
        return f"[PDF extraction error: {e}]"


def extract_docx_text(content):
    try:
        document = Document(BytesIO(content))

        paragraphs = []

        for paragraph in document.paragraphs:
            if paragraph.text.strip():
                paragraphs.append(paragraph.text.strip())

        return "\n".join(paragraphs).strip()

    except Exception as e:
        return f"[DOCX extraction error: {e}]"


def detect_document_type(content):
    if content.startswith(b"%PDF"):
        return "PDF"

    if content.startswith(b"PK"):
        return "DOCX"

    return "UNKNOWN"


def parse_document(content):
    document_type = detect_document_type(content)

    if document_type == "PDF":
        return "PDF", extract_pdf_text(content)

    if document_type == "DOCX":
        return "DOCX", extract_docx_text(content)

    return "UNKNOWN", ""


def extract_key_dates(text):
    rules = {
        "response_deadline": [
            "response due",
            "response deadline",
            "offer due",
            "proposal due",
            "due date",
            "closing date"
        ],

        "questions_deadline": [
            "questions due",
            "question deadline",
            "questions deadline",
            "questions must be submitted"
        ],

        "amendment_date": [
            "amendment date",
            "date of amendment",
            "effective date"
        ],

        "performance_start": [
            "performance start",
            "period of performance begins",
            "start date"
        ],

        "performance_end": [
            "performance end",
            "period of performance ends",
            "end date"
        ]
    }

    date_patterns = [
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
        r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+\d{1,2},\s+\d{4}\b"
    ]

    results = []
    seen = set()
    text_lower = text.lower()

    for date_type, keywords in rules.items():

        for keyword in keywords:

            start = 0

            while True:

                position = text_lower.find(keyword, start)

                if position == -1:
                    break

                section_start = max(0, position - 100)
                section_end = min(
                    len(text),
                    position + 500
                )

                section = text[
                    section_start:section_end
                ]

                section = re.sub(
                    r"\s+",
                    " ",
                    section
                ).strip()

                dates = []

                for pattern in date_patterns:
                    dates.extend(
                        re.findall(
                            pattern,
                            section,
                            flags=re.IGNORECASE
                        )
                    )

                for date_text in dates:

                    key = (
                        date_type,
                        date_text,
                        section
                    )

                    if key in seen:
                        continue

                    seen.add(key)

                    date_value = None

                    formats = [
                        "%m/%d/%Y",
                        "%m/%d/%y",
                        "%m-%d-%Y",
                        "%m-%d-%y",
                        "%B %d, %Y"
                    ]

                    for fmt in formats:

                        try:
                            date_value = datetime.strptime(
                                date_text,
                                fmt
                            )

                            break

                        except ValueError:
                            continue

                    results.append({
                        "date_type": date_type,
                        "date_value": date_value,
                        "date_text": date_text,
                        "context": section
                    })

                start = position + len(keyword)

    return results


def save_key_dates(
    cursor,
    notice_id,
    source_document,
    key_dates
):

    for item in key_dates:

        cursor.execute(
            """
            INSERT INTO public.solicitation_key_dates (
                notice_id,
                date_type,
                date_value,
                date_text,
                source_document
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                notice_id,
                item["date_type"],
                item["date_value"],
                item["date_text"],
                source_document
            )
        )


def main():

    print("=" * 70)
    print("STAGE 4.5 - DEADLINE & KEY-DATE INTELLIGENCE")
    print("=" * 70)

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            notice_id,
            title,
            attachments
        FROM public.opportunities
        WHERE attachments IS NOT NULL
        ORDER BY response_deadline ASC NULLS LAST
        LIMIT 3;
    """)

    opportunities = cursor.fetchall()

    total_documents = 0
    successful_documents = 0
    total_dates = 0

    print(f"Opportunities selected: {len(opportunities)}")
    print()

    for notice_id, title, attachments in opportunities:

        print("-" * 70)
        print(f"Notice ID: {notice_id}")
        print(f"Title: {title}")

        if not attachments:
            continue

        try:

            if isinstance(attachments, str):
                attachments = json.loads(attachments)

        except Exception:

            print("Could not parse attachments.")
            continue

        for url in attachments:

            total_documents += 1

            content, error = download_document(url)

            if error:
                print(f"Download failed: {error}")
                continue

            document_type, text = parse_document(content)

            if not text or text.startswith("["):
                continue

            successful_documents += 1

            key_dates = extract_key_dates(text)

            save_key_dates(
                cursor,
                notice_id,
                url,
                key_dates
            )

            total_dates += len(key_dates)

            print(
                f"{document_type}: "
                f"{len(key_dates)} key dates"
            )

            conn.commit()

    cursor.close()
    conn.close()

    print()
    print("=" * 70)
    print("STAGE 4.5 SUMMARY")
    print("=" * 70)
    print(f"Documents processed:    {total_documents}")
    print(f"Documents parsed:       {successful_documents}")
    print(f"Key dates extracted:    {total_dates}")
    print("=" * 70)


if __name__ == "__main__":
    main()