import os
import json
import re
import html
from datetime import date, datetime

import psycopg2
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

GOOGLE_SHEET_ID = "1EN1r3x3xpHmW8tbGDe523e1tJ5x3TZqIWy-KFJT06R8"
WORKSHEET_NAME = "Opportunities"
SERVICE_ACCOUNT_FILE = "google_service_account.json"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ============================================================
# CLEAN HTML FROM DESCRIPTION
# ============================================================

def clean_html(text):

    if text is None:
        return ""

    text = str(text)

    if not text.strip():
        return ""

    # Decode HTML entities
    text = html.unescape(text)

    # Convert <br> tags to line breaks
    text = re.sub(
        r"<\s*br\s*/?\s*>",
        "\n",
        text,
        flags=re.IGNORECASE
    )

    # Convert block HTML tags to line breaks
    text = re.sub(
        r"<\s*/?\s*(p|div|li|ul|ol|tr|h1|h2|h3|h4|h5|h6)\s*[^>]*>",
        "\n",
        text,
        flags=re.IGNORECASE
    )

    # Remove remaining HTML tags
    text = re.sub(
        r"<[^>]+>",
        "",
        text
    )

    # Replace non-breaking spaces
    text = text.replace("\xa0", " ")

    # Normalize spaces
    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    # Clean lines
    lines = []

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        # Remove long +++++ separator lines
        if re.fullmatch(r"\+{5,}", line):
            continue

        lines.append(line)

    # Join lines
    text = "\n".join(lines)

    # Remove excessive blank lines
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


# ============================================================
# CONVERT DATABASE VALUES
# ============================================================

def convert_value(value, column_name=None):

    if value is None:
        return ""

    # Clean HTML description
    if (
        column_name
        and column_name.lower() == "description"
    ):
        return clean_html(value)

    # Convert JSON values
    if isinstance(value, (dict, list)):

        return json.dumps(
            value,
            ensure_ascii=False
        )

    # Convert date/datetime
    if isinstance(value, (datetime, date)):

        return value.isoformat()

    return str(value)


# ============================================================
# DATABASE CONNECTION
# ============================================================

def connect_database():

    database_url = os.getenv(
        "DATABASE_URL"
    )

    if not database_url:

        raise RuntimeError(
            "DATABASE_URL was not found in .env"
        )

    try:

        connection = psycopg2.connect(
            database_url
        )

        print(
            "Database connection successful."
        )

        return connection

    except Exception as e:

        print(
            "Database connection failed."
        )

        print(
            f"Error: {e}"
        )

        raise


# ============================================================
# FETCH OPPORTUNITIES
# ============================================================

def fetch_opportunities(connection):

    query = """
        SELECT *
        FROM opportunities
        ORDER BY response_deadline ASC NULLS LAST;
    """

    try:

        cursor = connection.cursor()

        cursor.execute(query)

        rows = cursor.fetchall()

        columns = [
            description[0]
            for description in cursor.description
        ]

        cursor.close()

        print(
            f"Opportunities read from Supabase: {len(rows)}"
        )

        return columns, rows

    except Exception as e:

        print(
            "Failed to read opportunities."
        )

        print(
            f"Error: {e}"
        )

        raise


# ============================================================
# CONNECT TO GOOGLE SHEETS
# ============================================================

def connect_google_sheet():

    if not os.path.exists(
        SERVICE_ACCOUNT_FILE
    ):

        raise FileNotFoundError(
            f"Service account file not found: "
            f"{SERVICE_ACCOUNT_FILE}"
        )

    try:

        credentials = (
            Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE,
                scopes=GOOGLE_SCOPES
            )
        )

        client = gspread.authorize(
            credentials
        )

        spreadsheet = client.open_by_key(
            GOOGLE_SHEET_ID
        )

        print(
            f"Google Sheet connected: "
            f"{spreadsheet.title}"
        )

        worksheet = spreadsheet.worksheet(
            WORKSHEET_NAME
        )

        print(
            f"Worksheet connected: "
            f"{WORKSHEET_NAME}"
        )

        return worksheet

    except Exception as e:

        print(
            "Failed to connect to Google Sheets."
        )

        print(
            f"Error: {e}"
        )

        raise


# ============================================================
# BUILD SHEET DATA
# ============================================================

def build_sheet_data(
    columns,
    rows
):

    sheet_data = []

    # Header row
    sheet_data.append(
        columns
    )

    # Data rows
    for row in rows:

        converted_row = []

        for index, value in enumerate(row):

            column_name = columns[index]

            converted_value = convert_value(
                value,
                column_name
            )

            converted_row.append(
                converted_value
            )

        sheet_data.append(
            converted_row
        )

    return sheet_data


# ============================================================
# COLUMN NUMBER TO LETTER
# ============================================================

def column_letter(
    column_number
):

    result = ""

    while column_number > 0:

        column_number, remainder = divmod(
            column_number - 1,
            26
        )

        result = (
            chr(65 + remainder)
            + result
        )

    return result


# ============================================================
# WRITE DATA TO GOOGLE SHEETS
# ============================================================

def write_to_google_sheet(
    worksheet,
    sheet_data
):

    try:

        # Clear existing data
        worksheet.clear()

        # Write data using current gspread syntax
        worksheet.update(
            range_name="A1",
            values=sheet_data,
            value_input_option="RAW"
        )

        print(
            f"Google Sheets rows written: "
            f"{len(sheet_data) - 1}"
        )

    except Exception as e:

        print(
            "Failed to write data to Google Sheets."
        )

        print(
            f"Error: {e}"
        )

        raise


