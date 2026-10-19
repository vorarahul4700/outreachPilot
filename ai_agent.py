import json
import re
from typing import Any

from groq import Groq

import config

client = Groq(api_key=config.GROQ_API_KEY) if config.GROQ_API_KEY else None


def clean_json_response(raw_text: str) -> dict[str, Any]:
    """Extract and parse JSON safely even if wrapped in markdown codeblocks"""
    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        return {"summary": text[:400], "detailed_analysis": text, "industry": "Technology", "tech_stack": []}


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

    clean_sample = scraped_text[:7000]

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
        response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are an elite technical profiler. Always respond with detailed, structured, valid JSON. Be thorough, concrete, and concise."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=850,
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

    sample_resume = resume_text[:8000]

    prompt = f"""You are an executive talent evaluator and senior engineering leader.
Perform a concise, comprehensive technical analysis (200-300 words) of this candidate's resume for the target role: "{target_role or 'Software Engineer'}".

Candidate Resume Content:
---
{sample_resume}
---

Your response MUST be a valid JSON object matching this schema:
{{
  "full_name": "Candidate Full Name (or 'Candidate' if not explicitly stated)",
  "target_role": "{target_role if target_role else 'Software Engineer'}",
  "elevator_pitch": "1-2 punchy sentences summarizing candidate's unique technical superpower and key strengths",
  "detailed_profile_analysis": "Structured candidate technical evaluation with Markdown sections: ### 1. Engineering Archetype\\nAnalysis of candidate's technical identity and maturity.\\n\\n### 2. Core Technical Strengths\\nCategorized skills across languages, frameworks, and databases.\\n\\n### 3. Key Accomplishments & Scale\\nKey achievements with metrics and business impact.\\n\\n### 4. Strategic Job Fit\\nPositioning narrative for this target role.",
  "top_skills": ["Skill1", "Skill2", "Skill3", "Skill4", "Skill5", "Skill6"],
  "experience_years": "Estimated total years of technical experience (e.g. 3+ years, 5+ years)",
  "key_achievements": [
    "High-impact achievement 1 with technical metrics",
    "High-impact achievement 2 with technologies used",
    "High-impact achievement 3 with system scale and results"
  ]
}}
"""

    try:
        response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are an executive technical talent matcher. Always respond with detailed, structured, valid JSON. Be concise, punchy, and high-impact."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        return clean_json_response(response.choices[0].message.content)
    except Exception as e:
        print(f"[AI Agent Error] parse_resume_text failed: {e}")
        return {
            "full_name": "Candidate",
            "target_role": target_role or "Software Engineer",
            "elevator_pitch": "Engineered scalable applications and automated workflows.",
            "detailed_profile_analysis": "Technical Assessment:\n\nCandidate demonstrates proficiency in full-stack engineering and software delivery.",
            "top_skills": ["Python", "FastAPI", "React", "PostgreSQL"],
            "experience_years": "2+ years",
            "key_achievements": ["Developed scalable web applications and data pipelines"]
        }


