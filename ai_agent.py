import json
import re
from typing import Any

from groq import Groq

import config

import itertools
import time

_CLIENT_POOL = [
    Groq(api_key=k) for k in config.GROQ_API_KEYS
] if config.GROQ_API_KEYS else ([Groq(api_key=config.GROQ_API_KEY)] if config.GROQ_API_KEY else [])

_client_counter = itertools.count()
client = _CLIENT_POOL[0] if _CLIENT_POOL else None

_ROTATING_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]
_model_counter = itertools.count()


def call_groq_with_fallback(messages: list[dict], temperature: float = 0.3, max_tokens: int = 1200, response_format: dict = None):
    """
    Calls Groq with automatic multi-account round-robin and model fallback cascade:
    Distributes parallel queries across multiple independent Groq accounts and models
    to maximize throughput (up to 32,000+ TPM) and completely prevent rate-limit throttling.
    """
    if not _CLIENT_POOL:
        raise RuntimeError("No active Groq API keys available.")

    # Pick next starting client in rotation
    client_start_idx = next(_client_counter) % len(_CLIENT_POOL)
    candidate_clients = _CLIENT_POOL[client_start_idx:] + _CLIENT_POOL[:client_start_idx]

    # Pick next primary model in rotation
    next_idx = next(_model_counter)
    primary = _ROTATING_MODELS[next_idx % len(_ROTATING_MODELS)]
    candidate_models = [primary] + [m for m in _ROTATING_MODELS if m != primary]

    last_exc = None
    for active_client in candidate_clients:
        for model_name in candidate_models:
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
                    if "429" in err_str or "rate limit" in err_str:
                        # Account-level rate limit hit: immediately try the next account client
                        time.sleep(0.3)
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
    Generates an in-depth 500-700 word technical intelligence report for precision outreach.
    """
    if not client:
        return {
            "summary": f"{company_name} is a technology company operating on {domain}.",
            "detailed_analysis": f"Comprehensive Technical Profile for {company_name} ({domain}):\n\n1. Business Model & Core Offerings:\n{company_name} specializes in software and digital technology solutions.\n\n2. Technical Infrastructure:\nUtilizes modern web development frameworks, databases, and cloud services.\n\n3. Potential Pain Points & Opportunities:\nScaling web applications, optimizing database performance, and expanding feature sets.\n\n4. Recommended Outreach Hook:\nHighlight strong full-stack foundations, microservices, and rapid feature execution.",
            "industry": "Software & Services",
            "tech_stack": ["Web Technologies", "APIs"],
            "services": ["Software Development", "IT Services"],
            "hiring_signals": "General engineering expansion",
            "tone": "Professional"
        }

    clean_sample = scraped_text[:3500]

    prompt = f"""You are an elite B2B technical research analyst and engineering talent strategist.
Perform a thorough, comprehensive technical intelligence analysis (500 to 700 words) of the company "{company_name}" ({domain}) based on their scraped website content.

Scraped Website Content:
---
{clean_sample}
---

