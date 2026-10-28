"""
OutreachPilot - Google Local Scraper Engine
Module: scraper_engine.py
Architecture: SeleniumBase (Undetected Chrome) + ThreadPoolExecutor for Parallel Website Resolution
"""

import os
import re
import shutil
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
from bs4 import BeautifulSoup
from seleniumbase import Driver

from config import is_safe_public_url

DISALLOWED_DOMAIN_SUFFIXES = (
    ".local",
    ".localhost",
    ".test",
    ".example",
    ".invalid",
    ".internal",
    ".lan",
    ".home",
    ".corp",
    ".dummy",
    ".fake",
    ".onion",
    ".null",
)

DISALLOWED_AGGREGATOR_DOMAINS = {
    "google.com",
    "google.co.in",
    "maps.google.com",
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "youtube.com",
    "wikipedia.org",
    "justdial.com",
    "sulekha.com",
    "indiamart.com",
    "tradeindia.com",
    "yelp.com",
    "yellowpages.com",
    "tripadvisor.com",
    "trustpilot.com",
    "glassdoor.com",
    "ambitionbox.com",
}

VERIFIED_GOOGLE_COOKIE = (
    "__Secure-BUCKET=CMQC; "
    "SID=g.a000DQmIT8_RO_bnf5DGAEoTTh_s44l8JtyWQCE_mqygUKUq9hFNGiDTG3VdWHqF0gbO5JdL4AACgYKAV8SARMSFQHGX2Mi5kbiJlq0rlinC1cBtDW0DBoVAUF8yKrmp1vqw0Ose1c6UZ6SY0OW0076; "
    "__Secure-1PSID=g.a000DQmIT8_RO_bnf5DGAEoTTh_s44l8JtyWQCE_mqygUKUq9hFN_6jb-jhMX6uOSYNPkfF6bQACgYKAaYSARMSFQHGX2MiDOjK9t-P3bsqaUD7WFoWRRoVAUF8yKpMJ14OyAeKnVSflfeEkQrc0076; "
    "__Secure-3PSID=g.a000DQmIT8_RO_bnf5DGAEoTTh_s44l8JtyWQCE_mqygUKUq9hFNPEwXsyVYyMMFFETSi3P-swACgYKAeASARMSFQHGX2MiWn_DFnRlBvQhK85YJfLcFBoVAUF8yKoB2_FGC-zZ_R64wrtJ7N3a0076; "
    "HSID=A93ryFBPIornk6vPH; SSID=A1A3zcuFaIdJLunxh; APISID=sQZWANssEkrsKSfc/AEd4J7TqNnVjvmoQc; SAPISID=GeK0YAD8bNnP9I-b/ATJGw1R483rcmLoxO; "
    "__Secure-1PAPISID=GeK0YAD8bNnP9I-b/ATJGw1R483rcmLoxO; __Secure-3PAPISID=GeK0YAD8bNnP9I-b/ATJGw1R483rcmLoxO; "
    "AEC=Aaa9EJr5MWJbwHMfB4-zaQZ4dHzb8OgKqZu5gH8tVlKxD2IOxqop_hQiGUU; SEARCH_SAMESITE=CgQIi6IB; "
    "__Secure-1PSIDTS=sidts-CjcBkldj_2bFfFquy3v8mLRbvUF_7J15hV9cOo-A979gEK23jlUEqei46khUghRBpPqIaBqXIVyyEAA; "
    "__Secure-1PSIDRTS=sidts-CjcBkldj_2bFfFquy3v8mLRbvUF_7J15hV9cOo-A979gEK23jlUEqei46khUghRBpPqIaBqXIVyyEAA; "
    "__Secure-3PSIDTS=sidts-CjcBkldj_2bFfFquy3v8mLRbvUF_7J15hV9cOo-A979gEK23jlUEqei46khUghRBpPqIaBqXIVyyEAA; "
    "__Secure-3PSIDRTS=sidts-CjcBkldj_2bFfFquy3v8mLRbvUF_7J15hV9cOo-A979gEK23jlUEqei46khUghRBpPqIaBqXIVyyEAA; "
    "DV=E8Y7g4L_e8Fh4NvUndzzyhltM6nkFZpmZJkM5iW6-AAAAFDlHC2AqIuOqwAAAPCSFA-qpoSSPgAAAKaqsXzyEc3TEAAAAB71NcqXBrlQBAAAAA; "
    "NID=CqYECAES2AMBOxGDSIowy7otIxPYRn9_bifCfAJQAuZANBAzTWP0qNsVb-wehYz6HXIeR907-99eD9OZ0eNRSB5DCBR1i11yRfzeZkUthJlRd2MhzS5qam_-4ddSAYCt0eRKSNWROGrECSULKYZNuGwY7V1PtEICqLZOF7ANfTXDiA8QclnXooPrAMut1tn8Lr7nH2MfOf3kThqti05lc0Hz5KOWC1_rzz-6DDHzVeX_XiH51KrKMVKDyQixDuy83xzJuyfMbmXMlfwh9LeeYOlE_9DfX1TbFw0MjNv1ckmQOMdXIchXm57_2XrfuR17gYPrWBGG_f6Axh_upiNYVp4OkXyYVLM6FP8wvDEynUI3E6AP3r849F_0C_PnztmgRpPZvTzY7UyY1Hw9Pf90PtD6ooDwUTe0Mx3iKlyAaFMufeq99kjKapXwoPgDP8iMGfGiw2OmGiN3jKmn80EHSV5BJmnDVcw4THs7pRYKNdz_OWhmsA7yqeOBzRgZVIgizt8ebpmaCSxE_t5PJh8jsVbBHzCwd5p8Yg04ln3EACeBwcsOUuiBwsaDRdfBwGyFIMC3qovR8YIVrCHfTExWm7kcm9mJrkc681efkI4AYw_DGL7M-HWnsBiCQJFUKqsqKAEyRQHSrAfPr8k-TVPinSSC0KveQ7vupKKOph-XaH4ty95UNaUx5LRJH4Usf1-4gF28WisWDzK8tK2QpS-IvK4ZEi-tCJhfCQ; "
    "SIDCC=AKEyXzVxqeGRadKG3s41KaW7uIw_pQe0wiouwPVWv1WbbNxuJituDPgjkuieMPwubxX02wXOOT26; "
    "__Secure-1PSIDCC=AKEyXzWG0BV5LqBQzCqTiQCLmwwlvvag-gjpQ3Gy9wyLa7gRb7zYY95fCxSHh-N6EVFlTQFtV8g; "
    "__Secure-3PSIDCC=AKEyXzWyAk9QYmEE9cKCNAyX4IFxAMV-3wV30dSByWMtqcWZWlJDRpCD84-a_23ycjVjmS258mI; "
    "__Secure-STRP=ABNhA6iBo35mRIwXV7-MyJ1XMvjeJI8aK4u8JjziwhhMsErzckqhL-78xdl5IhxyPQF1pRyZBRJ2UosPtUxXtOzvKb5JbHC8Hn_G; "
    "UULE=j+WzEsMTIsMTc5MjU4MzQwMzk4MzAwMCxudWxsLFsyMTIzNTIxODksNzI5MzkwODM4XSxudWxsLDk5MjAwLG51bGwsNl0="
)


