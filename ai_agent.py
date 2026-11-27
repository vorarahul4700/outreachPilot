import itertools
import json
import re
import time
from typing import Any

from groq import Groq
try:
    import httpx
except ImportError:
    httpx = None
import requests

import config


class AIMessage:
    def __init__(self, content: str):
        self.content = content


class AIChoice:
    def __init__(self, content: str):
        self.message = AIMessage(content)


class AIResponse:
    def __init__(self, content: str):
        self.choices = [AIChoice(content)]


# Groq Multi-Account Client Pool
_GROQ_CLIENT_POOL = [
    Groq(api_key=k) for k in config.GROQ_API_KEYS
] if config.GROQ_API_KEYS else ([Groq(api_key=config.GROQ_API_KEY)] if config.GROQ_API_KEY else [])

_groq_counter = itertools.count()
_gemini_counter = itertools.count()

# Primary client reference for legacy boolean truthy checks
client = _GROQ_CLIENT_POOL[0] if _GROQ_CLIENT_POOL else (True if config.GEMINI_API_KEYS else None)

_ROTATING_GROQ_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b"]
_groq_model_counter = itertools.count()

_EXHAUSTED_GROQ_CLIENTS: dict[int, float] = {}
_EXHAUSTED_GEMINI_KEYS: dict[str, float] = {}


def is_groq_cooling_down(client_idx: int) -> bool:
    exp = _EXHAUSTED_GROQ_CLIENTS.get(client_idx)
    if not exp:
        return False
    if time.time() < exp:
        return True
    _EXHAUSTED_GROQ_CLIENTS.pop(client_idx, None)
    return False


def mark_groq_cooldown(client_idx: int, cooldown_seconds: int = 180):
    _EXHAUSTED_GROQ_CLIENTS[client_idx] = time.time() + cooldown_seconds


def is_gemini_cooling_down(key: str) -> bool:
    exp = _EXHAUSTED_GEMINI_KEYS.get(key)
    if not exp:
        return False
    if time.time() < exp:
        return True
    _EXHAUSTED_GEMINI_KEYS.pop(key, None)
    return False


def mark_gemini_cooldown(key: str, cooldown_seconds: int = 120):
    _EXHAUSTED_GEMINI_KEYS[key] = time.time() + cooldown_seconds


def call_gemini_single_key(
    key: str,
    messages: list[dict],
    temperature: float = 0.2,
    max_tokens: int = 2200,
    response_format: dict = None,
    model: str = "gemini-3.5-flash"
) -> AIResponse:
    """
    Executes a prompt against Google Gemini using the direct Google AI Studio REST protocol.
    Supports official AQ. authentication keys, JSON output enforcement, and fallback model cascade.
    """
    clean_model = model.replace("models/", "")
    models_to_try = [clean_model]
    for alt in ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash"]:
        if alt not in models_to_try:
            models_to_try.append(alt)

    contents = []
    system_text = None
    for m in messages:
        role = m.get("role", "user")
        c_text = m.get("content", "")
        if role == "system":
            system_text = c_text
        else:
            c_role = "user" if role == "user" else "model"
            contents.append({"role": c_role, "parts": [{"text": c_text}]})

    if not contents and system_text:
        contents.append({"role": "user", "parts": [{"text": system_text}]})
        system_text = None

    gen_config = {"temperature": temperature}
    if max_tokens:
        gen_config["maxOutputTokens"] = max_tokens
    if response_format and response_format.get("type") == "json_object":
        gen_config["responseMimeType"] = "application/json"

    # Long answers (resume reports, research) take longer than the 25 s short calls get.
    request_timeout = 25.0 if not max_tokens or max_tokens <= 1000 else 75.0

    last_gem_err = None
    for target_m in models_to_try:
        model_config = dict(gen_config)
        if target_m == "gemini-3.5-flash":
            # This model thinks before it answers, and the thinking counts against
            # maxOutputTokens. Uncapped, it spent 1,889 of 3,200 tokens thinking on a resume
            # and the JSON came back cut off (finishReason MAX_TOKENS). Capping thinking keeps
            # the answer whole and roughly halves the time (measured 2026-11-16). Short
            # requests get no thinking so a small budget cannot be used up by it.
            model_config["thinkingConfig"] = {"thinkingBudget": 512 if (max_tokens or 0) >= 2000 else 0}
        native_payload = {
            "contents": contents,
            "generationConfig": model_config
        }
        if system_text:
            native_payload["systemInstruction"] = {"parts": [{"text": system_text}]}
        native_url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_m}:generateContent?key={key}"
        try:
            if httpx:
                with httpx.Client(timeout=request_timeout) as h_client:
                    r = h_client.post(native_url, json=native_payload)
            else:
                r = requests.post(native_url, json=native_payload, timeout=request_timeout)

            if r.status_code == 200:
                data = r.json()
                candidate = (data.get("candidates") or [{}])[0]
                parts = candidate.get("content", {}).get("parts", [])
                text_content = "".join(p.get("text", "") for p in parts)
                finish = candidate.get("finishReason")
                # A 200 can still carry a cut-off or empty answer. Treat it as a failure so
                # the next model (or key, or provider) gets a turn instead of the caller
                # failing to parse half a JSON object.
                if not text_content.strip() or finish == "MAX_TOKENS":
                    last_gem_err = f"Gemini model {target_m} returned an incomplete answer (finishReason {finish}, {len(text_content)} chars)"
                    continue
                return AIResponse(text_content)
            elif r.status_code == 429:
                raise RuntimeError(f"Gemini 429 Rate Limit ({key[:8]}...): {r.text}")
            elif r.status_code in (404, 503):
                last_gem_err = f"Gemini model {target_m} returned {r.status_code}: {r.text[:100]}"
                continue
            else:
                last_gem_err = f"Gemini error {r.status_code}: {r.text[:150]}"
        except Exception as e:
            if "429" in str(e).lower() or "quota" in str(e).lower() or "rate limit" in str(e).lower():
                raise
            last_gem_err = str(e)
            continue

    raise RuntimeError(f"All Gemini models failed on key {key[:8]}... Last error: {last_gem_err}")