# ============================================================
# FORMAT GOOGLE SHEET
# ============================================================

def format_sheet(
    worksheet,
    columns
):

    try:

        # ----------------------------------------------------
        # Freeze first row
        # ----------------------------------------------------

        worksheet.freeze(
            rows=1
        )

        # ----------------------------------------------------
        # Find last column
        # ----------------------------------------------------

        last_column = column_letter(
            len(columns)
        )

        # ----------------------------------------------------
        # Format header
        # ----------------------------------------------------

        worksheet.format(
            f"A1:{last_column}1",
            {
                "textFormat": {
                    "bold": True
                },
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP"
            }
        )

        # ----------------------------------------------------
        # Find description column
        # ----------------------------------------------------

        description_index = None

        for index, column_name in enumerate(columns):

            if column_name.lower() == "description":

                description_index = (
                    index + 1
                )

                break

        # ----------------------------------------------------
        # Format description column
        # ----------------------------------------------------

        if description_index:

            description_column = (
                column_letter(
                    description_index
                )
            )

            # Wrap description text
            worksheet.format(
                f"{description_column}2:{description_column}",
                {
                    "wrapStrategy": "WRAP",
                    "verticalAlignment": "TOP"
                }
            )

            # Make description wider
            worksheet.spreadsheet.batch_update(
                {
                    "requests": [
                        {
                            "updateDimensionProperties": {
                                "range": {
                                    "sheetId": worksheet.id,
                                    "dimension": "COLUMNS",
                                    "startIndex": (
                                        description_index - 1
                                    ),
                                    "endIndex": (
                                        description_index
                                    )
                                },
                                "properties": {
                                    "pixelSize": 600
                                },
                                "fields": "pixelSize"
                            }
                        }
                    ]
                }
            )

            print(
                f"Description column formatted: "
                f"{description_column}"
            )

        # ----------------------------------------------------
        # Set widths for important columns
        # ----------------------------------------------------

        width_settings = {

            "notice_id": 180,

            "posted_date": 120,

            "notice_type": 140,

            "title": 350,

            "solicitation_number": 180,

            "agency": 220,

            "naics_code": 120,

            "set_aside": 180,

            "response_deadline": 190,

            "place_of_performance": 220,

            "contact_name": 180,

            "contact_email": 240,

            "contact_phone": 160,

            "sam_link": 300,

            "status": 120,

            "psc_code": 120,

            "contract_type": 160,

            "inactive_date": 180

        }

        requests = []

        for index, column_name in enumerate(
            columns
        ):

            column_key = column_name.lower()

            if column_key in width_settings:

                width = width_settings[
                    column_key
                ]

                requests.append(
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": worksheet.id,
                                "dimension": "COLUMNS",
                                "startIndex": index,
                                "endIndex": index + 1
                            },
                            "properties": {
                                "pixelSize": width
                            },
                            "fields": "pixelSize"
                        }
                    }
                )

        if requests:

            worksheet.spreadsheet.batch_update(
                {
                    "requests": requests
                }
            )

        print(
            "Header formatting applied."
        )

        print(
            "Description wrapping applied."
        )

        print(
            "Column widths adjusted."
        )

        print(
            "First row frozen."
        )

    except Exception as e:

        print(
            "Warning: Sheet formatting failed."
        )

        print(
            f"Error: {e}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print(
        "=" * 60
    )

    print(
        "SUPABASE -> GOOGLE SHEETS SYNC"
    )

    print(
        "=" * 60
    )

    print()

    connection = None

    try:

        # ----------------------------------------------------
        # 1. Connect database
        # ----------------------------------------------------

        connection = connect_database()

        # ----------------------------------------------------
        # 2. Fetch opportunities
        # ----------------------------------------------------

        columns, rows = (
            fetch_opportunities(
                connection
            )
        )

        # ----------------------------------------------------
        # 3. Connect Google Sheets
        # ----------------------------------------------------

        worksheet = (
            connect_google_sheet()
        )

        # ----------------------------------------------------
        # 4. Prepare data
        # ----------------------------------------------------

        sheet_data = (
            build_sheet_data(
                columns,
                rows
            )
        )

        print(
            f"Rows prepared for Google Sheets: "
            f"{len(rows)}"
        )

        # ----------------------------------------------------
        # 5. Write data
        # ----------------------------------------------------

        write_to_google_sheet(
            worksheet,
            sheet_data
        )

        # ----------------------------------------------------
        # 6. Format sheet
        # ----------------------------------------------------

        format_sheet(
            worksheet,
            columns
        )

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        print()

        print(
            "=" * 60
        )

        print(
            "SYNC COMPLETED SUCCESSFULLY"
        )

        print(
            "=" * 60
        )

        print()

        print(
            "HTML descriptions cleaned: YES"
        )

        print(
            "Description wrapping: YES"
        )

        print(
            "Description column widened: YES"
        )

        print(
            "Header formatting: YES"
        )

        print(
            "First row frozen: YES"
        )

        print()

    except Exception as e:

        print()

        print(
            "=" * 60
        )

        print(
            "SYNC FAILED"
        )

        print(
            "=" * 60
        )

        print()

        print(
            f"Error: {e}"
        )

        print()

    finally:

        if connection:

            connection.close()

            print(
                "Database connection closed."
            )


# ============================================================
# RUN SCRIPT
# ============================================================

if __name__ == "__main__":
    main()