Your response MUST be a valid JSON object containing:
{{
  "summary": "Concise 2-sentence executive overview of what they build and their target audience",
  "detailed_analysis": "A thorough, in-depth 500 to 700 word technical intelligence report formatted with clean Markdown sections:\\n\\n### 1. Executive Business Overview & Value Proposition\\nDetailed explanation of what problems they solve, their products/services, and customer market.\\n\\n### 2. Architecture & Technical Infrastructure\\nDeep breakdown of their engineering stack, frameworks, programming languages, databases, and development methodologies evident from their site.\\n\\n### 3. Core Products & Solutions\\nDetailed breakdown of their flagship solutions, client projects, or software products.\\n\\n### 4. Engineering Needs & Growth Challenges\\nAnalysis of their potential technical scaling pain points, performance challenges, or areas where an ambitious engineer can add immense value.\\n\\n### 5. High-Impact Cold Outreach Angles\\nSpecific technical hooks and strategic angles a job seeker can leverage to immediately catch the hiring team's attention.",
  "industry": "Specific industry (e.g. Enterprise SaaS, FinTech, Custom Software Agency, E-commerce Tech)",
  "tech_stack": ["Comprehensive", "list", "of", "all", "detected", "technologies", "libraries", "tools"],
  "services": ["Primary service/product 1", "Primary service/product 2", "Primary service/product 3", "Primary service/product 4"],
  "hiring_signals": "Clear signals on hiring needs, technology focus, or team growth",
  "tone": "Company engineering culture vibe (e.g. Fast-Paced Startup, Enterprise Engineering, Client-Focused Agency)"
}}
"""

    try:
        response = call_groq_with_fallback(
            messages=[
                {"role": "system", "content": "You are an elite technical profiler. Always respond with detailed, structured, valid JSON. Be thorough, concrete, and concise."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1800,
            response_format={"type": "json_object"}
        )
        return clean_json_response(response.choices[0].message.content)
    except Exception as e:
        print(f"[AI Agent Error] analyze_company failed: {e}")
        return {
            "summary": f"{company_name} is an active technology provider on {domain}.",
            "detailed_analysis": f"Detailed Technical Profile for {company_name}:\n\nOperates in digital software engineering with active web solutions. Focuses on client solutions and web services.",
            "industry": "Information Technology",
            "tech_stack": ["PHP", "JavaScript", "MySQL"],
            "services": ["Custom Software Development"],
            "hiring_signals": "Open to talented engineers",
            "tone": "Professional"
        }


def parse_resume_text(resume_text: str, target_role: str = "") -> dict[str, Any]:
    """
    Analyzes candidate's uploaded resume text in-memory and generates
    an in-depth 500-700 word technical candidate profile report.
    """
    if not client:
        return {
            "full_name": "Candidate",
            "target_role": target_role or "Software Engineer",
            "elevator_pitch": "Full-Stack Engineer specialized in scalable web services and high-performance APIs.",
            "detailed_profile_analysis": "Comprehensive Candidate Technical Evaluation:\n\n1. Technical Archetype:\nFull-Stack Engineer with strong capabilities in backend systems, database modeling, and frontend integration.\n\n2. Core Competencies:\nLanguages: Python, JavaScript, TypeScript, PHP.\nFrameworks: FastAPI, React, Node.js.\nDatabases: PostgreSQL, MySQL, Redis.\n\n3. Impact & Strengths:\nProven track record of architecting reliable web services, automating data pipelines, and building responsive user interfaces.\n\n4. Recommended Job Positioning:\nPosition as a versatile builder capable of owning features end-to-end.",
            "top_skills": ["Python", "FastAPI", "React", "PostgreSQL", "REST APIs"],
            "experience_years": "3+ years",
            "key_achievements": [
                "Architected scalable backend microservices with sub-50ms response times",
                "Built full-stack applications with responsive React interfaces and clean state management",
                "Automated end-to-end data pipelines reducing manual processing by 80%"
            ]
        }

    sample_resume = resume_text[:12000]

    prompt = f"""You are a Principal Engineering Evaluator, Staff Systems Architect, and Executive Technical Recruiter.
Analyze this candidate's resume in exhaustive technical depth for the target role: "{target_role or 'Software Engineer'}".

Do NOT output a brief or shallow summary. Provide an in-depth, high-context, 600–800 word Technical Candidate Dossier.
Extract all concrete architectural details, specific database optimizations, query profiling, anti-bot mechanisms, concurrency patterns, e-commerce repricing algorithms, mobile/edge data parsing, and measurable performance metrics.

Candidate Resume Content:
---
{sample_resume}
---