def call_ai_with_fallback(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 450,
    response_format: dict = None,
    prefer_provider: str = "auto"
):
    """
    Unified multi-provider AI engine with automatic multi-account key pooling and failover.
    Distributes queries across Google Gemini (4 accounts, 1M TPM) and Groq (4 accounts, ultra-fast)
    to completely prevent rate-limit throttling and token exhaustion.
    """
    has_gemini = bool(config.GEMINI_API_KEYS)
    has_groq = bool(_GROQ_CLIENT_POOL)

    if not has_gemini and not has_groq:
        raise RuntimeError("No active AI provider API keys available (checked Gemini and Groq).")

    # Routing strategy:
    # Large context / enrichment tasks (>1000 tokens) -> Gemini primary (1M TPM)
    # Fast pitch / short tasks -> Groq primary (<500ms response time)
    if prefer_provider == "gemini":
        providers = ["gemini", "groq"]
    elif prefer_provider == "groq":
        providers = ["groq", "gemini"]
    else:
        if max_tokens and max_tokens > 1000:
            providers = ["gemini", "groq"]
        else:
            providers = ["groq", "gemini"]

    last_exc = None
    for prov in providers:
        if prov == "gemini" and has_gemini:
            available_keys = [k for k in config.GEMINI_API_KEYS if not is_gemini_cooling_down(k)]
            if not available_keys:
                continue

            start_idx = next(_gemini_counter) % len(available_keys)
            ordered_keys = available_keys[start_idx:] + available_keys[:start_idx]

            for gem_key in ordered_keys:
                try:
                    return call_gemini_single_key(
                        key=gem_key,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format=response_format,
                        model=config.GEMINI_MODEL
                    )
                except Exception as e:
                    last_exc = e
                    err_str = str(e).lower()
                    if "429" in err_str or "rate limit" in err_str or "quota" in err_str:
                        mark_gemini_cooldown(gem_key, cooldown_seconds=120)
                    continue

        elif prov == "groq" and has_groq:
            available_indices = [
                i for i in range(len(_GROQ_CLIENT_POOL))
                if not is_groq_cooling_down(i)
            ]
            if not available_indices:
                continue

            start_rot = next(_groq_counter) % len(available_indices)
            ordered_indices = available_indices[start_rot:] + available_indices[:start_rot]

            next_idx = next(_groq_model_counter)
            primary = _ROTATING_GROQ_MODELS[next_idx % len(_ROTATING_GROQ_MODELS)]
            candidate_models = [primary] + [m for m in _ROTATING_GROQ_MODELS if m != primary]

            for c_idx in ordered_indices:
                active_client = _GROQ_CLIENT_POOL[c_idx]
                client_rate_limited = False
                for model_name in candidate_models:
                    if client_rate_limited:
                        break
                    for rf in [response_format, None]:
                        try:
                            kwargs = {
                                "model": model_name,
                                "messages": messages,
                                "temperature": temperature,
                            }
                            if max_tokens:
                                # Groq qwen/qwen3.8-27b has an Output Tokens Per Minute (OTPM) limit of 1000
                                kwargs["max_tokens"] = min(max_tokens, 950)
                            if rf:
                                kwargs["response_format"] = rf
                            return active_client.chat.completions.create(**kwargs)
                        except Exception as e:
                            last_exc = e
                            err_str = str(e).lower()
                            if "tpd" in err_str or "tokens per day" in err_str:
                                mark_groq_cooldown(c_idx, cooldown_seconds=180)
                                client_rate_limited = True
                                break
                            elif "429" in err_str or "rate limit" in err_str:
                                client_rate_limited = True
                                break
                            elif rf and "json_validate_failed" in err_str:
                                break  # this model can't produce the JSON; try the next model, not free text
                            continue

    if last_exc:
        raise last_exc
    raise RuntimeError("All configured AI keys (Gemini & Groq) are currently in cooldown.")