def is_genuine_company_domain(domain: str) -> bool:
    """
    Validate that a domain belongs to a genuine company website.
    Filters out .local, dummy domains, aggregator directories, and invalid formats.
    """
    if not domain or not isinstance(domain, str):
        return False
    d = domain.strip().lower()
    d = d.replace("www.", "").split(":")[0].split("/")[0]

    if not d or "." not in d:
        return False

    for suffix in DISALLOWED_DOMAIN_SUFFIXES:
        if d.endswith(suffix):
            return False

    for blocked in DISALLOWED_AGGREGATOR_DOMAINS:
        if d == blocked or d.endswith("." + blocked):
            return False

    parts = d.split(".")
    if len(parts) < 2:
        return False

    tld = parts[-1]
    if not tld.isalpha() or len(tld) < 2:
        return False

    name_part = parts[-2]
    if not name_part or len(name_part) < 2:
        return False

    for p in parts:
        if not p or not re.match(r"^[a-z0-9-]+$", p) or p.startswith("-") or p.endswith("-"):
            return False

    return True


SERVICE_PATTERNS = re.compile(
    r"\b(on-site services|online appointments|online classes|in-store|curbside|delivery|pickup|pick-up)\b",
    re.I,
)
HOURS_PATTERNS = re.compile(
    r"\b(open|closed|closes|opens|24 hours)\b",
    re.I,
)
YEARS_PATTERN = re.compile(
    r"\b\d+\+?\s+years?\s+in\s+business\b",
    re.I,
)
PHONE_PATTERN = re.compile(
    r"(\+?\d[\d\s-]{8,}\d)",
)