Your response MUST be a valid JSON object matching this schema:
{{
  "full_name": "Candidate Full Name (or 'Candidate' if not explicitly stated)",
  "target_role": "{target_role if target_role else 'Software Engineer'}",
  "elevator_pitch": "1-2 punchy, metric-driven sentences highlighting the candidate's core technical superpower, signature architectures, and scale impact.",
  "detailed_profile_analysis": "Comprehensive Technical Candidate Dossier in Markdown format with the following structured sections:

### 1. Executive Engineering Archetype & Technical Identity
Thorough analysis of the candidate's engineering persona (e.g. backend optimization specialist, distributed data pipeline engineer, systems builder). Discuss their depth in low-level database tuning, e-commerce production backends, anti-bot data extraction, and hybrid mobile/edge systems.

### 2. Comprehensive Architectural & Technical Stack Breakdown
- **Core Languages & Runtimes:** Deep dive into language proficiencies (e.g. PHP, Python, JavaScript, Dart, SQL) and their real-world application.
- **Databases, Indexing & Query Tuning:** Specific databases (MySQL, PostgreSQL), profiling techniques, slow query refactoring, schema indexing, and bulk upsert strategies with zero-duplicate guarantees.
- **Scraping, Anti-Bot & Pipeline Engineering:** Anti-bot bypass frameworks (curl_cffi browser fingerprinting/TLS, FlareSolverr, undetected-chromedriver, Playwright, Selenium, Scrapy), Cloudflare/reCAPTCHA mitigation, distributed runner matrices (GitHub Actions), and cron job automation.
- **Mobile, Systems & Offline Edge Data:** On-device application engineering (Flutter, Riverpod, Isar database), background PDF extraction, localized regex for complex/Unicode statement parsing, and zero-cloud privacy architecture.

### 3. Signature Accomplishments, Concrete Scale & Measured Impact
Analyze each major project and role in detail with actual quantitative outcomes:
- **E-Commerce & High-Impact Backend:** Quantify execution speedups (e.g. cutting 25-minute cron workflows to 15 minutes by eliminating redundant queries and applying database indexes), dynamic repricing engines using margin maps and competitor price intelligence.
- **Distributed Scraping & ETL Infrastructure:** Serverless multi-worker pipelines scraping 10k+ SKUs across major US retail platforms on GitHub Actions, deduplication, and Railway Flask dashboards.
- **Client-Side Data Intelligence:** On-device financial parsing engines handling transactional bank SMS across national banks, Unicode font edge-cases, background PDF parsing, and smart entity brand normalization.

### 4. Problem-Solving Rigor & Optimization Philosophy
Discuss how the candidate approaches difficult engineering trade-offs: handling anti-scraping defenses without dedicated servers, optimizing legacy codebases (e.g. Magento 1) alongside modern stacks, ensuring transactional consistency, and building resilient automated pipelines.

### 5. Strategic Job Fit & Positioning Narrative
A compelling, hiring-manager-facing narrative articulating exactly why this candidate is an immediate multiplier for this target role and what problems they can solve on Day 1.",
  "top_skills": ["Skill1", "Skill2", "Skill3", "Skill4", "Skill5", "Skill6", "Skill7", "Skill8"],
  "experience_years": "Estimated total years of technical experience (e.g. 2+ years, 3+ years)",
  "key_achievements": [
    "Quantified achievement 1 with exact metrics, technologies, and speedup/scale",
    "Quantified achievement 2 with exact pipeline architecture and database deduplication",
    "Quantified achievement 3 with edge-device or mobile parsing complexity and system design",
    "Quantified achievement 4 with legacy optimization or e-commerce repricing margin logic"
  ]
}}
"""

    try:
        response = call_groq_with_fallback(
            messages=[
                {"role": "system", "content": "You are a Principal Systems Architect and Executive Technical Recruiter. Provide thorough, high-context, in-depth technical analysis in valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2200,
            response_format={"type": "json_object"}
        )
        return clean_json_response(response.choices[0].message.content)
    except Exception as e:
        print(f"[AI Agent Error] parse_resume_text failed: {e}")
        return {
            "full_name": "Candidate",
            "target_role": target_role or "Software Engineer",
            "elevator_pitch": "Performance-focused backend engineer experienced in SQL optimization, distributed data pipelines, and full-stack development.",
            "detailed_profile_analysis": "Technical Assessment:\n\nCandidate demonstrates proficiency in backend architecture, database indexing, and distributed scraping pipelines.",
            "top_skills": ["Python", "PHP", "MySQL", "PostgreSQL", "Playwright", "Flask"],
            "experience_years": "2+ years",
            "key_achievements": [
                "Optimized database cron execution time by 40% via query restructuring and indexing",
                "Engineered multi-site parallel scraping pipelines with automated PostgreSQL deduplication",
                "Built offline mobile data parsers handling complex Unicode banking statements"
            ]
        }


def generate_personalized_pitch(
    candidate_profile: dict[str, Any],
    company_name: str,
    company_profile: dict[str, Any],
    contact_name: str = ""
) -> dict[str, Any]:
    """
    Synthesizes company intelligence with candidate technical assessment
    to create a laser-targeted 1-to-1 cold application email.
    Guarantees zero robotic bracket placeholders and authentic engineering tone.
    """
    candidate_name = candidate_profile.get("full_name", "Rahul Vora")
    target_role = candidate_profile.get("target_role", "Backend Developer")
    skills = ", ".join(candidate_profile.get("top_skills", []) or ["PHP", "Python", "MySQL", "PostgreSQL", "REST APIs"])
    achievements = "\n".join([f"- {a}" for a in candidate_profile.get("key_achievements", [])])
    candidate_deep_analysis = candidate_profile.get("detailed_profile_analysis", "")
    resume_link = (candidate_profile.get("resume_link") or "").strip()

    company_summary = company_profile.get("summary", "")
    company_deep_analysis = company_profile.get("detailed_analysis", "")
    company_tech = ", ".join(company_profile.get("tech_stack", []))
    company_industry = company_profile.get("industry", "Technology")

    resume_link_instruction = f"Candidate Resume/Portfolio Link: {resume_link}\nInclude this live link naturally in the email closing/CTA so the hiring team can review candidate's work directly." if resume_link else "Mention that candidate is ready to share complete resume and code samples upon reply."

    prompt = f"""You are an expert engineering talent strategist and cold email copywriter.