# Backward compatibility alias - legacy callers use call_groq_with_fallback seamlessly
call_groq_with_fallback = call_ai_with_fallback


def clean_json_response(raw_text: str) -> dict[str, Any]:
    """Extract and parse JSON safely even if wrapped in markdown codeblocks or containing unescaped control chars."""
    text = (raw_text or "").strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text, strict=False)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1], strict=False)
            except Exception:
                pass
        return {}


def sanitize_human_text(text: str) -> str:
    """
    Cleans text to strictly adhere to natural human writing:
    - Em dashes and en dashes -> simple hyphen (-)
    - Curly quotes -> straight quotes (" ')
    - Unicode ellipsis -> ...
    - Structural emojis removed
    - Non-breaking spaces and zero-width characters removed
    """
    if not text or not isinstance(text, str):
        return text or ""
    
    cleaned = text
    cleaned = cleaned.replace("\u2014", " - ").replace("\u2013", "-")
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")
    cleaned = cleaned.replace("\u2026", "...")
    cleaned = cleaned.replace("\u00a0", " ").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    cleaned = cleaned.replace("\u202f", " ").replace("\u2009", " ").replace("\ufeff", "")
    cleaned = cleaned.replace("\u2011", "-").replace("\u2010", "-")
    # Strip emojis and special bullets/crosses using escaped codepoints
    cleaned = re.sub(
        r"[\U0001f680\u2728\U0001f4a1\U0001f525\U0001f3af\U0001f4cc\U0001f511\u26a1\U0001f6e0\U0001f4c8\U0001f9e0\U0001f31f\U0001f4bc\U0001f50d\u2705\u274c\u26a0\u2713\u2714\u2717\u2022\u00b7\u25b8\u25b6\u25ba]",
        "",
        cleaned
    )
    cleaned = re.sub(r" +", " ", cleaned)
    cleaned = re.sub(r" - - ", " - ", cleaned)
    return cleaned.strip()


def extract_high_signal_text(text: str, max_chars: int = 5000) -> str:
    """
    Pre-filters raw scraped website text by stripping repetitive navigation menus,
    footer copyright links, and cookie notices. Preserves 100% of the actual company bio,
    services, tech stack, and portfolio facts while drastically speeding up LLM prompt evaluation.
    """
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    seen = set()
    filtered = []
    skip_keywords = (
        "cookie", "privacy policy", "terms of use", "terms & conditions",
        "all rights reserved", "copyright", "designed by", "powered by",
        "accept cookies", "decline cookies", "manage preferences"
    )
    for l in lines:
        lower = l.lower()
        if any(k in lower for k in skip_keywords) and len(l) < 140:
            continue
        if lower in seen and len(l) < 200:
            continue
        seen.add(lower)
        filtered.append(l)
    return "\n".join(filtered)[:max_chars]


def sanitize_human_text(text: str) -> str:
    """
    Cleans text to strictly adhere to natural human writing:
    - Em dashes and en dashes -> simple hyphen (-)
    - Curly quotes -> straight quotes (" ')
    - Unicode ellipsis -> ...
    - Structural emojis removed
    - Non-breaking spaces and zero-width characters removed
    """
    if not text or not isinstance(text, str):
        return text or ""
    
    cleaned = text
    cleaned = cleaned.replace("\u2014", " - ").replace("\u2013", "-")
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")
    cleaned = cleaned.replace("\u2026", "...")
    cleaned = cleaned.replace("\u00a0", " ").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    cleaned = cleaned.replace("\u202f", " ").replace("\u2009", " ").replace("\ufeff", "")
    cleaned = cleaned.replace("\u2011", "-").replace("\u2010", "-")
    # Strip emojis and special bullets/crosses using escaped codepoints
    cleaned = re.sub(
        r"[\U0001f680\u2728\U0001f4a1\U0001f525\U0001f3af\U0001f4cc\U0001f511\u26a1\U0001f6e0\U0001f4c8\U0001f9e0\U0001f31f\U0001f4bc\U0001f50d\u2705\u274c\u26a0\u2713\u2714\u2717\u2022\u00b7\u25b8\u25b6\u25ba]",
        "",
        cleaned
    )
    cleaned = re.sub(r" +", " ", cleaned)
    cleaned = re.sub(r" - - ", " - ", cleaned)
    return cleaned.strip()