def extract_address_and_phone(card: Any, company_name: str) -> tuple[str, str]:
    """
    Accurately extracts real street address and phone number from a Google Local card.
    Strictly filters out business hours (Open/Closed), service badges (On-site services/Online appointments),
    and customer review quotes.
    """
    address = ""
    phone = ""
    details_div = card.find("div", class_="rllt__details")
    if not details_div:
        return address, phone

    rows = details_div.find_all("div", recursive=False)
    for r_idx, row in enumerate(rows):
        row_text = row.get_text(separator=" ", strip=True)
        if not row_text:
            continue

        # Row 0 or row with role='heading' is the company name heading
        if r_idx == 0 or row.get("role") == "heading" or row_text.strip().lower() == company_name.lower():
            continue

        # Skip customer review snippet quotes
        if row_text.startswith('"') or row_text.startswith("\u201c"):
            continue

        # Skip rows that are purely rating and category (e.g. "4.8 (269) - Software company")
        if re.search(r"^\d\.\d\s*\(\d+\)", row_text):
            continue

        parts = [p.strip() for p in row_text.split("\u00b7")]

        # Skip if entire row is business hours
        if all(HOURS_PATTERNS.search(p) or "pm" in p.lower() or "am" in p.lower() for p in parts if p):
            continue

        # Skip if entire row is service tags
        if all(SERVICE_PATTERNS.search(p) for p in parts if p):
            continue

        addr_parts = []
        for p in parts:
            p_clean = p.strip()
            if not p_clean:
                continue

            # Check for phone number
            phone_m = PHONE_PATTERN.search(p_clean)
            if phone_m and len(re.sub(r"\D", "", p_clean)) >= 8:
                if not phone:
                    phone = phone_m.group(1).strip()
                continue

            # Filter out business hours, service tags, years in business
            if HOURS_PATTERNS.search(p_clean) and any(
                w in p_clean.lower()
                for w in ["closes", "opens", "24 hours", "open", "closed", "pm", "am"]
            ):
                continue
            if SERVICE_PATTERNS.search(p_clean):
                continue
            if YEARS_PATTERN.search(p_clean):
                continue

            # Legitimate address candidate (must have reasonable length and not be numeric only)
            if len(p_clean) >= 4 and not re.match(r"^\d+$", p_clean):
                addr_parts.append(p_clean)

        if addr_parts and not address:
            address = ", ".join(addr_parts)

    return address, phone


def build_google_maps_url(name: str, address: str = "", city: str = "") -> str:
    """
    Constructs a verified universal Google Maps search URL for the company.
    Opens directly to the company's place, pin, and directions.
    """
    parts = [name]
    if address and address != "N/A":
        parts.append(address)
    elif city:
        parts.append(city)
    query = ", ".join(parts)
    return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(query)}"


def format_local_query(keyword: str = "", city: str = "") -> str:
    """
    Formats the search query to ensure Google triggers the local Places pack (udm=local).
    Inserts 'in' preposition between keyword and city if not already present.
    """
    k = (keyword or "").strip()
    c = (city or "").strip()
    if not k and not c:
        return "IT Companies"
    if not c:
        return k
    if not k:
        return f"Companies in {c}"
    if re.search(r"\b(in|near|at|around)\b", k, re.I):
        return f"{k} {c}".strip()
    return f"{k} in {c}".strip()


def extract_card_website_and_goto(card: Any) -> tuple[str, str]:
    """
    Extract website URL or /goto redirect URL from a Google Local card.
    Handles both direct links (typical in HTTP HTML) and /goto redirects (typical in desktop JS).
    Returns (direct_website_url, goto_url).
    """
    direct_url = ""
    goto_url = ""

    # 1. Check for explicit /goto link
    goto_a = card.find("a", href=lambda h: h and "/goto?url=" in h)
    if goto_a:
        goto_url = goto_a["href"].strip()

    # 2. Iterate all <a> tags looking for company website link
    for a in card.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(separator=" ", strip=True).lower()
        aria = (a.get("aria-label") or "").lower()
        pcu = (a.get("data-pcu") or "").strip()

        # If it's a /goto link and we haven't captured one
        if "/goto?url=" in href and not goto_url:
            goto_url = href
            continue

        # If data-pcu is present and is external URL
        if pcu.startswith("http") and not any(x in pcu for x in ["google.com", "google.co", "gstatic.com"]):
            direct_url = pcu
            break

        # Check explicit "website" text or aria-label
        if ("website" in text or "website" in aria) and href.startswith("http"):
            if not any(x in href for x in ["google.com", "google.co", "gstatic.com", "schema.org"]):
                direct_url = href
                break

        # Fallback external link (not google, not directions/maps)
        if href.startswith("http") and not direct_url:
            if not any(x in href for x in ["google.com", "google.co", "gstatic.com", "schema.org", "waze.com", "/maps/"]):
                direct_url = href

    return direct_url, goto_url