You are helping an engineer ({candidate_name}) send a direct, high-impact cold application / talent inquiry email to {company_name}.
This email is strictly a JOB OPPORTUNITY / TALENT APPLICATION outreach, NOT a sales pitch or agency inquiry.

Target Company: {company_name}
Industry: {company_industry}
Active Tech Stack: {company_tech or 'Modern Web & Backend Architecture'}
Company Overview: {company_summary}
In-Depth Company Intelligence:
---
{company_deep_analysis[:3500]}
---

Candidate: {candidate_name} (Target Role: {target_role})
Candidate Core Skills: {skills}
Key Achievements:
{achievements}
Candidate In-Depth Profile:
---
{candidate_deep_analysis[:3500]}
---
{resume_link_instruction}

STRICT WRITING RULES:
1. GREETING: NEVER use bracketed placeholders like "[Hiring Manager Name]", "[Name]", "[Founder]", or "[Recipient]". These destroy response rates.
   Greet naturally as: "Hi {company_name} team," or "Hi there,".
2. SUBJECT LINE: 4 to 7 words. Natural, direct, professional. Zero marketing buzzwords.
   Examples: "{target_role} inquiry - {candidate_name}" or "Quick question regarding {target_role} at {company_name}".
3. BODY: 110-150 words. Authentic, concise, engineering-focused.
   - Genuine Hook: Specifically reference what {company_name} builds.
   - Value Bridge: Connect candidate's hands-on experience and metrics to how candidate can help {company_name} scale or ship.
   - Clear CTA: Inquire about current or upcoming {target_role} opportunities.
4. SIGN-OFF: Professional with candidate's name ({candidate_name}).

Return ONLY a valid JSON object matching this schema:
{{
  "subject_line": "Direct job inquiry subject line",
  "email_body": "Full body of cold email (with natural line breaks)",
  "cover_letter": "A 200-250 word tailored cover letter aligning candidate experience with company mission",
  "matched_skills": ["Skill 1", "Skill 2", "Skill 3"]
}}
"""

    def make_fallback():
        resume_mention = f"\n\nYou can also view my complete resume and projects here: {resume_link}" if resume_link else ""
        greeting = f"Hi {company_name} team,"
        return {
            "subject_line": f"{target_role} inquiry - {candidate_name}",
            "email_body": f"{greeting}\n\nI’ve been following {company_name} and wanted to reach out directly. As a {target_role} specializing in {skills}, I have hands-on experience building performant backend systems, automating data pipelines, and optimizing high-load databases.\n\nI'm exploring new {target_role} opportunities and would love to know if {company_name} has any current or upcoming openings on the engineering team.{resume_mention}\n\nWould you be open to a brief chat to see if my background might be a good fit for your product roadmap?\n\nBest regards,\n{candidate_name}",
            "cover_letter": f"Dear Hiring Team at {company_name},\n\nI am writing to express my strong enthusiasm for {target_role} opportunities at {company_name}. With deep technical experience in {skills}, I specialize in delivering robust software architectures, tuning database performance, and building resilient automated services.\n\nI would welcome the opportunity to discuss how my technical foundations can support {company_name}'s goals.\n\nSincerely,\n{candidate_name}",
            "matched_skills": candidate_profile.get("top_skills", [])[:3] or ["Backend Engineering", "APIs", "Databases"]
        }

    if not client:
        return make_fallback()

    try:
        response = call_groq_with_fallback(
            messages=[
                {"role": "system", "content": "You are an elite technical talent copywriter crafting direct job opportunity cold emails. Never use bracket placeholders. Output pure JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        parsed = clean_json_response(response.choices[0].message.content)
        
        subject = (parsed.get("subject_line") or "").strip()
        body = (parsed.get("email_body") or "").strip()

        # Sanitize any accidental bracketed tokens
        body = re.sub(r"\[(?:Hiring Manager Name|Hiring Manager|Founder Name|Founder|Name|Recipient)\]", f"{company_name} team", body, flags=re.IGNORECASE)
        body = re.sub(r"\[.*?\]", "", body).strip()
        subject = re.sub(r"\[.*?\]", "", subject).strip()

        if not subject or not body:
            return make_fallback()

        parsed["subject_line"] = subject
        parsed["email_body"] = body
        if not parsed.get("cover_letter"):
            parsed["cover_letter"] = make_fallback()["cover_letter"]
        if not parsed.get("matched_skills"):
            parsed["matched_skills"] = candidate_profile.get("top_skills", [])[:3]

        return parsed
    except Exception as e:
        print(f"[AI Agent Error] generate_personalized_pitch failed: {e}")
        return make_fallback()


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