TECH_CATALOG = {
    # Languages
    "Python": r"\bpython\b", "JavaScript": r"\bjavascript\b|\bjs\b", "TypeScript": r"\btypescript\b|\bts\b",
    "PHP": r"\bphp\b", "Java": r"\bjava\b(?!script)", "Kotlin": r"\bkotlin\b", "Swift": r"\bswift\b",
    "Dart": r"\bdart\b", "Go": r"\bgolang\b|\bgo language\b", "C# / .NET": r"\bc#\b|\b\.net\b|\basp\.net\b",
    "Ruby": r"\bruby\b|\brails\b", "Rust": r"\brust\b",
    # Frontend
    "React": r"\breact\b|\breact\.js\b|\breactjs\b", "Next.js": r"\bnext\.js\b|\bnextjs\b",
    "Angular": r"\bangular\b|\bangularjs\b", "Vue.js": r"\bvue\b|\bvue\.js\b|\bvuejs\b",
    "Nuxt.js": r"\bnuxt\b|\bnuxt\.js\b", "HTML5 / CSS3": r"\bhtml5\b|\bcss3\b",
    "Tailwind CSS": r"\btailwind\b", "Bootstrap": r"\bbootstrap\b",
    # Mobile
    "Flutter": r"\bflutter\b", "React Native": r"\breact native\b",
    "iOS Development": r"\bios development\b|\bios app\b|\biphone app\b|\bios\b",
    "Android Development": r"\bandroid development\b|\bandroid app\b|\bandroid\b",
    # Backend
    "Node.js": r"\bnode\.js\b|\bnodejs\b", "Express.js": r"\bexpress\.js\b|\bexpressjs\b",
    "NestJS": r"\bnestjs\b", "Laravel": r"\blaravel\b", "Django": r"\bdjango\b",
    "FastAPI": r"\bfastapi\b", "Spring Boot": r"\bspring boot\b",
    # Databases & Cloud
    "PostgreSQL": r"\bpostgresql\b|\bpostgres\b", "MySQL": r"\bmysql\b", "MongoDB": r"\bmongodb\b|\bmongo\b",
    "Redis": r"\bredis\b", "Firebase": r"\bfirebase\b", "Supabase": r"\bsupabase\b",
    "AWS": r"\baws\b|\bamazon web services\b", "Google Cloud (GCP)": r"\bgoogle cloud\b|\bgcp\b",
    "Microsoft Azure": r"\bazure\b|\bmicrosoft azure\b", "Docker": r"\bdocker\b",
    "Kubernetes": r"\bkubernetes\b|\bk8s\b", "CI/CD": r"\bci/cd\b|\bjenkins\b|\bgithub actions\b",
    # CMS & Tools
    "WordPress": r"\bwordpress\b", "Shopify": r"\bshopify\b", "Magento": r"\bmagento\b",
    "WooCommerce": r"\bwoocommerce\b", "Figma": r"\bfigma\b", "GraphQL": r"\bgraphql\b"
}

SERVICE_CATALOG = {
    "Mobile App Development": r"\bmobile app\b|\bandroid\b|\bios\b|\bflutter\b|\breact native\b",
    "Web Application Development": r"\bweb development\b|\bweb design\b|\bwebsite\b|\bfull stack\b",
    "UI/UX Design & Prototyping": r"\bui/ux\b|\bui ux\b|\buser interface\b|\bfigma\b",
    "Cloud & DevOps Infrastructure": r"\bcloud\b|\bdevops\b|\baws\b|\bazure\b|\bdocker\b",
    "Custom Software Engineering": r"\bcustom software\b|\bsoftware development\b|\benterprise software\b",
    "AI & Machine Learning Solutions": r"\bartificial intelligence\b|\bmachine learning\b|\bai/ml\b|\bai solutions\b",
    "QA & Software Testing": r"\bquality assurance\b|\bqa testing\b|\bsoftware testing\b",
    "E-Commerce Solutions": r"\be-commerce\b|\becommerce\b|\bshopify\b|\bwoocommerce\b|\bmagento\b",
    "Dedicated Resource Hiring": r"\bdedicated team\b|\bhire developers\b|\bstaff augmentation\b"
}

def scan_technologies(text: str) -> list[str]:
    found = []
    text_lower = text.lower()
    for tech_name, pattern in TECH_CATALOG.items():
        if re.search(pattern, text_lower, re.IGNORECASE):
            found.append(tech_name)
    return found

def scan_services(text: str) -> list[str]:
    found = []
    text_lower = text.lower()
    for srv_name, pattern in SERVICE_CATALOG.items():
        if re.search(pattern, text_lower, re.IGNORECASE):
            found.append(srv_name)
    return found


