# GovCon AI – Government Contract Intelligence & Bid/No-Bid System

## Overview

GovCon AI is an automated Government Contract Intelligence System designed to discover, collect, analyze, score, and prioritize federal contracting opportunities.

The system transforms government contracting data into actionable opportunity intelligence and Bid/No-Bid recommendations.

## Project Architecture

![GovCon AI Architecture](screenshots/architecture.png)

The system connects SAM.gov data ingestion, Python processing, Supabase/PostgreSQL, document intelligence, opportunity scoring, Google Sheets, n8n automation, and Gmail alerts.

The system combines:

- SAM.gov API
- Python
- Pandas
- PostgreSQL / Supabase
- Document parsing
- Capability Statement analysis
- Opportunity scoring
- Historical contract intelligence
- Google Sheets
- n8n
- Gmail

## Core Features

### 1. SAM.gov Opportunity Ingestion

The system connects to the SAM.gov API and retrieves federal contracting opportunities based on configured NAICS codes.

The ingestion process:

- Retrieves active opportunities
- Extracts solicitation information
- Captures NAICS codes
- Captures PSC codes
- Captures agencies
- Captures set-aside information
- Captures response deadlines
- Captures points of contact
- Captures locations
- Stores opportunity descriptions
- Stores raw API data
- Updates existing opportunities
- Avoids duplicate records

### 2. Federal Contract Award Intelligence

Historical federal contract award data is collected and stored in PostgreSQL/Supabase.

The system analyzes:

- Award history
- NAICS codes
- Agencies
- Awardees
- PSC codes
- Competition types
- Set-aside types
- Pricing types
- Geographic information
- Historical competitors

### 3. Opportunity Intelligence

Each opportunity is analyzed for relevance using multiple intelligence factors.

The system evaluates:

- NAICS relevance
- Agency relevance
- PSC/service relevance
- Set-aside compatibility
- Historical contract relevance
- Opportunity status
- Response deadline

### 4. Solicitation & Document Intelligence

The system processes solicitation documents and extracts useful information.

Document intelligence includes:

- Solicitation requirements
- Evaluation criteria
- Compliance requirements
- Submission instructions
- Important dates
- Key deadlines
- Supporting documents

The extracted information is stored in structured PostgreSQL tables.

### 5. Capability Statement Analysis

The company capability statement is used to build a capability profile.

The profile includes:

- NAICS codes
- Core capabilities
- Services
- Past performance
- Experience areas

The capability profile is compared with government opportunities.

### 6. Opportunity Scoring

GovCon AI uses a custom 100-point analytical scoring model.

| Criteria | Weight |
|---|---:|
| NAICS Match | 20 |
| Service Capability Match | 20 |
| Solicitation Requirement Match | 20 |
| Set-Aside / Eligibility Compatibility | 15 |
| Past Performance / Experience Match | 10 |
| Agency & Historical Contract Relevance | 10 |
| Deadline / Opportunity Status | 5 |
| **Total** | **100** |

The scoring model is a custom analytical framework for this project and is not a universal federal contracting rule.

### 7. Bid / No-Bid Intelligence

The system classifies opportunities into:

- BID
- REVIEW
- NO-BID

The classification uses opportunity score, NAICS compatibility, deadline status, and other intelligence factors.

Latest project results:

- 102 opportunities analyzed
- 73 REVIEW
- 29 NO-BID
- 0 BID
- Average score: 42.21

### 8. Production Automation

The production pipeline connects the major components:

```text
SAM.gov API
    ↓
Python Data Ingestion
    ↓
Supabase / PostgreSQL
    ↓
Opportunity Scoring
    ↓
Google Sheets
    ↓
n8n Automation
    ↓
Gmail Alerts
```

The automated pipeline runs:

1. SAM.gov opportunity ingestion
2. Historical award ingestion
3. Opportunity scoring
4. Google Sheets synchronization

### 9. n8n Automation & Alerts

n8n is used for automated opportunity monitoring and alerts.

Workflow:

```text
Schedule Trigger
      ↓
Supabase
      ↓
Filter Relevant Opportunities
      ↓
Code / Format Alert
      ↓
Gmail
```

The workflow identifies relevant opportunities requiring review and sends a consolidated email alert.

## Technology Stack

- Python
- Pandas
- PostgreSQL
- Supabase
- SAM.gov API
- REST APIs
- PyPDF2
- python-docx
- Google Sheets API
- Google Cloud Service Account
- n8n
- Gmail
- GitHub

## Database

The PostgreSQL/Supabase database contains structured intelligence tables including:

- `naics_config`
- `opportunities`
- `contract_awards`
- `solicitation_requirements`
- `solicitation_compliance`
- `solicitation_key_dates`
- `company_capability_profile`
- `opportunity_scoring_weights`
- `opportunity_scores`

The database also contains intelligence views for analyzing agencies, competitors, PSC codes, set-asides, geography, competition, pricing, and opportunity relevance.

## Pipeline Execution

The complete pipeline can be executed with:

```bash
python run_pipeline.py
```

The pipeline executes:

```text
stage1_sam_ingest.py
        ↓
run_scoring.py
        ↓
sync_google_sheets.py
```

## Project Results

Latest successful end-to-end pipeline execution:

```text
Opportunities found: 150
Skipped awarded/closed: 63
New opportunities: 1
Existing opportunities updated: 86

Awards API calls: 4
Awards returned/saved: 400 / 400

Opportunities scored: 102

BID: 0
REVIEW: 73
NO-BID: 29

Average score: 42.21

Google Sheets rows written: 102
```

## Project Screenshots

### SAM.gov / Python Data Ingestion

![SAM.gov Python Data Ingestion](screenshots/samgov-python.png)

### Supabase / PostgreSQL Database

![Supabase Database](screenshots/supabase-database.png)

### Google Sheets Opportunity Intelligence

![Google Sheets Opportunity Intelligence](screenshots/google-sheets.png)

### Project Architecture

![GovCon AI Architecture](screenshots/architecture.png)

## Project Structure

```text
govcon-ai-samgov-contract-intelligence/
│
├── screenshots/
│   ├── architecture.png
│   ├── samgov-python.png
│   ├── supabase-database.png
│   └── google-sheets.png
│
├── stage1_sam_ingest.py
├── stage1_sam_ingest_updated.py
├── stage4_document_parser.py
├── run_scoring.py
├── run_pipeline.py
├── sync_google_sheets.py
├── sync_to_google_sheets.py
├── README.md
└── .gitignore
```

## Security

Sensitive credentials are intentionally excluded from the repository.

The following files are not committed:

```text
.env
google_service_account.json
```

API keys, database credentials, service-account credentials, and other secrets should never be uploaded to GitHub.

## Portfolio Purpose

This project demonstrates practical experience with:

- Government contracting data
- Federal procurement intelligence
- API integration
- Python automation
- Data engineering
- PostgreSQL / Supabase
- Document intelligence
- Opportunity scoring
- Business intelligence
- Google Sheets automation
- n8n workflow automation
- Automated email alerts

## Author
**Abdul Samad**

Government Contracting | Data Analytics | Python | SQL | Power BI | n8n | AI Automation
**Abdul Samad**

Government Contracting | Data Analytics | Python | SQL | Power BI | n8n | AI Automation