class GoogleScraper:
    """
    High-performance Google Local Scraper engine with explicit DOM synchronization
    and parallel /goto redirect resolution.
    """

    def __init__(self, headless: bool = True, max_workers: int = 25, log_callback: Any = None):
        self.headless = headless
        self.max_workers = max_workers
        self.log_callback = log_callback
        self.is_running = False
        self.progress = 0
        self.status_message = "Idle"
        self.logs: list[str] = []
        self.results: list[dict[str, Any]] = []
        self.error: str | None = None

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        })

    def _log(self, msg: str, progress: int | None = None):
        """Internal logging helper with immediate stdout flush and optional callback"""
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
        self.logs.append(msg)
        self.status_message = msg
        if progress is not None:
            self.progress = progress
        if self.log_callback:
            try:
                self.log_callback(msg, progress)
            except Exception:
                pass

    def _resolve_single_website(self, goto_url: str) -> str:
        """Resolve Google /goto redirect URL to the destination website"""
        if not goto_url:
            return ""
        if not goto_url.startswith("http"):
            goto_url = "https://www.google.com" + goto_url

        if not is_safe_public_url(goto_url):
            return ""

        try:
            r = self.session.get(goto_url, allow_redirects=False, timeout=1.8)
            loc = r.headers.get("Location") or goto_url
            if loc and is_safe_public_url(loc):
                return loc
            return ""
        except Exception:
            return ""

    def _resolve_websites_parallel(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Resolve company website URLs concurrently across thread pool"""
        goto_indices = [
            (idx, item["_goto_url"])
            for idx, item in enumerate(items)
            if item.get("_goto_url") and not item.get("website_url")
        ]

        if goto_indices:
            # Lower worker count in containerized environments (Render) to avoid 0.1 vCPU starvation
            worker_limit = 8 if os.environ.get("RENDER") else self.max_workers
            with ThreadPoolExecutor(max_workers=min(worker_limit, len(goto_indices))) as executor:
                future_to_idx = {
                    executor.submit(self._resolve_single_website, url): idx
                    for idx, url in goto_indices
                }
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        resolved = future.result()
                        # Extract clean domain
                        parsed = urllib.parse.urlparse(resolved)
                        domain = parsed.netloc or parsed.path
                        domain = domain.lower().replace("www.", "").split(":")[0].split("/")[0]
                        if is_genuine_company_domain(domain) and is_safe_public_url(resolved):
                            items[idx]["website_url"] = resolved
                            items[idx]["domain"] = domain
                        else:
                            items[idx]["website_url"] = ""
                            items[idx]["domain"] = ""
                    except Exception:
                        items[idx]["website_url"] = ""
                        items[idx]["domain"] = ""

        for item in items:
            if item.get("website_url") and not item.get("domain"):
                item["domain"] = self._extract_domain_from_url(item["website_url"])
            if "website_url" not in item:
                item["website_url"] = ""
            item.pop("_goto_url", None)

        return items

    def _extract_domain_from_url(self, url: str) -> str:
        """Extract clean domain name without www or path"""
        if not url:
            return ""
        try:
            parsed = urllib.parse.urlparse(url if url.startswith("http") else "http://" + url)
            domain = parsed.netloc or parsed.path
            return domain.lower().replace("www.", "").split(":")[0].split("/")[0]
        except Exception:
            return ""

    def build_initial_url(
        self,
        keyword: str = "",
        city: str = "",
        direct_url: str = "",
        gl: str = "in",
        hl: str = "en"
    ) -> str:
        """Construct a standardized Google Local Search URL"""
        if direct_url and ("google.com/search" in direct_url or direct_url.startswith("http")):
            parsed = urllib.parse.urlparse(direct_url)
            params = urllib.parse.parse_qs(parsed.query)
            params["udm"] = ["local"]
            params.pop("start", None)
            if gl and "gl" not in params:
                params["gl"] = [gl]
            if hl and "hl" not in params:
                params["hl"] = [hl]
            new_query = urllib.parse.urlencode(params, doseq=True)
            return f"https://www.google.com/search?{new_query}"

        full_query = format_local_query(keyword, city)
        encoded = urllib.parse.quote_plus(full_query)
        return f"https://www.google.com/search?q={encoded}&udm=local&gl={gl}&hl={hl}"

    def _scrape_http(
        self,
        keyword: str = "",
        city: str = "",
        direct_url: str = "",
        max_pages: int = 2,
        gl: str = "in",
        hl: str = "en",
        cookie: str = ""
    ) -> list[dict[str, Any]]:
        """
        Fast-Path HTTP scraper using authenticated anti-abuse Google headers and cookies.
        Bypasses Cloudflare / Google /sorry/index captcha blocks directly without Chromium overhead.
        """
        cookie_to_use = (cookie or os.environ.get("GOOGLE_COOKIE") or "").strip() or VERIFIED_GOOGLE_COOKIE
        if not cookie_to_use:
            return []

        http_session = requests.Session()
        http_session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Cookie": cookie_to_use.replace("\n", " ").strip(),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8,"
                "application/signed-exchange;v=b3;q=0.7"
            ),
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Arch": '"x86"',
            "Sec-Ch-Ua-Bitness": '"64"',
            "Sec-Ch-Ua-Full-Version": '"124.0.6367.92"',
            "Sec-Ch-Ua-Full-Version-List": '"Chromium";v="124.0.6367.92", "Google Chrome";v="124.0.6367.92", "Not-A.Brand";v="99.0.0.0"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Model": '""',
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Ch-Ua-Platform-Version": '"15.0.0"',
            "Sec-Ch-Ua-Wow64": "?0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Priority": "u=0, i",
        })

        effective_max = 50 if max_pages <= 0 else max_pages
        all_results = []

        for page in range(1, effective_max + 1):
            start_offset = (page - 1) * 20
            page_label = f"Page {page}/{max_pages}" if max_pages > 0 else f"Page {page}"
            pct = int(20 + ((page - 1) * 70 / effective_max))
            self._log(f"[Fast-Path HTTP] Fetching listings from {page_label}...", pct)

            if direct_url and "google.com/search" in direct_url:
                parsed = urllib.parse.urlparse(direct_url)
                params = urllib.parse.parse_qs(parsed.query)
                params["udm"] = ["local"]
                params["start"] = [str(start_offset)]
                if gl and "gl" not in params:
                    params["gl"] = [gl]
                if hl and "hl" not in params:
                    params["hl"] = [hl]
                url = f"https://www.google.com/search?{urllib.parse.urlencode(params, doseq=True)}"
            else:
                full_query = format_local_query(keyword, city)
                encoded = urllib.parse.quote_plus(full_query)
                url = f"https://www.google.com/search?q={encoded}&udm=local&start={start_offset}&gl={gl}&hl={hl}"

            try:
                resp = http_session.get(url, timeout=8.0)
                if resp.status_code != 200 or "sorry/index" in resp.url:
                    self._log(f"[Fast-Path HTTP] Notice: Status {resp.status_code} or checkpoint on {page_label}.", pct)
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = (
                    soup.find_all("div", class_="VkpGBb")
                    or soup.find_all("div", class_="cXedhc")
                    or soup.find_all("div", class_="rllt__details")
                )

                if not cards:
                    self._log(f"[Fast-Path HTTP] No more listings on {page_label}.", pct)
                    break

                page_raw = []
                for card in cards:
                    name_el = (
                        card.find("span", class_="OSrXXb")
                        or card.find("div", role="heading")
                        or card.find("div", class_="dbg0pd")
                    )
                    name = name_el.get_text(strip=True) if name_el else None
                    if not name:
                        continue

                    direct_web, goto_url = extract_card_website_and_goto(card)
                    dom = self._extract_domain_from_url(direct_web) if direct_web else ""

                    rating_el = card.find("span", class_="yi40Hd")
                    rating_str = rating_el.get_text(strip=True) if rating_el else "0.0"
                    try:
                        rating = float(rating_str)
                    except ValueError:
                        rating = 0.0

                    reviews_el = card.find("span", class_="RDApEe")
                    reviews_raw = reviews_el.get_text(strip=True).strip("()") if reviews_el else "0"
                    try:
                        reviews_count = int(re.sub(r"[^\d]", "", reviews_raw) or 0)
                    except ValueError:
                        reviews_count = 0

                    address_part, phone = extract_address_and_phone(card, name)
                    loc_url = build_google_maps_url(name, address_part, city)

                    page_raw.append({
                        "name": name,
                        "domain": dom,
                        "website_url": direct_web,
                        "location_url": loc_url,
                        "_goto_url": goto_url,
                        "rating": rating,
                        "reviews_count": reviews_count,
                        "address": address_part,
                        "phone": phone
                    })

                page_results = self._resolve_websites_parallel(page_raw)
                genuine_page = []
                for item in page_results:
                    dom = item.get("domain") or self._extract_domain_from_url(item.get("website_url", ""))
                    if is_genuine_company_domain(dom):
                        item["domain"] = dom
                        genuine_page.append(item)

                all_results.extend(genuine_page)
                page_pct = int(20 + (page * 70 / effective_max))
                self._log(f"[Fast-Path HTTP] {page_label}: Extracted {len(genuine_page)} genuine companies (Total: {len(all_results)})", page_pct)
                time.sleep(0.8)
            except Exception as e:
                self._log(f"[Fast-Path HTTP Error] on {page_label}: {e}", pct)
                break

        return all_results

    def scrape(
        self,
        keyword: str = "",
        city: str = "",
        direct_url: str = "",
        max_pages: int = 2,
        gl: str = "in",
        hl: str = "en"
    ) -> list[dict[str, Any]]:
        """
        Executes the scraping process.
        Attempts authenticated Fast-Path HTTP first, automatically falling back to Chromium browser.
        """
        self.is_running = True
        self.error = None
        self.results = []
        self.progress = 5

        # 1. Attempt Fast-Path HTTP Scraping with Anti-Abuse Cookies
        try:
            http_res = self._scrape_http(
                keyword=keyword,
                city=city,
                direct_url=direct_url,
                max_pages=max_pages,
                gl=gl,
                hl=hl
            )
            if http_res and len(http_res) > 0:
                self._log(f"Fast-path HTTP scraping completed! Extracted {len(http_res)} genuine companies.", 100)
                self.results = http_res
                return self.results
            else:
                self._log("Fast-path HTTP yielded 0 listings. Falling back to Chromium browser engine...", 15)
        except Exception as http_err:
            self._log(f"Fast-path HTTP notice ({http_err}). Falling back to Chromium browser engine...", 15)

        # 2. Browser-based fallback via SeleniumBase
        return self._scrape_browser(
            keyword=keyword,
            city=city,
            direct_url=direct_url,
            max_pages=max_pages,
            gl=gl,
            hl=hl
        )

    def _scrape_browser(
        self,
        keyword: str = "",
        city: str = "",
        direct_url: str = "",
        max_pages: int = 2,
        gl: str = "in",
        hl: str = "en"
    ) -> list[dict[str, Any]]:
        self._log(f"Initializing Chromium engine for: {keyword} {city} (Pages: {max_pages}, Region: {gl})...", 10)

        target_url = self.build_initial_url(keyword, city, direct_url, gl=gl, hl=hl)
        driver = None
        tmp_profile_dir = None

        try:
            # Create a unique, isolated user profile directory to avoid Windows file locks [WinError 32]
            for attempt in range(2):
                try:
                    chrome_bin_path = None
                    for candidate in (
                        "/opt/render/project/.render/chrome/opt/google/chrome/google-chrome",
                        "/opt/render/project/.render/chrome/opt/google/chrome/chrome",
                        "/usr/bin/google-chrome-stable",
                        "/usr/bin/google-chrome",
                        "/usr/bin/chromium",
                        "/usr/bin/chromium-browser"
                    ):
                        if os.path.exists(candidate):
                            chrome_bin_path = candidate
                            chrome_dir = os.path.dirname(candidate)
                            if chrome_dir not in os.environ.get("PATH", ""):
                                os.environ["PATH"] = f"{chrome_dir}:{os.environ.get('PATH', '')}"
                            break

                    has_display = bool(os.environ.get("DISPLAY"))
                    # When running under Xvfb (xvfb-run on GitHub Actions or Linux display),
                    # run with headless=False in the virtual desktop with UC mode enabled.
                    # This completely avoids navigator.webdriver=true and Google bot challenges.
                    driver_kwargs = {
                        "uc": True,
                        "headless": False if has_display else self.headless,
                        "user_data_dir": tmp_profile_dir,
                        "disable_gpu": True,
                        "no_sandbox": True,
                        "chromium_arg": "--disable-dev-shm-usage,--disable-software-rasterizer,--no-first-run,--start-maximized,--disable-blink-features=AutomationControlled",
                    }
                    if chrome_bin_path:
                        driver_kwargs["binary_location"] = chrome_bin_path

                    driver = Driver(**driver_kwargs)
                    break
                except Exception as init_err:
                    if tmp_profile_dir and os.path.exists(tmp_profile_dir):
                        shutil.rmtree(tmp_profile_dir, ignore_errors=True)
                    if attempt == 1:
                        raise init_err
                    time.sleep(1.2)

            self._log(f"Navigating to Google Local: {target_url}", 20)
            if hasattr(driver, "uc_open_with_reconnect"):
                try:
                    driver.uc_open_with_reconnect(target_url, reconnect_time=4.0)
                except Exception as ne:
                    self._log(f"UC reconnect notice: {ne}; using standard navigation", 21)
                    driver.get(target_url)
            else:
                driver.get(target_url)

            # Check and auto-accept Google Consent dialog (standard on cloud / datacenter IPs)
            time.sleep(1.5)
            try:
                curr_url = (driver.current_url or "").lower()
                if "consent.google.com" in curr_url or "consent" in curr_url:
                    self._log("Detected Google Consent prompt; auto-accepting terms...", 22)
                    for accept_sel in ["button#L2AGLb", "button:contains('Accept all')", "button:contains('I agree')", "form[action*='consent'] button"]:
                        try:
                            if driver.is_element_visible(accept_sel):
                                driver.click(accept_sel, timeout=2)
                                time.sleep(1.5)
                                break
                        except Exception:
                            pass
            except Exception:
                pass

            # Auto-solve Google verification / sorry challenge if triggered on datacenter IP
            try:
                curr_url = (driver.current_url or "").lower()
                page_src = (driver.page_source or "").lower()
                if "sorry" in curr_url or "sorry/index" in curr_url or "recaptcha" in page_src:
                    self._log("Detected Google verification challenge; executing automated UC bypass...", 22)
                    for solver_method in ["uc_gui_handle_rc", "uc_gui_click_rc", "uc_gui_click_captcha", "uc_gui_handle_captcha"]:
                        if hasattr(driver, solver_method):
                            try:
                                self._log(f"Attempting {solver_method}()...", 23)
                                getattr(driver, solver_method)()
                                time.sleep(3.5)
                                curr_url = (driver.current_url or "").lower()
                                if "sorry" not in curr_url:
                                    self._log("Automated UC bypass successful!", 25)
                                    break
                            except Exception as ce:
                                self._log(f"{solver_method} notice: {ce}", 23)
            except Exception:
                pass

            is_all_pages = (max_pages <= 0)
            effective_max = 50 if is_all_pages else max_pages
            page = 1

            while page <= effective_max:
                page_label = f"Page {page} (All Pages Mode)" if is_all_pages else f"Page {page}/{max_pages}"
                progress_pct = int(20 + ((page - 1) * 70 / effective_max))
                self._log(f"Parsing results from {page_label}...", progress_pct)

                # Polling for cards (up to 12 seconds with 0.4s interval)
                cards = []
                soup = None
                for poll_i in range(30):
                    page_source = driver.page_source
                    soup = BeautifulSoup(page_source, "html.parser")

                    # Check for inline consent button
                    if poll_i < 3 and "consent" in page_source.lower() and "l2aglb" in page_source.lower():
                        try:
                            driver.click("button#L2AGLb", timeout=1)
                        except Exception:
                            pass

                    # Multi-selector matching for Google Local business listing cards
                    cards = (
                        soup.find_all("div", class_="VkpGBb")
                        or soup.find_all("div", {"jscontroller": "AtSb"})
                        or soup.find_all("div", class_="cXedhc")
                        or soup.find_all("div", class_="rllt__details")
                        or soup.find_all("div", class_="C8fQm")
                    )
                    if cards:
                        break
                    time.sleep(0.4)

                # Fallback on Page 1: If udm=local yields 0 cards, search via Google Places Web pack
                if not cards and page == 1:
                    fallback_query = format_local_query(keyword, city)
                    fallback_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(fallback_query)}&gl={gl}&hl={hl}"
                    self._log(f"No cards on udm=local; falling back to Google Places Search: {fallback_url}", 26)
                    if hasattr(driver, "uc_open_with_reconnect"):
                        try:
                            driver.uc_open_with_reconnect(fallback_url, reconnect_time=3.5)
                        except Exception:
                            driver.get(fallback_url)
                    else:
                        driver.get(fallback_url)
                    time.sleep(2.5)

                    for poll_i in range(15):
                        page_source = driver.page_source
                        soup = BeautifulSoup(page_source, "html.parser")
                        cards = (
                            soup.find_all("div", class_="VkpGBb")
                            or soup.find_all("div", {"jscontroller": "AtSb"})
                            or soup.find_all("div", class_="cXedhc")
                            or soup.find_all("div", class_="rllt__details")
                            or soup.find_all("div", class_="C8fQm")
                        )
                        if cards:
                            self._log(f"Found {len(cards)} listings via Google Places fallback!", 28)
                            break
                        time.sleep(0.4)

                if not cards:
                    page_title = driver.title or "No Title"
                    curr_url = driver.current_url or "No URL"
                    src_preview = (driver.page_source or "")[:250].replace("\n", " ")
                    self._log(f"No listings found on {page_label}. URL: {curr_url} | Title: {page_title} | HTML snippet: {src_preview}", 90)
                    break

                page_raw_items = []
                for card in cards:
                    name_el = (
                        card.find("span", class_="OSrXXb")
                        or card.find("div", role="heading")
                        or card.find("div", class_="dbg0pd")
                        or card.find("span", class_="LrzXr")
                    )
                    name = name_el.get_text(strip=True) if name_el else None
                    if not name:
                        continue

                    direct_web, goto_url = extract_card_website_and_goto(card)
                    dom = self._extract_domain_from_url(direct_web) if direct_web else ""

                    # Rating and reviews
                    rating_el = card.find("span", class_="yi40Hd")
                    rating_str = rating_el.get_text(strip=True) if rating_el else "0.0"
                    try:
                        rating = float(rating_str)
                    except ValueError:
                        rating = 0.0

                    reviews_el = card.find("span", class_="RDApEe")
                    reviews_raw = reviews_el.get_text(strip=True).strip("()") if reviews_el else "0"
                    try:
                        reviews_count = int(re.sub(r"[^\d]", "", reviews_raw) or 0)
                    except ValueError:
                        reviews_count = 0

                    # Extract real physical address and phone number (filtering out 'Open', 'On-site services', etc.)
                    address_part, phone = extract_address_and_phone(card, name)
                    loc_url = build_google_maps_url(name, address_part, city)

                    page_raw_items.append({
                        "name": name,
                        "domain": dom,
                        "website_url": direct_web,
                        "location_url": loc_url,
                        "_goto_url": goto_url,
                        "rating": rating,
                        "reviews_count": reviews_count,
                        "address": address_part,
                        "phone": phone
                    })

                # Resolve website URLs in parallel
                page_results = self._resolve_websites_parallel(page_raw_items)

                # Filter strictly for genuine company domains only
                genuine_results = []
                for item in page_results:
                    dom = item.get("domain") or self._extract_domain_from_url(item.get("website_url", ""))
                    if is_genuine_company_domain(dom):
                        item["domain"] = dom
                        genuine_results.append(item)

                self.results.extend(genuine_results)
                page_progress = int(20 + (page * 70 / effective_max))
                self._log(
                    f"{page_label}: Extracted {len(genuine_results)} genuine companies (Total: {len(self.results)})",
                    page_progress,
                )

                # Next Page navigation if more pages requested or in All Pages mode
                if page < effective_max:
                    start_offset = page * 20
                    if direct_url and "google.com/search" in direct_url:
                        parsed = urllib.parse.urlparse(direct_url)
                        params = urllib.parse.parse_qs(parsed.query)
                        params["udm"] = ["local"]
                        params["start"] = [str(start_offset)]
                        if gl and "gl" not in params:
                            params["gl"] = [gl]
                        if hl and "hl" not in params:
                            params["hl"] = [hl]
                        next_url = f"https://www.google.com/search?{urllib.parse.urlencode(params, doseq=True)}"
                    else:
                        full_query = format_local_query(keyword, city)
                        encoded = urllib.parse.quote_plus(full_query)
                        next_url = f"https://www.google.com/search?q={encoded}&udm=local&start={start_offset}&gl={gl}&hl={hl}"

                    next_label = f"Page {page + 1} (All Pages Mode)" if is_all_pages else f"Page {page + 1}/{max_pages}"
                    self._log(f"Navigating to {next_label}...", page_progress)
                    if hasattr(driver, "uc_open_with_reconnect"):
                        try:
                            driver.uc_open_with_reconnect(next_url, reconnect_time=3.0)
                        except Exception:
                            driver.get(next_url)
                    else:
                        driver.get(next_url)
                    time.sleep(1.5)
                    page += 1
                else:
                    self._log(f"Reached requested limit of {max_pages} pages.", page_progress)
                    break

            self._log(f"Scraping completed! Successfully extracted {len(self.results)} companies.", 100)
            return self.results

        except Exception as e:
            self.error = str(e)
            self._log(f"Error during scrape: {e!s}", 100)
            return self.results

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            if tmp_profile_dir and os.path.exists(tmp_profile_dir):
                try:
                    time.sleep(0.5)
                    shutil.rmtree(tmp_profile_dir, ignore_errors=True)
                except Exception:
                    pass