PARKED_OR_STUB_PATTERNS = (
    r"parked domain name on hostinger",
    r"manage it in your hostinger account",
    r"\bthis domain (?:is )?(?:for sale|parked)\b",
    r"\bdomain is for sale\b",
    r"\bbuy this domain\b",
    r"\binquire about this domain\b",
    r"\bsedo domain parking\b",
    r"\bhugedomains\b",
    r"\bafternic\b",
    r"\baccount suspended\b",
    r"\bjust a moment\.\.\.",
    r"enable javascript and cookies to continue",
    r"checking if the site connection is secure",
    r"attention required!\s*\|\s*cloudflare",
    r"\baccess denied\s*\|",
    r"welcome to wordpress\.\s*this is your first post\.",
    r"\bapache2? (?:ubuntu|debian) default page\b",
    r"\bwelcome to nginx!\b",
    r"\bplesk default page\b",
    r"\bwebsite coming soon\b",
)


def detect_parked_or_stub_reason(scraped_text: str, clean_sample: str) -> str | None:
    """Returns a non-empty reason if scraped content is a parked domain, hosting stub, or WAF/cookie block."""
    combined = f"{scraped_text or ''}\n{clean_sample or ''}".lower()
    if len(clean_sample.strip()) < 60:
        return "insufficient_content"
    # Pages that only repeat the title/domain (e.g. "Title: x.com x.com x.com") pass the length
    # check but give the model nothing, so it invents a profile. Require some real words.
    words = {w for w in re.findall(r"[a-z]{3,}", clean_sample.lower()) if w not in ("title", "www", "com", "http", "https")}
    if len(words) < 15:
        return "insufficient_content"
    for pattern in PARKED_OR_STUB_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            # Ignore generic "website coming soon" if the page otherwise has rich multi-section business copy
            if pattern in (r"\bwebsite coming soon\b", r"enable javascript and cookies to continue") and len(clean_sample) > 1800:
                continue
            return pattern
    return None