def generate_personalized_pitch(
    candidate_profile: dict[str, Any],
    company_name: str,
    company_profile: dict[str, Any],
    contact_name: str = "Hiring Team"
) -> dict[str, Any]:
    """
    Synthesizes the 500-700 word company intelligence report with the 500-700 word
    candidate technical assessment to create a laser-targeted 1-to-1 cold email and cover letter.
    """
    candidate_name = candidate_profile.get("full_name", "Candidate")
    target_role = candidate_profile.get("target_role", "Software Engineer")
    skills = ", ".join(candidate_profile.get("top_skills", []))
    achievements = "\n".join([f"- {a}" for a in candidate_profile.get("key_achievements", [])])
    candidate_deep_analysis = candidate_profile.get("detailed_profile_analysis", "")
    resume_link = (candidate_profile.get("resume_link") or "").strip()

    company_summary = company_profile.get("summary", "")
    company_deep_analysis = company_profile.get("detailed_analysis", "")
    company_tech = ", ".join(company_profile.get("tech_stack", []))
    company_industry = company_profile.get("industry", "Tech")

    resume_link_instruction = f"Candidate Resume/Portfolio Link: {resume_link}\nInclude this live link naturally in the call to action or closing of the email so the hiring team can review candidate's work directly." if resume_link else "Mention that candidate is ready to share complete resume and work samples upon reply."

    prompt = f"""You are an elite engineering talent strategist and cold email copywriter.
You are helping an engineer ({candidate_name}) send a direct, high-impact cold application / talent inquiry email to an engineering leader, founder, or hiring manager at {company_name}.
This email is strictly a JOB OPPORTUNITY / TALENT APPLICATION outreach, NOT a sales pitch or service inquiry.

Target Company: {company_name}
Industry: {company_industry}
Active Tech Stack: {company_tech}
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

Rules for the Cold Email (Job Opportunity Outreach):
1. Subject line: 5-8 words. Direct, professional, and clear about the role and value (e.g. "{target_role} Application - {candidate_name} - {company_name}" or "{candidate_name} - {target_role} Inquiry for {company_name}").
2. Word count: 120-160 words. Authentic, engineering-focused, zero corporate sales fluff.
3. Structure:
   - Genuine Hook: Specifically reference a product, feature, or tech stack initiative {company_name} builds from the intelligence profile.
   - Value Bridge: Explicitly link candidate's core skills and quantified achievements to how candidate can solve engineering challenges, scale systems, or ship features for {company_name}.
   - Clear Job Opportunity CTA: Inquire about current or upcoming engineering openings for {target_role}. If a resume link was provided, include it cleanly.
4. Sign-off: Professional with candidate's name.

Return ONLY a valid JSON object matching this schema:
{{
  "subject_line": "Direct job inquiry subject line",
  "email_body": "Full body of cold email (with natural line breaks)",
  "cover_letter": "A 250-300 word tailored cover letter aligning candidate experience with company mission and engineering stack",
  "matched_skills": ["Skill 1", "Skill 2", "Skill 3"]
}}
"""

    if not client:
        resume_mention = f"You can also view my complete resume and project portfolio here: {resume_link}\n\n" if resume_link else ""
        return {
            "subject_line": f"{target_role} Opportunity - {candidate_name} | {company_name}",
            "email_body": f"Hi {contact_name},\n\nI’ve been following {company_name}'s work in {company_industry} and love how your team builds systems using {company_tech or 'modern engineering stacks'}.\n\nAs a {target_role} specializing in {skills}, I’ve recently delivered high-impact engineering projects, including architecting scalable services and high-throughput APIs.\n\n{resume_mention}I'm writing to inquire about open {target_role} opportunities or upcoming engineering team expansion at {company_name}. Would you be open to discussing how my background could support your product roadmap?\n\nBest regards,\n{candidate_name}",
            "cover_letter": f"Dear Hiring Team at {company_name},\n\nI am writing to express my strong enthusiasm for joining {company_name} as a {target_role}. With extensive hands-on experience across {skills}, I have built resilient systems and solved complex engineering problems that align directly with your technical goals.\n\nI would welcome the opportunity to discuss how my technical skills can drive impactful results for {company_name}.\n\nSincerely,\n{candidate_name}",
            "matched_skills": candidate_profile.get("top_skills", [])[:3]
        }

    try:
        response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are an elite technical talent copywriter crafting direct job opportunity cold emails. Output pure JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        return clean_json_response(response.choices[0].message.content)
    except Exception as e:
        print(f"[AI Agent Error] generate_personalized_pitch failed: {e}")
        return {
            "subject_line": f"{target_role} Inquiry - {candidate_name} for {company_name}",
            "email_body": f"Hi {contact_name},\n\nI’ve been following {company_name} and really admire what your engineering team is shipping. As a {target_role} experienced in {skills}, I specialize in building robust, performant software.\n\nI'm actively exploring {target_role} opportunities and would love to know if {company_name} is currently looking for talented engineers to join the team. I'd be glad to share my resume and work samples.\n\nWould you be open to pointing me toward the appropriate engineering hiring manager?\n\nBest regards,\n{candidate_name}",
            "cover_letter": f"Dear Hiring Team at {company_name},\n\nI am writing to apply for {target_role} opportunities at {company_name}...",
            "matched_skills": candidate_profile.get("top_skills", [])[:2]
        }


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
            response = client.chat.completions.create(
                model=config.GROQ_MODEL,
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

