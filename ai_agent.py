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

_ROTATING_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"]
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
            "summary": "",
            "detailed_analysis": "",
            "industry": "",
            "tech_stack": [],
            "services": [],
            "hiring_signals": "",
            "tone": ""
        }

    clean_sample = (scraped_text or "").strip()[:12000]
    if len(clean_sample) < 60:
        return {
            "summary": "",
            "detailed_analysis": f"### No Readable Website Content Detected\nUnable to extract technical intelligence for **{company_name}** (`{domain}`) because the website returned no readable text (the domain may be parked, inactive, or restricted by client-side protection).",
            "industry": "",
            "tech_stack": [],
            "services": [],
            "hiring_signals": "",
            "tone": ""
        }

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
            "summary": "",
            "detailed_analysis": "",
            "industry": "",
            "tech_stack": [],
            "services": [],
            "hiring_signals": "",
            "tone": ""
        }


def parse_resume_text(resume_text: str, target_role: str = "") -> dict[str, Any]:
    """
    Analyzes candidate's uploaded resume using a Senior Technical Recruiter & Hiring Manager
    3-Step deep evaluation workflow. Produces structured data fields and an exhaustive Markdown report.
    Never uses fake or synthetic fallbacks.
    """
    default_role = target_role or "Software Engineer"
    sample_resume = (resume_text or "").strip()[:14000]

    if not sample_resume:
        raise ValueError("Resume text is empty or could not be extracted from the file.")

    if not client:
        raise RuntimeError("Groq AI client is not initialized. Please verify your GROQ_API_KEY.")

    prompt = f"""Act as a senior technical recruiter and hiring manager with 15+ years of experience screening resumes across software engineering, product, design, and business roles. I will provide a resume. Analyze it deeply and produce a structured report that extracts every strong point, strictly grounded in the candidate's actual experience.

CRITICAL ANTI-HALLUCINATION RULES:
1. ZERO INVENTED STATS OR PROJECTS: You MUST NEVER invent or hallucinate metrics (e.g. do not invent "sub-80ms p95 latency", "42% query execution speedup", or "10,000+ records weekly"). Only cite numbers, percentages, and metrics that LITERALLY appear in the resume text!
2. ZERO INVENTED DOMAINS: If the candidate never worked in ETL Pipelines, Web Scraping, or Distributed Systems, DO NOT mention or tag them. Base all projects and accomplishments 100% on what is written.
3. EXTRACT EXACT CANDIDATE NAME: Extract the candidate's actual full name from the top of the resume (e.g. Dhanrajsinh Parmar). Never label them "Candidate" if their name is present.

Step 1 — Identify the resume archetype.
Classify it as: Fresher/Entry-level, Early-career (1–3 yrs), Mid-level (4–7 yrs), Senior (8+ yrs), Career-switcher, Freelancer/Consultant, Creative/Portfolio-based, or Non-technical/Business. Note the domain based strictly on their actual work.

Step 2 — Extract and structure:

Candidate Snapshot — Name, total years of experience, current/most recent role and company, education and CGPA/grade, location and contact signals.

Skills Inventory (grouped) — Languages, frameworks, databases, cloud/tools, soft skills. Only include technologies explicitly listed or used in their projects/jobs.

Experience Highlights — For each role: company, duration, scope. Pull out every quantified achievement (%, time saved, revenue, users, scale) that appears in the text. State the business impact.

Project Deep-Dives — For each project: problem, stack, what was built, measurable outcome, complexity.

Strong Points — The Differentiators — List 4–6 specific, evidence-backed strengths directly proven by their bullets.

Gaps & Risks — Honest evaluation of gaps relative to the target role ({default_role}).

Best-Fit Roles — 3–5 job titles the candidate is realistically competitive for based on their actual resume stack.

ATS Keyword Extract — 20–30 relevant keywords verified in their profile.

Step 3 — Output format. Return a strictly valid JSON object matching this schema:
{{
  "full_name": "Exact Candidate Full Name",
  "target_role": "{default_role}",
  "archetype": "Classification and domain",
  "elevator_pitch": "1-2 punchy, metric-driven sentences highlighting verified superpowers from the resume",
  "top_skills": ["Skill1", "Skill2", "Skill3", "Skill4", "Skill5", "Skill6"],
  "experience_years": "Total years of technical experience",
  "key_achievements": [
    "Exact achievement 1 from resume",
    "Exact achievement 2 from resume"
  ],
  "strong_points": [
    "Evidence-backed differentiator 1",
    "Evidence-backed differentiator 2"
  ],
  "best_fit_roles": ["Role 1", "Role 2", "Role 3"],
  "ats_keywords": ["keyword1", "keyword2", "keyword3"],
  "detailed_profile_analysis": "Comprehensive Markdown report with clear headings matching Step 1 and Step 2. Reference the exact resume bullets. Never invent anything."
}}

Target Role Context: {default_role}

Candidate Resume:
---
{sample_resume}
---"""

    response = call_groq_with_fallback(
        messages=[
            {"role": "system", "content": "You are a Senior Technical Recruiter and Hiring Manager. Ground all analysis strictly and 100% in the provided resume. Never fabricate projects, numbers, or tech stacks."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=3200,
        response_format={"type": "json_object"}
    )
    parsed = clean_json_response(response.choices[0].message.content)
    if not parsed or not isinstance(parsed, dict):
        raise ValueError("Could not parse structured JSON from resume analysis.")

    if not parsed.get("target_role") or (parsed["target_role"].lower() == "software engineer" and target_role):
        parsed["target_role"] = default_role

    # Handle alternate key naming gracefully without falling back to mock data
    analysis_text = parsed.get("detailed_profile_analysis") or parsed.get("detailed_analysis") or parsed.get("summary")
    if not analysis_text:
        achievements_md = "\n".join(f"- {ach}" for ach in parsed.get("key_achievements", []))
        parsed["detailed_profile_analysis"] = f"### Candidate Profile: {parsed.get('full_name', 'Candidate')}\n\n#### Key Verified Achievements\n{achievements_md}"
    else:
        parsed["detailed_profile_analysis"] = analysis_text

    if not parsed.get("strong_points") and parsed.get("key_achievements"):
        parsed["strong_points"] = parsed["key_achievements"]

    return parsed


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
    skills = ", ".join(candidate_profile.get("top_skills", [])[:5])

    raw_strong = candidate_profile.get("strong_points") or candidate_profile.get("key_achievements") or []
    if raw_strong:
        strong_points_str = "\n".join([f"- {sp}" for sp in raw_strong[:3]])
    else:
        strong_points_str = ""

    best_fit = ", ".join(candidate_profile.get("best_fit_roles", [])[:3]) or target_role
    resume_link = (candidate_profile.get("resume_link") or "").strip()

    company_summary = (company_profile.get("summary") or "")[:350]
    company_tech = ", ".join(company_profile.get("tech_stack", [])[:6])
    company_services = ", ".join(company_profile.get("services", [])[:4])
    company_industry = company_profile.get("industry") or ""
    culture_signals = company_profile.get("culture_signals") or company_profile.get("tone") or ""
    likely_pain_points = company_profile.get("likely_pain_points") or []
    if isinstance(likely_pain_points, list) and likely_pain_points:
        pain_points_str = "; ".join(likely_pain_points[:2])
    else:
        pain_points_str = ""

    greeting = f"Hi {contact_name}," if contact_name and contact_name.strip() else f"Hi {company_name} team,"
    resume_instruction = f"Explicitly mention that the candidate's resume/portfolio is available at ({resume_link}) or attached." if resume_link else "Mention that the candidate's resume is attached for review."

    prompt = f"""Act as a senior technical talent advisor and candidate career strategist. You are writing a high-signal, direct COLD JOB APPLICATION / INQUIRY email on behalf of a technical candidate reaching out to engineering leadership, founders, or the hiring team at {company_name}.

CONTEXT:
This is a JOB SEEKER reaching out for open or upcoming {target_role} employment opportunities.
This is NOT a B2B sales pitch, NOT an agency offering services, and NOT product marketing.

(A) Structured Resume Analysis of Candidate:
- Candidate Full Name: {candidate_name}
- Target Job Role: {target_role}
- Professional Archetype: {archetype}
- Core Verified Skills: {skills}
- Evidence-Backed Achievements from Resume:
{strong_points_str}
- Best-Fit Roles: {best_fit}
- Resume Reference: {resume_instruction}

(B) Company Intelligence:
- Company Name: {company_name}
- Industry: {company_industry}
- What They Build / Do: {company_summary}
- Core Services: {company_services}
- Tech Stack: {company_tech}
- Culture / Engineering Signals: {culture_signals}

YOUR OBJECTIVE:
Write a concise, professional cold job outreach email that connects the candidate's verified technical skills and measurable resume achievements to the company's tech stack and engineering work, inquiring about open or upcoming {target_role} positions.

CRITICAL RULES:
1. PURPOSE IS JOB OPPORTUNITY: Clearly state the candidate is reaching out regarding open or upcoming {target_role} roles / engineering opportunities at {company_name}.
2. ZERO SALES/AGENCY CLICHÉS:
   - NEVER ask "Worth a 15-min chat this week?" or "jump on a quick call".
   - NEVER say "support your upcoming roadmap" or "scale your business".
   - NEVER pitch consulting, contract services, or vendor solutions.
3. GROUNDED IN RESUME: Feature 1 concrete, verified achievement or project directly from the candidate's resume. Cite actual technologies ({skills}). Never invent numbers or fake metrics.
4. COMPANY RELEVANCE: In 1 sentence, show genuine alignment between the candidate's technical experience and what {company_name} works with ({company_tech or company_services}).
5. CALL TO ACTION (JOB INQUIRY):
   - Mention the attached resume (or portfolio link {resume_link if resume_link else ''}).
   - Ask a professional, low-pressure hiring question: e.g., "Are you currently hiring for {target_role} roles, or open to considering my profile for upcoming engineering needs?"
6. GREETING & SIGN-OFF:
   - Greet strictly with "{greeting}" (never use placeholders like [Hiring Manager]).
   - Sign off cleanly with:
     Best regards,
     {candidate_name}
7. LENGTH: Under 110 words. Clear, respectful, peer-to-peer engineering tone. No fluff ("I hope this finds you well").

Deliverables (must return valid JSON matching this schema):
{{
  "subject_lines": {{
    "specificity": "Application: {target_role} - {candidate_name} ({skills.split(',')[0] if skills else target_role})",
    "curiosity": "Inquiring about {target_role} opportunities at {company_name} - {candidate_name}",
    "benefit_led": "{target_role} candidate experienced in {skills.split(',')[0] if skills else target_role} - {candidate_name}"
  }},
  "subject_line": "The best recommended subject line out of the 3 above",
  "primary_email": "Primary cold job outreach email under 110 words",
  "email_body": "Same content as primary_email",
  "variant_a_linkedin": "Short LinkedIn message under 75 words to an engineering manager or founder regarding open roles",
  "variant_b_referral": "Warmer referral/networking note under 125 words expressing admiration for their tech stack and asking about team growth",
  "cover_letter": "Concise tailored candidate cover letter paragraph for application portals",
  "personalization_notes": [
    "Specific company tech or service aligned with candidate experience",
    "Candidate resume achievement highlighted for this role"
  ],
  "what_to_change_if": {{
    "if_not_hiring": "How candidate should respond if no immediate openings (e.g., ask to stay connected and keep resume on file for future expansion)",
    "if_recruiter": "How to tailor if speaking directly to an internal recruiter vs CTO/Tech Lead"
  }},
  "matched_skills": ["Skill1", "Skill2", "Skill3"]
}}"""

    def make_pitch_fallback():
        raw_proofs = candidate_profile.get("key_achievements") or candidate_profile.get("strong_points") or []
        proof = raw_proofs[0] if raw_proofs else f"building production applications using {skills}"
        resume_ref = f" (Portfolio / Resume: {resume_link})" if resume_link else " (Resume attached)"
        comp_tech_focus = company_tech.split(',')[0].strip() if company_tech else (company_services.split(',')[0].strip() if company_services else "modern software engineering")

        primary = (
            f"{greeting}\n\n"
            f"I am writing to inquire about open or upcoming {target_role} opportunities at {company_name}.\n\n"
            f"As a {target_role} specializing in {skills}, my recent work includes {proof}. "
            f"Given {company_name}'s focus on {comp_tech_focus}, I would love to contribute my experience to your engineering team.\n\n"
            f"I have shared my resume for your consideration{resume_ref}. Are you currently hiring for {target_role} roles, or open to a brief conversation if there might be a potential fit?\n\n"
            f"Best regards,\n"
            f"{candidate_name}"
        )

        linkedin = (
            f"Hi {contact_name or company_name + ' team'},\n\n"
            f"I’m reaching out to explore potential {target_role} opportunities at {company_name}. "
            f"I specialize in {skills} and recently {proof}. Given your work with {comp_tech_focus}, "
            f"I'd love to connect and share my resume{resume_ref} if you have any open engineering roles.\n\n"
            f"Best regards,\n{candidate_name}"
        )

        referral = (
            f"{greeting}\n\n"
            f"I have been following {company_name}'s work in {company_industry or 'technology'} and wanted to reach out regarding potential {target_role} openings.\n\n"
            f"In my background as a {target_role}, I focus on {skills}, where I {proof}. "
            f"I really admire the work your team is doing around {comp_tech_focus} and would welcome the chance to explore how my skills could add value to your projects.\n\n"
            f"I have attached my resume for your review{resume_ref}. Would you be open to considering my profile if an engineering opportunity arises?\n\n"
            f"Warm regards,\n"
            f"{candidate_name}"
        )

        return {
            "subject_lines": {
                "specificity": f"Application: {target_role} - {candidate_name}",
                "curiosity": f"{target_role} inquiry for {company_name} - {candidate_name}",
                "benefit_led": f"{target_role} ({skills.split(',')[0] if skills else target_role}) - {candidate_name}"
            },
            "subject_line": f"{target_role} Inquiry - {candidate_name}",
            "primary_email": primary,
            "email_body": primary,
            "variant_a_linkedin": linkedin,
            "variant_b_referral": referral,
            "cover_letter": referral,
            "personalization_notes": [
                f"Referenced {company_name}'s engineering focus on {comp_tech_focus}",
                f"Highlighted candidate's verified resume achievement for {target_role} role"
            ],
            "what_to_change_if": {
                "if_not_hiring": "Ask if you can stay in touch on LinkedIn or if they can keep your resume on file for future openings.",
                "if_recruiter": "Mention your immediate availability, work authorization, and preferred start date."
            },
            "matched_skills": candidate_profile.get("top_skills", [])[:3] or [target_role]
        }

    if not client:
        return make_pitch_fallback()

    try:
        response = call_groq_with_fallback(
            messages=[
                {"role": "system", "content": "You are a senior technical talent advisor and candidate career strategist. You write direct, respectful cold job application outreach from technical candidates to engineering teams. Never use bracket placeholders. Never pitch products or sales services. Connect candidate proof points to company engineering needs with precision. Return pure JSON."},
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