def analyze_company(company_name: str, domain: str, scraped_text: str) -> dict[str, Any]:
    """
    High-throughput hybrid business and technical intelligence extractor.
    Combines instantaneous deterministic tech & service scanning (1ms) with targeted
    AI synthesis grounded strictly in scraped website content.
    """
    # 1200 chars of the highest-signal text: measured same quality as 4000 at about a third of the cost
    clean_sample = extract_high_signal_text((scraped_text or "").strip(), max_chars=1200)
    stub_reason = detect_parked_or_stub_reason(scraped_text, clean_sample)
    if stub_reason:
        return {
            "summary": "",
            "detailed_analysis": (
                f"### No Readable Website Content Detected\n"
                f"Skipped AI synthesis for **{company_name}** (`{domain}`) because the site returned a "
                f"parked domain, hosting placeholder, cookie/WAF wall, or empty page (`{stub_reason}`)."
            ),
            "industry": "",
            "tech_stack": [],
            "services": [],
            "hiring_signals": "",
            "tone": "",
            "skipped": True,
            "skip_reason": stub_reason,
        }

    tech_detected = scan_technologies(scraped_text)
    srv_detected = scan_services(scraped_text)

    # Fixed instructions go in the system message so providers can reuse them from their prompt cache;
    # only the short company block below is new work for each call.
    system_msg = """You are a factual business research analyst. You read text scraped from a company's website and return ONLY a JSON object with exactly these keys:
{"summary": "2 short sentences: what the company does and its main offerings, from the text",
 "industry": "the primary industry of what this company itself sells or does (2-4 words). A shop that sells shoes online is Retail, not software",
 "hiring_signals": "open roles or hiring statements written in the text, else exactly: No explicit hiring signals",
 "differentiators": "1-2 concrete claims written in the text, else exactly: Not explicitly stated"}
Rules: use only facts written in the website text. Never invent technologies, clients, metrics or job openings. Keep every value short."""
    user_msg = f"Company: {company_name} ({domain})\nWebsite text:\n{clean_sample}"

    parsed = {}
    try:
        response = call_groq_with_fallback(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=260,
            response_format={"type": "json_object"},
        )
        parsed = clean_json_response(response.choices[0].message.content)
    except Exception:
        parsed = {}

    summary = (parsed.get("summary") or "").strip()
    industry = (parsed.get("industry") or "").strip()
    hiring_signals = (parsed.get("hiring_signals") or "").strip() or "No explicit hiring signals"
    diffs = (parsed.get("differentiators") or "").strip() or "Not explicitly stated"

    if not summary and not industry:
        return {
            "summary": "",
            "detailed_analysis": (
                f"### No Readable Website Content Detected\n"
                f"AI synthesis did not return a valid grounded profile for **{company_name}** (`{domain}`)."
            ),
            "industry": "",
            "tech_stack": tech_detected,
            "services": srv_detected,
            "hiring_signals": "",
            "tone": "",
            "skipped": True,
            "skip_reason": "empty_llm_output",
        }

    if not summary:
        summary = f"{company_name} operates in {industry or 'commercial services'} based on content extracted from {domain}."
    if not industry:
        industry = "General Business Services"

    langs = [t for t in tech_detected if t in ("Python", "JavaScript", "TypeScript", "PHP", "Java", "Kotlin", "Swift", "Dart", "Go", "C# / .NET", "Ruby", "Rust")]
    frontend = [t for t in tech_detected if t in ("React", "Next.js", "Angular", "Vue.js", "Nuxt.js", "HTML5 / CSS3", "Tailwind CSS", "Bootstrap", "Flutter", "React Native", "iOS Development", "Android Development")]
    backend = [t for t in tech_detected if t in ("Node.js", "Express.js", "NestJS", "Laravel", "Django", "FastAPI", "Spring Boot", "WordPress", "Shopify", "Magento", "WooCommerce")]
    cloud_db = [t for t in tech_detected if t in ("PostgreSQL", "MySQL", "MongoDB", "Redis", "Firebase", "Supabase", "AWS", "Google Cloud (GCP)", "Microsoft Azure", "Docker", "Kubernetes", "CI/CD", "Figma", "GraphQL")]

    services_bullets = "\n".join([f"- **{s}**" for s in srv_detected]) if srv_detected else f"- **{industry}** (see company website `{domain}` for full service catalog)"

    dossier = f"""### 1. Company Overview & Identity
- **Official Name:** {company_name}
- **Website:** {domain}
- **Primary Industry:** {industry}
- **Core Mission & Value Proposition:** {summary}

### 2. Services & Core Offerings
{services_bullets}

### 3. Detected Technology Stack
- **Programming Languages:** {', '.join(langs) if langs else 'None explicitly detected'}
- **Frontend & Mobile Frameworks:** {', '.join(frontend) if frontend else 'None explicitly detected'}
- **Backend & CMS Platforms:** {', '.join(backend) if backend else 'None explicitly detected'}
- **Databases & Cloud Infrastructure:** {', '.join(cloud_db) if cloud_db else 'None explicitly detected'}

### 4. Key Differentiators
- {diffs}

### 5. Hiring & Growth Signals
- **Hiring Signals:** {hiring_signals}"""

    return {
        "summary": summary,
        "detailed_analysis": dossier,
        "industry": industry,
        "tech_stack": tech_detected,
        "services": srv_detected,
        "hiring_signals": hiring_signals,
        "tone": "Professional"
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

Step 1: Identify the resume archetype.
Classify it as: Fresher/Entry-level, Early-career (1-3 yrs), Mid-level (4-7 yrs), Senior (8+ yrs), Career-switcher, Freelancer/Consultant, Creative/Portfolio-based, or Non-technical/Business. Note the domain based strictly on their actual work.

Step 2: Extract and structure:

Candidate Snapshot: Name, total years of experience, current/most recent role and company, education and CGPA/grade, location and contact signals.

Skills Inventory (grouped): Languages, frameworks, databases, cloud/tools, soft skills. Only include technologies explicitly listed or used in their projects/jobs.

Experience Highlights: For each role: company, duration, scope. Pull out every quantified achievement (%, time saved, revenue, users, scale) that appears in the text. State the business impact.

Project Deep-Dives: For each project: problem, stack, what was built, measurable outcome, complexity.

Strong Points (The Differentiators): List 4-6 specific, evidence-backed strengths directly proven by their bullets.

Gaps & Risks: Honest evaluation of gaps relative to the target role ({default_role}).

Best-Fit Roles: 3-5 job titles the candidate is realistically competitive for based on their actual resume stack.

ATS Keyword Extract: 20-30 relevant keywords verified in their profile.

Step 3: Output format. Return a strictly valid JSON object matching this schema:
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
  "detailed_profile_analysis": "Detailed technical report with clear headings matching Step 1 and Step 2. Reference the exact resume bullets. Never invent anything."
}}

Target Role Context: {default_role}

