<div align="center">

# OutreachPilot
### **Autonomous B2B Lead Scraping, AI Intelligence & 1-Click Outreach Engine**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%2B-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Groq AI](https://img.shields.io/badge/AI%20Engine-Groq%20Llama%20%2F%20Qwen-F55036.svg)](https://groq.com/)
[![Tailwind CSS](https://img.shields.io/badge/Frontend-TailwindCSS-38B2AC.svg?logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

**Find verified local businesses. Profile company tech stacks with AI. Match with candidate resumes. Reach out in 1 click.**

[Features](#key-features) | [Architecture](#system-architecture) | [Quick Start](#quick-start) | [Security](#security--privacy-safeguards) | [API Reference](#api-endpoints)

</div>

---

## Executive Overview

**OutreachPilot** is an autonomous, privacy-first technical job outreach and B2B lead generation platform. It automates what normally takes 10+ hours of tedious daily prospecting into a structured, 3-tab workflow:

1. **Precision Scouting:** Discovers live, verified business leads from Google Local / Google Maps across any query and location, filtering out aggregator directories (Yelp, Justdial, YellowPages) and dummy local domains.
2. **Deep Subpage Crawling:** Crawls company websites across `/contact`, `/about`, `/careers`, and `/jobs` in parallel, discovering verified contact emails.
3. **Exclusive HR / Recruitment Email Prioritization:** When talent acquisition emails (`hr@`, `careers@`, `jobs@`, `recruit@`) are detected, OutreachPilot automatically excludes all generic departmental addresses (`info@`, `sales@`, `support@`) and locks in the recruiter as the primary contact.
4. **AI Company Profiling:** Analyzes crawled website copy using **Groq AI** to extract active tech stacks, primary services, and strategic company challenges.
5. **Resume Parsing & Cold Pitch Engine:** Parses uploaded candidate resumes in-memory (zero disk storage) and drafts tailored cold outreach emails and custom cover letters matching candidate achievements to company tech stacks.
6. **Multi-Channel Anti-Spam Dispatch:** Sends emails via **1-Click Gmail Web**, native `mailto:`, or official **Google OAuth 2.0 (Gmail API)** with strict database deduplication to ensure no business is ever emailed twice.

---

## System Architecture

```mermaid
graph TD
    A[Target Keyword & City] --> B[Google Local Lead Scout]
    B -->|SeleniumBase Engine| C[Google Maps udm=local]
    C -->|Genuine Domain Filter| D[(PostgreSQL Leads DB)]
    
    D --> E[Subpage Email Crawler]
    E --> F{HR / Recruiter Email Found?}
    F -->|Yes| G[Lock Priority HR Contact & Drop Generic Info/Sales]
    F -->|No| H[Retain Best Verified Department Address]
    
    G & H --> I[Groq AI Tech Intelligence Engine]
    I --> J[Technical Stack & Services Dossier]
    
    K[Candidate Resume PDF] --> L[In-Memory Text Extractor]
    L --> M[AI Resume Intelligence Engine]
    M --> N[Candidate Strengths & Superpowers]
    
    J & N --> P[Contextual Cold Pitch Engine]
    P --> Q[Tailored Direct Job Proposal]
    
    Q --> R[1-Click Personal Gmail Web]
    Q --> S[Gmail OAuth 2.0 API Dispatch]
    
    R & Q --> T[(Outreach Audit Log & Deduplication)]
```

---

## Key Features

### 1. Real-Time Google Local Lead Scout
* **Live Discovery:** Scrapes real-time Google Maps listings with anti-bot bypass.
* **Stream Monitor:** Live terminal log activity console showing crawl progress, status messages, and discovered businesses in real time.
* **Genuine Domain Protection:** Automatically rejects unverified `.local` or dummy placeholder domains.
* **Clean Address Parser:** Cleans rating numbers, business hours ("Open 24 hours"), and creates direct Google Maps navigation links.

### 2. Dual-View Directory & Multi-Dimensional Filters
* **Flexible Views:** Instantly toggle between **Responsive Cards Grid** (2-column on mobile, 3-column on laptop/desktop) and a compact **Table View**.
* **Real-Time Filtering:** Filter instantly by keyword, city, domain, rating, and email availability.
* **Pagination Controls:** Full numbered pagination with configurable page sizes (12, 24, 48, 96, All).
* **CSV Export:** 1-click export of your verified leads to spreadsheet-compatible CSV files.

### 3. HR & Recruitment Email Prioritization Engine
* **Recruitment Keyword Matching:** Scans email prefixes for `hr@`, `recruit@`, `recruiting@`, `recruiter@`, `job@`, `jobs@`, `career@`, `careers@`, `talent@`, `hiring@`, `work@`, `join@`, and `people@`.
* **Exclusive Exclusion Rule:** If any recruitment email is detected, the crawler excludes all generic departmental emails (`info@`, `contact@`, `sales@`, `support@`) to keep your outreach laser-focused on hiring managers.
* **Smart Primary Assignment:** Automatically sets the HR email as `is_primary = True` for single-click outreach.

### 4. Groq-Powered Deep AI Company Profiling
* Analyzes crawled website content using ultra-fast Groq AI.
* Generates an executive overview, categorized tech stack inventory, services breakdown, and strategic technical pain points candidates can solve.
* Calibrated strictly to stay within Groq free-tier rate limits (OTPM token budget).

### 5. Privacy-First In-Memory Resume Ingestion
* Supports **PDF**, **TXT**, and **Markdown** resumes.
* **Zero Disk Persistence:** Resumes are parsed in volatile memory and purged immediately after analysis.
* Extracts core technical competencies, candidate superpowers, years of experience, and quantified achievements.

### 6. 1-on-1 Personalized Cold Pitch & Outreach Hub
* **Authentic Talent Inquiry:** Generates personalized cold job opportunity emails and tailored cover letters matching candidate achievements to company tech stacks (zero corporate sales fluff).
* **Multi-Channel Dispatch:**
  * **1-Click Gmail Web:** Opens Gmail with pre-filled recipient, subject, and body (requires zero passwords).
  * **Google OAuth 2.0:** Direct dispatch through official Gmail API with user authorization.
  * **Native Mailto:** Opens your operating system's default email client.
* **Strict Deduplication:** Tracks contact history in PostgreSQL to guarantee no company is ever messaged twice.

---

## Technology Stack

| Layer | Component | Description |
| :--- | :--- | :--- |
| **Backend** | Python 3.11+, FastAPI, Uvicorn | High-performance asynchronous API server |
| **Database** | PostgreSQL 15+, SQLAlchemy 2.0 | Relational database with automated migrations |
| **Browser Engine** | SeleniumBase (Undetected Chrome) | Google Maps discovery with CAPTCHA bypass |
| **Crawler** | HTTPX, BeautifulSoup4 | Asynchronous parallel website subpage extraction |
| **AI Intelligence** | Groq Cloud API (`qwen/qwen3.8-27b`) | High-speed LLM inference for profiles & pitches |
| **Auth & Mail** | Google OAuth 2.0, Gmail API | Secure token-based sending & session handling |
| **PDF Processing** | PyPDF (`PdfReader`) | In-memory text extraction from candidate resumes |
| **Frontend** | Vanilla HTML5, Tailwind CSS, Lucide Icons | Responsive matte-slate dark dashboard |

---

## Quick Start

### 1. Prerequisites
* **Python 3.11+** installed.
* **Google Chrome** installed (for browser automation).
* **PostgreSQL** running locally or via cloud (e.g. Neon, Supabase).
* A free **[Groq API Key](https://console.groq.com/)**.

### 2. Clone the Repository
```bash
git clone https://github.com/<your-username>/outreachPilot.git
cd outreachPilot
```

### 3. Create a Virtual Environment & Install Dependencies
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Populate your `.env` with your PostgreSQL database URL, Groq API key, and optional Google OAuth credentials.

### 5. Launch the Application
```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser to: **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## Security & Privacy Safeguards

OutreachPilot includes built-in security features:

- **Server-Side Request Forgery (SSRF) Protection:** The website crawler validates all URLs against private IP blocks (RFC 1918), loopback (`127.0.0.0/8`), link-local (`169.254.0.0/16`), and internal cloud metadata endpoints before issuing requests.
- **Encrypted Session Management:** Authentication cookies are cryptographically signed with `HMAC-SHA256` and set with `HttpOnly`, `SameSite=Lax`, and secure session handling.
- **Rate Limiting:** Sliding-window rate limiters protect AI endpoints, resume parsing, and email dispatches against automated abuse.
- **Safety Sandbox Mode (`DEV_MODE`):** When active, all outreach emails are redirected to `DEV_OVERRIDE_EMAIL` to prevent unintended emails during testing.
- **In-Memory Privacy:** Resumes are never stored on disk. Files are processed in memory and purged immediately after parsing.

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/scrape` | Trigger real-time Google Maps lead scout job |
| `GET` | `/api/progress` | Poll real-time scraping progress and terminal logs |
| `GET` | `/api/companies` | Fetch all verified leads with filtering & pagination |
| `POST` | `/api/enrich` | Crawl company subpages & generate AI intelligence profile |
| `POST` | `/api/resume/upload` | In-memory upload & AI candidate profile parsing |
| `POST` | `/api/pitch/generate` | Generate hyper-personalized cold outreach pitch |
| `POST` | `/api/outreach/send` | Dispatch verified email via Gmail OAuth |
| `GET` | `/auth/google/login` | Initiate Google OAuth 2.0 authentication flow |
| `GET` | `/auth/google/callback`| Handle OAuth 2.0 authorization code exchange |

---

## Repository Structure

```
outreachPilot/
├── app.py                  # Main FastAPI application & route controllers
├── config.py               # Environment configuration & SSRF security validator
├── db.py                   # SQLAlchemy models & PostgreSQL connection pool
├── ai_agent.py             # Groq AI integration (Profiles, Pitches, Resumes)
├── enricher.py             # Subpage crawler & HR email prioritization engine
├── outreach.py             # Gmail OAuth 2.0 & multi-channel dispatch engine
├── scraper_engine.py       # Google Local scraping engine (Undetected Chrome)
├── static/
│   ├── css/
│   │   └── style.css       # Matte-slate dark mode design system & responsive rules
│   └── js/
│       └── app.js          # Reactive frontend controller & state machine
├── templates/
│   └── index.html          # Semantic HTML5 UI dashboard
├── .env.example            # Environment variables configuration template
├── .gitignore              # Git ignore rules (protects .env and caches)
├── requirements.txt        # Python dependency manifest
├── ruff.toml               # Linter configuration
└── README.md               # Project documentation
```

---

## License

This project is licensed under the **MIT License**: feel free to use, modify, and distribute it for personal or commercial projects.
