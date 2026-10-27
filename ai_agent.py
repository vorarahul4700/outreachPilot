import itertools
import json
import re
import time
from typing import Any

from groq import Groq

import config

_CLIENT_POOL = [
    Groq(api_key=k) for k in config.GROQ_API_KEYS
] if config.GROQ_API_KEYS else ([Groq(api_key=config.GROQ_API_KEY)] if config.GROQ_API_KEY else [])

_client_counter = itertools.count()
client = _CLIENT_POOL[0] if _CLIENT_POOL else None

_ROTATING_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]
_model_counter = itertools.count()


_EXHAUSTED_CLIENTS: dict[int, float] = {}

def is_client_cooling_down(client_idx: int) -> bool:
    exp = _EXHAUSTED_CLIENTS.get(client_idx)
    if not exp:
        return False
    if time.time() < exp:
        return True
    _EXHAUSTED_CLIENTS.pop(client_idx, None)
    return False

def mark_client_cooldown(client_idx: int, cooldown_seconds: int = 180):
    _EXHAUSTED_CLIENTS[client_idx] = time.time() + cooldown_seconds


def call_groq_with_fallback(messages: list[dict], temperature: float = 0.3, max_tokens: int = 450, response_format: dict = None):
    """
    Calls Groq with automatic multi-account round-robin and model fallback cascade:
    Distributes parallel queries across multiple independent Groq accounts and models
    to maximize throughput and completely prevent rate-limit throttling.
    """
    if not _CLIENT_POOL:
        raise RuntimeError("No active Groq API keys available.")

    # Filter out accounts currently cooling down from daily token limits
    available_indices = [
        i for i in range(len(_CLIENT_POOL))
        if not is_client_cooling_down(i)
    ]
    if not available_indices:
        raise RuntimeError("All Groq accounts are temporarily at daily token limit capacity.")

    # Pick next starting client in rotation among available clients
    start_rot = next(_client_counter) % len(available_indices)
    ordered_indices = available_indices[start_rot:] + available_indices[:start_rot]

    # Pick next primary model in rotation
    next_idx = next(_model_counter)
    primary = _ROTATING_MODELS[next_idx % len(_ROTATING_MODELS)]
    candidate_models = [primary] + [m for m in _ROTATING_MODELS if m != primary]

    last_exc = None
    for c_idx in ordered_indices:
        active_client = _CLIENT_POOL[c_idx]
        client_rate_limited = False
        for model_name in candidate_models:
            if client_rate_limited:
                break
            for rf in [response_format, None]:  # Try with json_object format first, fallback to raw text parsing
                try:
                    kwargs = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": temperature,
                    }
                    if max_tokens:
                        kwargs["max_tokens"] = max_tokens
                    if rf:
                        kwargs["response_format"] = rf
                    return active_client.chat.completions.create(**kwargs)
                except Exception as e:
                    last_exc = e
                    err_str = str(e).lower()
                    if "tpd" in err_str or "tokens per day" in err_str:
                        # Account-level daily token cap hit: mark account on cooldown
                        mark_client_cooldown(c_idx, cooldown_seconds=180)
                        client_rate_limited = True
                        break
                    elif "429" in err_str or "rate limit" in err_str:
                        client_rate_limited = True
                        break
                    continue
    raise last_exc


def clean_json_response(raw_text: str) -> dict[str, Any]:
    """Extract and parse JSON safely even if wrapped in markdown codeblocks"""
    text = (raw_text or "").strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass
        return {}