Candidate Resume:
---
{sample_resume}
---"""

    # The report needs about 2,000 output tokens. Groq answers are capped at 950 tokens, so they
    # arrive cut off, and small local models often return malformed or differently shaped JSON.
    # Ask Gemini first (the second Gemini attempt rotates to the next key), use Groq only as a
    # last resort, and accept an answer only when it has the fields the app needs.
    parsed = None
    last_error: Exception | None = None
    for provider in ("gemini", "gemini", "groq"):
        try:
            response = call_groq_with_fallback(
                messages=[
                    {"role": "system", "content": "You are a Senior Technical Recruiter and Hiring Manager. Ground all analysis strictly and 100% in the provided resume. Never fabricate projects, numbers, or tech stacks."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=3200,
                response_format={"type": "json_object"},
                prefer_provider=provider
            )
        except Exception as e:
            last_error = e
            continue
        candidate = clean_json_response(response.choices[0].message.content)
        if (isinstance(candidate, dict) and isinstance(candidate.get("top_skills"), list)
                and candidate.get("top_skills") and candidate.get("elevator_pitch")):
            parsed = candidate
            break
        print(f"[AI Agent] Resume analysis from {provider} was not complete JSON; trying again.")
    if not parsed:
        if last_error:
            print(f"[AI Agent] Resume analysis provider error: {last_error}")
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


def build_fit_points(raw: Any, candidate_profile: dict[str, Any]) -> list[str]:
    """Keep only fit pairs whose resume side is really in the resume, and write the bullet ourselves,
    so the AI can't invent or embellish a claim. Achievements are quoted; skills become "I work with X"."""
    def norm(t: Any) -> str:
        return re.sub(r"[^a-z0-9%+#.]+", " ", str(t).lower()).strip(" .")

    # Both lists: the prompt shows strong_points first, key_achievements otherwise.
    achievements = {norm(a): str(a).strip().rstrip(".") for a in (list(candidate_profile.get("strong_points") or []) + list(candidate_profile.get("key_achievements") or [])) if str(a).strip()}
    skills = {norm(k): str(k).strip() for k in (candidate_profile.get("top_skills") or []) if str(k).strip()}
    points, used = [], set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        company = re.sub(r"\[.*?\]", "", str(item.get("company_fact") or "")).strip(" .-:")
        key = norm(item.get("resume_fact") or "")
        if not company or not key or key in used or len(company.split()) > 12:
            continue
        if key in achievements:
            resume_text = achievements[key]
            if len(resume_text) > 150:
                continue  # a whole paragraph is too long for a bullet
        elif key in skills:
            resume_text = f"I work with {skills[key]}"
        else:
            # A list of skills ("Python, FastAPI, PostgreSQL") counts if every item is a real resume skill;
            # name the ones the company side mentions, else the first two.
            parts = [norm(x) for x in re.split(r",|/|and", str(item.get("resume_fact") or "")) if norm(x)]
            if not parts or any(x not in skills for x in parts):
                continue  # not word for word from the resume: drop it
            named = [skills[x] for x in parts if skills[x].lower() in company.lower()] or [skills[x] for x in parts[:2]]
            resume_text = "I work with " + " and ".join(named[:2])
        used.add(key)
        points.append(f"{company[0].upper() + company[1:]}: {resume_text[0].upper() + resume_text[1:]}")
        if len(points) == 3:
            break
    return points


def add_fit_section(body: str, company_name: str, points: list[str]) -> str:
    """Put a "Why I fit <company>" list above the sign-off (or at the end if there is none)."""
    if not points:
        return body
    section = f"Why I fit {company_name}:\n" + "\n".join(f"- {p}" for p in points)
    m = re.search(r"\n\s*(Best regards|Warm regards|Kind regards|Regards|Thanks|Thank you)\b", body, flags=re.IGNORECASE)
    if m:
        return body[:m.start()].rstrip() + "\n\n" + section + "\n\n" + body[m.start():].lstrip("\n")
    return body.rstrip() + "\n\n" + section


def generate_personalized_pitch(
    candidate_profile: dict[str, Any],
    company_name: str,
    company_profile: dict[str, Any],
    contact_name: str = "",
    email_style: str = "tailored",
) -> dict[str, Any]:
    """
    email_style (from the user's plan): "standard" = short, general application using only the
    company's name and category; "tailored" = written around the company's research;
    "tailored_fit" = tailored plus a "Why I fit <company>" section (same AI call).

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

    fit_schema = ('\n  "fit_points": [{"company_fact": "Your ...", "resume_fact": "exact skill or achievement from (A)"}],'
                  if email_style == "tailored_fit" else "")
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

Deliverables (must return valid JSON matching this schema; keep it short, no extra keys):
{{
  "subject_line": "Clear subject, e.g. Application: {target_role} - {candidate_name}",
  "primary_email": "Primary cold job outreach email under 110 words",
  "variant_a_linkedin": "LinkedIn connection note to one person who works at {company_name}, UNDER 280 CHARACTERS (LinkedIn's limit). Start with 'Hi,' (the sender adds the name). Say who {candidate_name} is ({target_role}), name one skill that matches {company_name}'s work, say they are interested in {target_role} roles there, and ask to connect. No subject, no resume mention, no 'team' greeting, end with just the first name.",
  "variant_b_referral": "Message to one employee at {company_name} asking for a referral, under 90 words. Start with 'Hi,'. Say {candidate_name} is applying for {target_role} roles at {company_name}, give one verified resume achievement, ask if they would be open to referring them or pointing them to the right person, and offer to share the resume. Polite, no pressure. Sign off with {candidate_name}.",{fit_schema}
  "matched_skills": ["Skill1", "Skill2", "Skill3"]
}}"""

    if email_style == "tailored_fit":
        prompt += f"""

"fit_points" (REQUIRED in the JSON above for this email): pair things about {company_name} with the candidate's resume.
- company_fact: what {company_name} does or uses, from (B) above, starting with "Your", at most 8 words.
- resume_fact: COPIED EXACTLY, word for word, from Core Verified Skills (one skill) or Evidence-Backed Achievements (one full line) in (A).
Only pair things that genuinely relate. Use [] if nothing relates. Do NOT put these points inside the email body."""
    elif email_style == "standard":
        # Short general application: company name and category only, no company research.
        prompt = f"""Write a short, polite cold JOB APPLICATION email from a job seeker to {company_name}.

Candidate: {candidate_name}, {target_role}. Skills: {skills}.
One resume achievement to mention if present: {(raw_strong[0] if raw_strong else '')}
Company: {company_name} ({company_industry or 'their industry'}).

Rules:
- Greet strictly with "{greeting}". Never use bracket placeholders.
- Say who the candidate is, their role and 2-3 top skills, and ask whether {company_name} has open or upcoming {target_role} roles.
- {resume_instruction}
- Do not describe the company's products, services or tech; this is a general application.
- Never invent numbers or projects. Under 80 words. No sales language, no "quick call".
- Sign off with:
  Best regards,
  {candidate_name}

Return pure JSON: {{"subject_line": "Application: {target_role} - {candidate_name}", "primary_email": "...", "email_body": "same as primary_email", "matched_skills": ["..."]}}"""

    def make_pitch_fallback():
        raw_proofs = candidate_profile.get("key_achievements") or candidate_profile.get("strong_points") or []
        # Template used only when every AI provider fails: it states nothing that is not in the resume.
        proof = (raw_proofs[0] or "").strip().rstrip(".") if raw_proofs else ""
        skills_txt = f" specializing in {skills}" if skills else ""
        resume_ref = f" (Portfolio / Resume: {resume_link})" if resume_link else " (Resume attached)"
        comp_tech_focus = company_tech.split(',')[0].strip() if company_tech else (company_services.split(',')[0].strip() if company_services else "")

        primary = (
            f"{greeting}\n\n"
            f"I am writing to inquire about open or upcoming {target_role} opportunities at {company_name}.\n\n"
            f"As a {target_role}{skills_txt}" + (f", my recent work includes {proof}. " if proof else ". ") +
            (f"Given {company_name}'s focus on {comp_tech_focus}, I" if comp_tech_focus else "I") +
            " would love to contribute my experience to your engineering team.\n\n" +
            f"I have shared my resume for your consideration{resume_ref}. Are you currently hiring for {target_role} roles, or open to a brief conversation if there might be a potential fit?\n\n"
            f"Best regards,\n"
            f"{candidate_name}"
        )

        linkedin = (
            f"Hi {contact_name or company_name + ' team'},\n\n"
            f"I am reaching out to explore potential {target_role} opportunities at {company_name}. "
            + (f"I specialize in {skills}. " if skills else "") + (f"Recently: {proof}. " if proof else "") +
            (f"Given your work with {comp_tech_focus}, " if comp_tech_focus else "") +
            f"I'd love to connect and share my resume{resume_ref} if you have any open engineering roles.\n\n"
            f"Best regards,\n{candidate_name}"
        )

        referral = (
            f"{greeting}\n\n"
            f"I have been following {company_name}'s work in {company_industry or 'technology'} and wanted to reach out regarding potential {target_role} openings.\n\n"
            f"In my background as a {target_role}" + (f", I focus on {skills}" if skills else "") +
            (f", where I {proof}. " if proof else ". ") +
            (f"I really admire the work your team is doing around {comp_tech_focus} and would" if comp_tech_focus else "I would") +
            " welcome the chance to explore how my skills could add value to your projects.\n\n" +
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
        # Groq first: about 3 s per draft against 20 s on Gemini (measured 2026-11-16).
        # Groq can return an empty or cut-off answer (950-token cap, reasoning model), so
        # Gemini gets a turn before the template email is ever used.
        parsed = {}
        for provider in ("groq", "gemini"):
            try:
                response = call_groq_with_fallback(
                    messages=[
                        {"role": "system", "content": "You are a senior technical talent advisor and candidate career strategist. You write direct, respectful cold job application outreach from technical candidates to engineering teams. Never use bracket placeholders. Never pitch products or sales services. Connect candidate proof points to company engineering needs with precision. Return pure JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1500,
                    response_format={"type": "json_object"},
                    prefer_provider=provider
                )
            except Exception as e:
                print(f"[AI Agent] Draft from {provider} failed: {e}")
                continue
            candidate = clean_json_response(response.choices[0].message.content)
            if (isinstance(candidate, dict) and (candidate.get("subject_line") or "").strip()
                    and (candidate.get("primary_email") or candidate.get("email_body") or "").strip()):
                parsed = candidate
                break
            print(f"[AI Agent] Draft from {provider} was not complete JSON; trying the next provider.")
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

        if email_style == "tailored_fit":
            parsed["fit_points"] = build_fit_points(parsed.get("fit_points"), candidate_profile)
            body = add_fit_section(body, company_name, parsed["fit_points"])

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