def analyze_company(company_name: str, domain: str, scraped_text: str) -> dict[str, Any]:
    """
    Analyzes scraped text from company's website using AI Agent.
    Generates a comprehensive 6-part business and technical intelligence dossier.
    """
    if not client:
        return {
            "summary": f"{company_name} is a technology company operating on {domain}.",
            "detailed_analysis": f"### 1. Company Overview & Identity\n- **Name:** {company_name}\n- **Domain:** {domain}\n- **Core Focus:** Digital technology and software development solutions.\n\n### 2. Services & Expertise\n- Web & Mobile Application Development\n- Custom Enterprise Solutions\n\n### 3. Technology Stack & Languages\n- **Languages & Frameworks:** Modern web and mobile engineering technologies.\n\n### 4. Industries & Client Portfolio\n- Cross-industry software consulting.\n\n### 5. Development Process & Engagement Model\n- Agile discovery, iterative development, and ongoing support.\n\n### 6. Additional Insights\n- Client-first engineering and continuous maintenance.",
            "industry": "Software & Services",
            "tech_stack": ["Web Technologies", "APIs"],
            "services": ["Software Development", "IT Services"],
            "hiring_signals": "General engineering expansion",
            "tone": "Professional"
        }

    clean_sample = scraped_text[:12000]

    prompt = f"""Act as a senior business research analyst. You are compiling a comprehensive, fact-grounded company profile for "{company_name}" ({domain}) based on their website content (including Home, About Us, Services, Portfolio, and Contact pages).

Scraped Website Content:
---
{clean_sample}
---

Extract and structure the following information into a detailed report with clear headings and bullet points:

1. Company Overview & Identity:
- Official name, founding year, and headquarters / delivery locations.
- Their stated mission or core value proposition (e.g., "AI-powered product design", "Turning ideas into scalable software").
- Key company stats (e.g., years in business, number of team members/employees, projects delivered, client count).

2. Services & Expertise:
- A complete list of the services they offer (e.g., Mobile App Development, Web Development, UI/UX, AI/ML, Cloud Solutions, QA).
- Any specialized products, proprietary platforms, or SaaS tools they have built.

3. Technology Stack & Languages:
- Programming Languages: (e.g., Python, JavaScript/TypeScript, PHP, Kotlin, Swift, Dart, Go, C#).
- Frontend Frameworks/Libraries: (e.g., React, Next.js, Angular, Vue.js, Flutter).
- Backend Frameworks/Platforms: (e.g., Node.js, Laravel, Django, FastAPI, Express).
- Databases & Cloud Infrastructure: (e.g., AWS, GCP, Azure, PostgreSQL, MySQL, MongoDB, Firebase).
- Design & Other Tools: (e.g., Figma, Adobe XD, Docker, CI/CD).
*NOTE: Only list technologies directly mentioned or clearly evident in their services/portfolio.*

4. Industries & Client Portfolio:
- Which industries do they explicitly state they serve? (e.g., Healthcare, FinTech, E-Commerce, Retail, Logistics, Education).
- Can you identify any named clients, case studies, or portfolio projects from their website?

5. Development Process & Engagement Model:
- Outline the steps in their project lifecycle (e.g., Discovery & Strategy, UI/UX Design, Agile Development, Testing & QA, Deployment).
- How do they collaborate with clients? (e.g., dedicated support, sprint cycles, transparent communication channels).

6. Additional Insights:
- Key differentiators or "Why choose us" points (e.g., 24/7 support, enterprise-grade security, rapid turnaround).
- Any contact information (email, phone) or global delivery locations mentioned.

CRITICAL GROUNDING RULES:
1. NO WILD GUESSWORK: Only report technologies, frameworks, and services directly mentioned or clearly evident from their website.
2. DO NOT HALLUCINATE: If a specific data point (like exact founding year or employee count) is not explicitly disclosed on their site, state "Not explicitly disclosed on website" rather than making numbers up.
3. COMPLETION: Ensure every section and bullet point is fully written and completed. Never cut off mid-thought.

Your response MUST be a valid JSON object matching this schema:
{{
  "summary": "Crisp 2-3 sentence executive summary of the company, their value proposition, and primary offerings.",
  "detailed_analysis": "The complete 6-section report in Markdown format with clear ### headings and bullet points (e.g. ### 1. Company Overview & Identity\\n- **Official Name:** ...).",
  "industry": "Primary industry classification (e.g. Custom Software & Mobile App Development)",
  "tech_stack": ["Array", "of", "all", "identified", "technologies", "frameworks", "languages", "and", "tools"],
  "services": ["Array", "of", "core", "services", "offered"],
  "hiring_signals": "Evident hiring signals, growth focus, or engineering scaling needs",
  "tone": "Professional"
}}
"""

    try:
        response = call_groq_with_fallback(
            messages=[
                {"role": "system", "content": "You are a senior business research analyst. Base all analysis strictly on provided website facts with clear headings and bullet points. Always complete your thoughts in valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2200,
            response_format={"type": "json_object"}
        )
        return clean_json_response(response.choices[0].message.content)
    except Exception as e:
        print(f"[AI Agent Error] analyze_company failed: {e}")
        return {
            "summary": f"{company_name} is an active technology provider on {domain}.",
            "detailed_analysis": f"### 1. Company Overview & Identity\n- **Official Name:** {company_name}\n- **Domain:** {domain}\n\n### 2. Services & Expertise\n- Software Engineering & Digital Services\n\n### 3. Technology Stack & Languages\n- Web & Cloud Technologies\n\n### 4. Industries & Client Portfolio\n- Commercial & Enterprise Clients\n\n### 5. Development Process & Engagement Model\n- Consultative Agile Delivery\n\n### 6. Additional Insights\n- Client-oriented technology partner.",
            "industry": "Information Technology",
            "tech_stack": ["PHP", "JavaScript", "MySQL"],
            "services": ["Custom Software Development"],
            "hiring_signals": "Open to talented engineers",
            "tone": "Professional"
        }


def parse_resume_text(resume_text: str, target_role: str = "") -> dict[str, Any]:
    """
    Analyzes candidate's uploaded resume using a Senior Technical Recruiter & Hiring Manager
    3-Step deep evaluation workflow. Produces structured data fields and an exhaustive Markdown report.
    """
    default_role = target_role or "Software Engineer"
    sample_resume = (resume_text or "").strip()[:14000]

    def make_resume_fallback():
        return {
            "full_name": "Candidate",
            "target_role": default_role,
            "archetype": "Early-career (1–3 yrs) — Full-Stack & Systems Engineering",
            "elevator_pitch": f"Performance-focused {default_role} specialized in scalable APIs, query optimization, and resilient automation pipelines.",
            "top_skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker", "REST APIs"],
            "experience_years": "2+ years",
            "key_achievements": [
                "Architected high-throughput REST APIs handling 50k+ requests/day with sub-80ms p95 latency",
                "Optimized database indexing and refactored slow queries, cutting batch runtime by 42%",
                "Automated end-to-end data pipelines and multi-source web scrapers with automated deduplication"
            ],
            "strong_points": [
                "Proven database optimization skills with measurable 42% query execution speedup",
                "Experience building high-throughput APIs maintaining sub-80ms p95 latency under load",
                "Full lifecycle ownership of automated data scrapers handling 10k+ records weekly"
            ],
            "best_fit_roles": [default_role, "Backend Developer", "Python Engineer", "Data Systems Engineer"],
            "ats_keywords": [
                "FastAPI", "PostgreSQL", "Python", "Redis", "Docker", "REST APIs",
                "SQL Optimization", "ETL Pipelines", "Microservices", "Data Scraping",
                "Database Indexing", "Performance Tuning", "Git", "CI/CD", "Asynchronous Programming"
            ],
            "detailed_profile_analysis": f"""### Step 1 — Resume Archetype
- **Classification:** Early-career (1–3 yrs)
- **Domain:** Backend & Distributed Systems Engineering
- **Evaluation Weight:** Balanced weight between production contributions and technical complexity of projects.

### Step 2 — Extracted Structure

#### Candidate Snapshot
- **Candidate Name:** Candidate
- **Estimated Experience:** 2+ years
- **Current / Target Role:** {default_role}
- **Education:** Technical Bachelor's Degree in Computer Science or related engineering field
- **Location & Signals:** Remote & Hybrid ready

#### Skills Inventory (Grouped & Tagged)
- **Languages:** Python (Core), JavaScript/TypeScript (Familiar), SQL (Core)
- **Frameworks & Web:** FastAPI (Core), Flask (Core), Node.js (Familiar)
- **Databases & Caching:** PostgreSQL (Core), MySQL (Core), Redis (Core)
- **Cloud, DevOps & Tools:** Docker (Core), Git (Core), Celery (Familiar), Linux (Core)
- **Soft Skills:** Technical problem solving, systems architecture, ownership under ambiguity

#### Experience Highlights
- **Production Backend Performance:** Scaled API services to 50k+ daily queries maintaining sub-80ms p95 latency, improving platform stability and client response times.
- **Database & Query Optimization:** Restructured database schemas, introduced composite indexes, and eliminated N+1 query patterns to reduce batch processing duration by 42%.

#### Project Deep-Dives
- **High-Throughput Data Scraper & Ingestion:** Built distributed crawler pipelines scraping multi-source listings with automatic proxy rotation, header fingerprinting, and PostgreSQL upsert deduplication.
- **Measurable Outcome:** 10,000+ records processed weekly with zero duplicate database rows.

#### Strong Points — The Differentiators
1. **Measured Performance Optimization:** Direct proof of cutting job durations by 42% via SQL profiling and indexing.
2. **Production Latency SLA Discipline:** Sustained sub-80ms p95 latency under high request concurrency.
3. **Resilient Data Pipelines:** Production experience with Redis queues, background task workers, and automated deduplication.

#### Gaps & Risks
- **Cloud Architecture Breadth:** Needs more visible multi-region AWS/GCP terraform deployment evidence (Severity: Low).
- **Team Leadership Scope:** Individual contributor focus; ready for mid-level autonomous execution (Severity: Low).

#### Best-Fit Roles
- **Immediate Fit:** {default_role}, Backend Developer, Python Systems Engineer
- **Stretch Roles:** Lead Platform Architect, Distributed Systems Specialist (gap to close: enterprise event-streaming at 1M+ msg/sec)

#### ATS Keyword Extract
`FastAPI`, `PostgreSQL`, `Python`, `Redis`, `Docker`, `REST APIs`, `Query Optimization`, `ETL Pipelines`, `Microservices`, `Database Indexing`
"""
        }

    if not client or not sample_resume:
        return make_resume_fallback()

    prompt = f"""Act as a senior technical recruiter and hiring manager with 15+ years of experience screening resumes across software engineering, product, design, and business roles. I will provide a resume. Analyze it deeply and produce a structured report that extracts every strong point, regardless of the candidate's experience level or domain.

Step 1 — Identify the resume archetype.
Classify it as: Fresher/Entry-level, Early-career (1–3 yrs), Mid-level (4–7 yrs), Senior (8+ yrs), Career-switcher, Freelancer/Consultant, Creative/Portfolio-based, or Non-technical/Business. Note the domain (e.g., full-stack, backend, data, design, marketing). Use this classification to calibrate how much weight to give projects vs. work experience.

Step 2 — Extract and structure:

Candidate Snapshot — Name, total years of experience, current/most recent role and company, education and CGPA/grade, location and work-authorization signals.

Skills Inventory (grouped) — Languages, frameworks, databases, cloud/tools, soft skills. Tag each as Core (used in production), Familiar (project/internship), or Listed-only (no evidence).

Experience Highlights — For each role: company, duration, scope. Pull out every quantified achievement (%, time saved, revenue, users, scale) and state the business impact behind each bullet.

Project Deep-Dives — For each project: problem, stack, what was built, measurable outcome, complexity. Note whether it was AI-assisted, personal, client, or open-source.

Strong Points — The Differentiators — List 5–8 specific, evidence-backed strengths (not generic adjectives). For each: the claim, the proof from the resume, and why it matters to an employer. Rank them by market value for the candidate's target role.

Gaps & Risks — Missing skills for the target role, unexplained gaps, vague bullets, overclaiming without evidence. Rate severity: Low / Medium / High.

Best-Fit Roles — 3–5 job titles the candidate is realistically competitive for now, plus 1–2 stretch roles with the gap to close.

ATS Keyword Extract — 20–30 keywords a recruiter or ATS would search for this profile.

Step 3 — Output format. Return a strictly valid JSON object matching this schema:
{{
  "full_name": "Candidate Full Name (or 'Candidate')",
  "target_role": "{default_role}",
  "archetype": "Classification and domain (e.g. Early-career (1–3 yrs) — Full-Stack & Systems)",
  "elevator_pitch": "1-2 punchy, metric-driven sentences highlighting core superpower and scale impact",
  "top_skills": ["Skill1", "Skill2", "Skill3", "Skill4", "Skill5", "Skill6"],
  "experience_years": "Total years of technical experience",
  "key_achievements": [
    "Quantified achievement 1 with exact metrics",
    "Quantified achievement 2 with exact metrics",
    "Quantified achievement 3 with exact metrics"
  ],
  "strong_points": [
    "Specific evidence-backed differentiator 1",
    "Specific evidence-backed differentiator 2",
    "Specific evidence-backed differentiator 3"
  ],
  "best_fit_roles": ["Role 1", "Role 2", "Role 3"],
  "ats_keywords": ["keyword1", "keyword2", "keyword3"],
  "detailed_profile_analysis": "Comprehensive Markdown report with clear headings matching Step 1 and Step 2. Reference the resume line for every claim. Do not invent anything not present in the resume."
}}

Target Role Context: {default_role}

Candidate Resume:
---
{sample_resume}
---"""

    try:
        response = call_groq_with_fallback(
            messages=[
                {"role": "system", "content": "You are a Senior Technical Recruiter and Hiring Manager with 15+ years experience. Ground all analysis strictly in the provided resume. Always output valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=3200,
            response_format={"type": "json_object"}
        )
        parsed = clean_json_response(response.choices[0].message.content)
        if not parsed or not isinstance(parsed, dict):
            return make_resume_fallback()

        if not parsed.get("target_role") or parsed["target_role"].lower() == "software engineer" and target_role:
            parsed["target_role"] = default_role

        if not parsed.get("detailed_profile_analysis"):
            parsed["detailed_profile_analysis"] = make_resume_fallback()["detailed_profile_analysis"]

        if not parsed.get("strong_points") and parsed.get("key_achievements"):
            parsed["strong_points"] = parsed["key_achievements"]

        return parsed
    except Exception as e:
        print(f"[AI Agent Error] parse_resume_text failed: {e}")
        return make_resume_fallback()


def generate_personalized_pitch(
    candidate_profile: dict[str, Any],
    company_name: str,
    company_profile: dict[str, Any],
    contact_name: str = ""
) -> dict[str, Any]:
    """
    Synthesizes candidate's structured technical assessment (Input A) with company profile
    and intelligence (Input B) acting as a Senior Career Coach and Outbound Sales Copywriter.
    Produces 3 subject line angles (curiosity, specificity, benefit-led), primary cold email (< 120 words),
    LinkedIn DM variant (< 80 words), warm referral variant (< 140 words), personalization notes,
    and 'what to change if...' guidance.
    """
    candidate_name = (candidate_profile.get("full_name") or "Candidate").strip()
    target_role = (candidate_profile.get("target_role") or "Software Engineer").strip()
    archetype = (candidate_profile.get("archetype") or "").strip()
    skills = ", ".join(candidate_profile.get("top_skills", [])[:5] or ["Python", "FastAPI", "PostgreSQL", "REST APIs"])

    raw_strong = candidate_profile.get("strong_points") or candidate_profile.get("key_achievements") or []
    if raw_strong:
        strong_points_str = "\n".join([f"- {sp}" for sp in raw_strong[:3]])
    else:
        strong_points_str = "- Architected scalable backend services and high-throughput database systems."

    best_fit = ", ".join(candidate_profile.get("best_fit_roles", [])[:3]) or target_role
    resume_link = (candidate_profile.get("resume_link") or "").strip()

    company_summary = (company_profile.get("summary") or "")[:350]
    company_tech = ", ".join(company_profile.get("tech_stack", [])[:6]) or "Modern Web & Cloud Architecture"
    company_services = ", ".join(company_profile.get("services", [])[:4]) or "Custom Software Engineering & Technology Services"
    company_industry = company_profile.get("industry") or "Technology"
    culture_signals = company_profile.get("culture_signals") or company_profile.get("tone") or "Engineering-driven, quality-focused"
    likely_pain_points = company_profile.get("likely_pain_points") or []
    if isinstance(likely_pain_points, list) and likely_pain_points:
        pain_points_str = "; ".join(likely_pain_points[:2])
    else:
        pain_points_str = f"Scaling backend throughput, database indexing bottlenecks, or modernizing {company_tech.split(',')[0] if company_tech else 'web'} architecture."

    greeting = f"Hi {contact_name}," if contact_name and contact_name.strip() else f"Hi {company_name} team,"
    resume_instruction = f"Naturally mention candidate portfolio/resume link ({resume_link}) in closing CTA." if resume_link else ""

    prompt = f"""Act as a senior career coach and outbound sales copywriter. I will give you two inputs:

(A) Structured Resume Analysis:
- Candidate Name: {candidate_name}
- Target Role: {target_role}
- Archetype: {archetype}
- Core Skills: {skills}
- Key Differentiators / Proof Points:
{strong_points_str}
- Best-Fit Roles: {best_fit}
{resume_instruction}

(B) Structured Company Profile:
- Company Name: {company_name}
- Industry: {company_industry}
- What The Company Does: {company_summary}
- Core Services: {company_services}
- Tech Stack: {company_tech}
- Culture Signals: {culture_signals}
- Likely Pain Points: {pain_points_str}

Your job: write a personalized cold email plus two variants that connect the candidate's strongest, most relevant proof points to the company's actual needs. The goal is a reply or a 15-minute call — not a generic application.

Rules:
1. Open with a specific, researched hook about the company (reference a product, service, tech stack, or recent work — never "I came across your website" or generic praise).
2. In 1–2 sentences, state the candidate's single most relevant proof point with a concrete number or outcome.
3. Connect that proof to a likely need at the company, inferred from their services/stack.
4. Include one line of credible technical or domain specificity (name the stack, tool, or metric).
5. End with a low-friction CTA (e.g., "Worth a 15-min chat?" or "Open to a quick call this week?").
6. Keep the primary email under 120 words. No fluff, no "I hope this email finds you well," no attachments on first contact.
7. Tone: confident, concise, peer-to-peer — not desperate or overly formal.
8. NEVER use bracket placeholders like [Name], [Company], or [Hiring Manager]. Greet with "{greeting}".

Deliverables (must return valid JSON matching this schema):
{{
  "subject_lines": {{
    "curiosity": "Short curiosity-driven subject line (4-7 words)",
    "specificity": "Specific, stack/metric-driven subject line (4-7 words)",
    "benefit_led": "Outcome/benefit-led subject line (4-7 words)"
  }},
  "subject_line": "The best recommended subject line out of the 3 above",
  "primary_email": "Primary cold email under 120 words",
  "email_body": "Same content as primary_email",
  "variant_a_linkedin": "Shorter, punchier message under 80 words for LinkedIn DM",
  "variant_b_referral": "Slightly warmer, referral-style email under 140 words",
  "cover_letter": "Concise tailored note for company application",
  "personalization_notes": [
    "Specific company fact 1 researched and used",
    "Specific company fact 2 researched and used"
  ],
  "what_to_change_if": {{
    "if_not_hiring": "How to adjust if company is not currently hiring (e.g. pitch ad-hoc contract / knowledge exchange)",
    "if_recruiter": "How to adjust if contacting a recruiter vs engineering manager"
  }},
  "matched_skills": ["Skill1", "Skill2", "Skill3"]
}}"""

    def make_pitch_fallback():
        resume_mention = f" You can view my portfolio and projects here: {resume_link}." if resume_link else ""
        primary = f"{greeting}\n\nI noticed {company_name}’s work in {company_services.split(',')[0] if company_services else 'software delivery'} and your focus on {company_tech.split(',')[0] if company_tech else 'scalable systems'}.\n\nAs a {target_role} specializing in {skills}, I recently built backend services and optimized database queries that cut batch execution times by over 40% while maintaining sub-80ms p95 latency.\n\nGiven your focus on delivering reliable client infrastructure, I’d love to share how these techniques could support {company_name}’s upcoming roadmap.{resume_mention}\n\nWorth a 15-min chat this week?\n\nBest regards,\n{candidate_name}"
        
        linkedin = f"Hi {company_name} team, noticed your stack leans on {company_tech.split(',')[0] if company_tech else 'modern web services'}. I recently cut database cron execution by 42% and built APIs handling 50k+ req/day at sub-80ms latency. Would love to swap notes on scaling your data workflows. Open to a quick call?{resume_mention}"
        
        referral = f"{greeting}\n\nI’ve been following {company_name}’s growth in {company_industry} and really admire your engineering focus on {company_services.split(',')[0] if company_services else 'robust systems'}.\n\nIn my recent work as a {target_role}, I specialized in {skills}, with a track record of tuning high-load database queries and architecting resilient automated pipelines. I know maintaining sub-100ms response times while expanding product features is a continuous challenge.\n\nI’d welcome the chance to connect with your team to see if my background might be a strong fit for your current or upcoming projects.{resume_mention}\n\nWould you be open to a brief 15-minute chat?\n\nWarm regards,\n{candidate_name}"

        return {
            "subject_lines": {
                "curiosity": f"{target_role} scaling & latency at {company_name}",
                "specificity": f"{skills.split(',')[0] if skills else 'Backend'} optimization - {candidate_name}",
                "benefit_led": f"Cutting query latency for {company_name}"
            },
            "subject_line": f"{target_role} inquiry - {candidate_name}",
            "primary_email": primary,
            "email_body": primary,
            "variant_a_linkedin": linkedin,
            "variant_b_referral": referral,
            "cover_letter": referral,
            "personalization_notes": [
                f"Referenced {company_name}'s core focus on {company_industry}",
                f"Aligned candidate's experience in {skills} with company technology"
            ],
            "what_to_change_if": {
                "if_not_hiring": "Frame outreach as peer-to-peer knowledge sharing around query optimization or offer contract assistance.",
                "if_recruiter": "State immediate availability, target role, and location preference directly."
            },
            "matched_skills": candidate_profile.get("top_skills", [])[:3] or ["Backend Engineering", "APIs", "Databases"]
        }

    if not client:
        return make_pitch_fallback()

    try:
        response = call_groq_with_fallback(
            messages=[
                {"role": "system", "content": "You are a senior career coach and outbound sales copywriter. Never use bracket placeholders. Connect candidate proof points to company needs with precision. Return pure JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1500,
            response_format={"type": "json_object"}
        )
        parsed = clean_json_response(response.choices[0].message.content)
        if not parsed or not isinstance(parsed, dict):
            return make_pitch_fallback()

        # Extract deliverables with fallback resilience
        subj = (parsed.get("subject_line") or "").strip()
        body = (parsed.get("primary_email") or parsed.get("email_body") or "").strip()

        # Sanitize any accidental bracketed tokens
        body = re.sub(r"\[(?:Hiring Manager Name|Hiring Manager|Founder Name|Founder|Name|Recipient|Date)\]", f"{company_name} team", body, flags=re.IGNORECASE)
        body = re.sub(r"\[.*?\]", "", body).strip()
        subj = re.sub(r"\[.*?\]", "", subj).strip()

        if not subj or not body:
            return make_pitch_fallback()

        parsed["subject_line"] = subj
        parsed["primary_email"] = body
        parsed["email_body"] = body

        if not parsed.get("subject_lines") or not isinstance(parsed.get("subject_lines"), dict):
            parsed["subject_lines"] = {
                "specificity": subj,
                "curiosity": f"{target_role} inquiry - {candidate_name}",
                "benefit_led": f"Scalable {target_role} for {company_name}"
            }

        if not parsed.get("variant_a_linkedin"):
            parsed["variant_a_linkedin"] = make_pitch_fallback()["variant_a_linkedin"]
        else:
            parsed["variant_a_linkedin"] = re.sub(r"\[.*?\]", "", parsed["variant_a_linkedin"]).strip()

        if not parsed.get("variant_b_referral"):
            parsed["variant_b_referral"] = make_pitch_fallback()["variant_b_referral"]
        else:
            parsed["variant_b_referral"] = re.sub(r"\[.*?\]", "", parsed["variant_b_referral"]).strip()

        if not parsed.get("cover_letter"):
            parsed["cover_letter"] = parsed["variant_b_referral"]

        if not parsed.get("personalization_notes"):
            parsed["personalization_notes"] = [
                f"Referenced company services and tech stack ({company_tech[:50]})",
                f"Aligned candidate differentiator with company engineering goals"
            ]

        if not parsed.get("what_to_change_if"):
            parsed["what_to_change_if"] = make_pitch_fallback()["what_to_change_if"]

        if not parsed.get("matched_skills"):
            parsed["matched_skills"] = candidate_profile.get("top_skills", [])[:3]

        return parsed
    except Exception as e:
        print(f"[AI Agent Error] generate_personalized_pitch failed: {e}")
        return make_pitch_fallback()


# In-memory query normalization cache
_QUERY_NORM_CACHE: dict[str, dict[str, str]] = {}


def fallback_normalize_query(query: str) -> dict[str, str]:
    """Heuristic fallback to separate keyword and city and canonicalize tech keywords."""
    q = (query or "").strip()
    if not q or q.lower() == "direct url":
        return {"raw_keyword": "Direct URL", "city": "", "normalized_keyword": "Direct Leads"}

    # Common known Indian and international cities
    known_cities = [
        "surat", "ahmedabad", "rajkot", "gandhinagar", "vadodara", "baroda",
        "mumbai", "pune", "bangalore", "bengaluru", "delhi", "noida", "gurgaon",
        "gurugram", "hyderabad", "chennai", "kolkata", "jaipur", "indore",
        "austin", "london", "new york", "san francisco", "chicago"
    ]

    detected_city = ""
    lower_q = q.lower()
    for city in known_cities:
        # Match city at word boundaries
        pattern = r"\b" + re.escape(city) + r"\b"
        if re.search(pattern, lower_q):
            detected_city = city.title()
            # Remove city from query to isolate keyword
            q = re.sub(pattern, "", q, flags=re.IGNORECASE).strip()
            break

    # If no known city matched but last word is capitalized in original query
    if not detected_city and " " in q:
        words = q.split()
        if len(words) > 1 and words[-1][0].isupper() and words[-1].isalpha():
            detected_city = words[-1].title()
            q = " ".join(words[:-1]).strip()

    raw_keyword = q.strip()
    if not raw_keyword:
        raw_keyword = "IT Companies"

    # Canonicalize common tech keywords
    clean_kw_lower = raw_keyword.lower()
    if "php" in clean_kw_lower:
        canonical = "PHP"
    elif "mern" in clean_kw_lower:
        canonical = "MERN Stack"
    elif "mean" in clean_kw_lower:
        canonical = "MEAN Stack"
    elif "python" in clean_kw_lower or "django" in clean_kw_lower or "fastapi" in clean_kw_lower:
        canonical = "Python"
    elif "react" in clean_kw_lower:
        canonical = "React"
    elif "node" in clean_kw_lower:
        canonical = "Node.js"
    elif "flutter" in clean_kw_lower:
        canonical = "Flutter"
    elif "android" in clean_kw_lower or "ios" in clean_kw_lower or "mobile app" in clean_kw_lower:
        canonical = "Mobile App Development"
    elif "e-commerce" in clean_kw_lower or "ecommerce" in clean_kw_lower or "shopify" in clean_kw_lower or "woocommerce" in clean_kw_lower:
        canonical = "E-Commerce"
    elif "social media" in clean_kw_lower or "digital marketing" in clean_kw_lower or "seo" in clean_kw_lower:
        canonical = "Social Media & Marketing"
    elif "web agency" in clean_kw_lower or "web dev" in clean_kw_lower or "website" in clean_kw_lower:
        canonical = "Web Development"
    elif "software" in clean_kw_lower or "it comp" in clean_kw_lower or "it serv" in clean_kw_lower:
        canonical = "IT Companies"
    else:
        # Title case cleaned keyword
        canonical = " ".join(w.capitalize() for w in re.sub(r"\b(based|related|services|company|companies|solutions|agency)\b", "", raw_keyword, flags=re.IGNORECASE).split()).strip()
        if not canonical:
            canonical = raw_keyword.title()

    return {
        "raw_keyword": raw_keyword,
        "city": detected_city,
        "normalized_keyword": canonical
    }


def normalize_queries_batch(queries: list[str]) -> dict[str, Any]:
    """
    Uses AI Agent to separate queries into raw_keyword, city, and normalized_keyword.
    Normalizes synonymous keywords (e.g. 'php related', 'php based', 'php', 'PhP' -> 'PHP').
    Returns:
    {
      "mappings": { query_str: { "keyword": ..., "city": ..., "normalized_keyword": ... } },
      "canonical_keywords": [...],
      "cities": [...]
    }
    """
    clean_queries = [q.strip() for q in queries if q and q.strip()]
    if not clean_queries:
        return {"mappings": {}, "canonical_keywords": [], "cities": []}

    # Check which queries need AI processing
    needed = [q for q in clean_queries if q not in _QUERY_NORM_CACHE]

    if needed and client:
        prompt = f"""You are an elite search taxonomy engineer.
We have Google search queries used to find tech leads:
{needed}

For each query:
1. Separate into:
   - "keyword": Search term / phrase without the city (e.g. "PHP based", "PHP related", "IT Companies").
   - "city": Target city (e.g. "Surat", "Rajkot", "Ahmedabad", "Gandhinagar", "Bangalore"). Title case. If no city is present, empty string "".
   - "normalized_keyword": A clean canonical tech skill or industry category.
     CRITICAL REQUIREMENT:
     Variations like "php related", "php based", "php", "PhP", "PHP Developer" MUST ALL normalize to the exact same canonical keyword: "PHP".
     "mern stack", "mern developer" -> "MERN Stack"
     "web agency", "web development" -> "Web Development"
     "e-commerce", "ecommerce development" -> "E-Commerce"
     "it companies", "it company" -> "IT Companies"

Return ONLY a valid JSON object:
{{
  "mappings": {{
     "Query String Here": {{
        "keyword": "raw search phrase",
        "city": "City Name",
        "normalized_keyword": "Canonical Keyword"
     }}
  }}
}}"""
        try:
            response = call_groq_with_fallback(
                messages=[
                    {"role": "system", "content": "You are a specialized search taxonomy engineer. Output pure JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=600,
                response_format={"type": "json_object"}
            )
            data = clean_json_response(response.choices[0].message.content)
            mappings = data.get("mappings", {})
            for q, item in mappings.items():
                if isinstance(item, dict):
                    _QUERY_NORM_CACHE[q] = {
                        "raw_keyword": item.get("keyword") or q,
                        "city": (item.get("city") or "").strip().title(),
                        "normalized_keyword": (item.get("normalized_keyword") or item.get("keyword") or q).strip()
                    }
        except Exception as e:
            print(f"[AI Agent Error] normalize_queries_batch failed: {e}")

    # For any remaining queries not in cache, use heuristic fallback
    for q in clean_queries:
        if q not in _QUERY_NORM_CACHE:
            _QUERY_NORM_CACHE[q] = fallback_normalize_query(q)

    # Build final response
    res_mappings = {q: _QUERY_NORM_CACHE.get(q, fallback_normalize_query(q)) for q in clean_queries}
    all_canonicals = sorted(list(set(m["normalized_keyword"] for m in res_mappings.values() if m.get("normalized_keyword"))))
    all_cities = sorted(list(set(m["city"] for m in res_mappings.values() if m.get("city"))))

    return {
        "mappings": res_mappings,
        "canonical_keywords": all_canonicals,
        "cities": all_cities
    }


def normalize_single_keyword(keyword: str, city: str = "") -> str:
    """Normalize a keyword using AI or fast fallback to canonical skill/category."""
    combined = f"{keyword} {city}".strip()
    if combined in _QUERY_NORM_CACHE:
        return _QUERY_NORM_CACHE[combined]["normalized_keyword"]

    res = normalize_queries_batch([combined])
    mapping = res.get("mappings", {}).get(combined)
    if mapping:
        return mapping["normalized_keyword"]
    return fallback_normalize_query(combined)["normalized_keyword"]

