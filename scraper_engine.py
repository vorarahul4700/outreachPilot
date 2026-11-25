"""
OutreachPilot - Google Local Scraper Engine
Module: scraper_engine.py
Architecture: SeleniumBase (Undetected Chrome) + ThreadPoolExecutor for Parallel Website Resolution
"""

import os
import random
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


class GoogleBlockedException(Exception):
    """Raised when Google anti-bot verification challenge (sorry/index) is active and cannot be bypassed."""
    pass


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
    "SID=g.a000EgmITwCY6Pi1chmiB9vSXZFqWK91HeCkxqhLm-zCKIqKLjsuoYceNoc0vo_PD3ndlhMSPwACgYKAf0SARMSFQHGX2MifSDXGHMSosoi2fm-4cFhSBoVAUF8yKrSes7z3j-fe32gkkonTL9L0076; "
    "__Secure-1PSID=g.a000EgmITwCY6Pi1chmiB9vSXZFqWK91HeCkxqhLm-zCKIqKLjsuKMk9XBAbmsbOOnHy8BQjUAACgYKAWoSARMSFQHGX2MiCB1SmdLI48mKy58ep53qiBoVAUF8yKpZ4Mjh_Mj8B3BpG1fMN9hP0076; "
    "__Secure-3PSID=g.a000EgmITwCY6Pi1chmiB9vSXZFqWK91HeCkxqhLm-zCKIqKLjsu2NnyxJoO_iOnA6lWO_TNwQACgYKAc4SARMSFQHGX2MijEewydtKDAq2HvDJ49rvnRoVAUF8yKoYta9BbBfvSnaGnY6c0XPB0076; "
    "HSID=AfYzugTeIVV3J8Q-f; SSID=ApzVAvQY0D-03DvWY; APISID=hSGeZnm1RB9yZtFb/ASatu7JwK9UamJfzr; SAPISID=pkrS9oeUhUv-FISY/AaYg-7eDDsRqf2wMV; "
    "__Secure-1PAPISID=pkrS9oeUhUv-FISY/AaYg-7eDDsRqf2wMV; __Secure-3PAPISID=pkrS9oeUhUv-FISY/AaYg-7eDDsRqf2wMV; "
    "AEC=Aaa9EJpTjs-RU35V-2PpfGNl17GvHyo8Qng9Bhc4CjV_fboL2TeMPPfiVw; UULE=j+WzEsMTIsMTc5NDgyNDAzNjMzMzAwMCxudWxsLFsyMTIzNTI2MDYsNzI5MzkyNjg3XSxudWxsLDExMDk4MCxudWxsLDZd; "
    "SEARCH_SAMESITE=CgQIpaIB; "
    "NID=CrAECAES4gMBM9Agl0p6GSZXfvi1xLbvhfbyFfK_XAzc7J4ihGC15ZCU-dxoSugU_8kxg6doAHCKaGYiUwhVOUWG4jE8pV7drAOSeDf2QOhdksiX1mCHkbxOJMNlIaR4bIrCL_av3JuleKpRWm-lcyBOjkzd--DM9c_y4Lv75CiSE5RgeFsRBmZw-ZGNGA_73SwqLqaPiz2SNG3czL_UnIkEOF0jtuErYJ3QePcr2D-aBqluFuJvrOegpCM0bOx8PQwJGWfX_bCTc3Aiaw6TVRDDbZVQuPUuvwah7xWYzJyaOVtChs0P9zb9hC4i4Ao8zyTc6rjyw13aIkh56ruzqE1iseJrXiKpNQlWtmCR0GsIkw-5jDw5xeqL_qXlSX4bhjPbcEvqr5YpAReEnnCLnEvsYL9ouVcjfeGJ0hM7WkdDBlPHvSvNtaTfcWlkc34zmTPDmnL_ElOZlr5iN5bwEPFmfmhm40HjZAasHZrvhxiymrkmhKhv1Xl4Nt0xeO5OBhf1iNNuuw6irmuP_7EFqXw9G6XqQ0mhFLo2ddruylHUvfI5Bc9h29A8QF2usfioUOLf-lMQvDTkn6Zb9Ij3YnCtAoycFctPx4Fn6O4SbjZVyEhxXFG64jHnDRXPCyGNs83DgfMdZbpueSgBMkUBcEpCz3dHZmIN8v9un-OMPNfGmSUmNMS4rzRdH8nlTzXPm9iFzw1jwfNinY49aj_txA3sIGSY7pa55dBY4Ru7FFNmhwA; "
    "__Secure-1PSIDTS=sidts-CjYBnJZzal-wMh1oVhH4tlHvGEaVACLVl11EyUgnqWBfVMP2H3-7jle4r91-wl4UMsTlw7ExB4sQAA; "
    "__Secure-1PSIDRTS=sidts-CjYBnJZzal-wMh1oVhH4tlHvGEaVACLVl11EyUgnqWBfVMP2H3-7jle4r91-wl4UMsTlw7ExB4sQAA; "
    "__Secure-3PSIDTS=sidts-CjYBnJZzal-wMh1oVhH4tlHvGEaVACLVl11EyUgnqWBfVMP2H3-7jle4r91-wl4UMsTlw7ExB4sQAA; "
    "__Secure-3PSIDRTS=sidts-CjYBnJZzal-wMh1oVhH4tlHvGEaVACLVl11EyUgnqWBfVMP2H3-7jle4r91-wl4UMsTlw7ExB4sQAA; "
    "DV=E8Y7g4L_e8FhYKoayycf0TwtuC0_HlqVc7QAoi46rgAAAKAZWSaDeYkuPgAAAPg2dSf3vHJGMwAAAHjU1yhfGuRCDwAAAC9J8aBqSijpBAAAAA; "
    "__Secure-STRP=ABNhA6gd1UyR7T1t4KBw2zOG1xVx4THKAGFFQfDh9u_vpkpXW2-EV82FQ_Dcpm8PI4dqpKoLZJxIW6HgbKCS9cNMnjAjmVm2m7hq; "
    "SIDCC=APD_SKFKnbvJYvPB6X8AeXc_-jMhZ8oSSEeG1MVVBCgSZ-f5_pAaE8wc1CfaqYlDZNaP2n0M6M48; "
    "__Secure-1PSIDCC=APD_SKEOiR0q5Y-s2ONbqAo4kzl7nG4ufWqQdIVTwUnfsY46vnZuau4EKBIOFAZSqCoQOFzgRFI; "
    "__Secure-3PSIDCC=APD_SKEKav9S7f1Mf_ET9zDvraPTp8ztFlz1fLWBrLyVIvn7rZAxpP8xmej7QJG_0Uh1iLCGLdo"
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


def extract_embedded_places_data(page_source: str) -> dict[str, dict[str, str]]:
    """
    Directly extracts verified company websites, phone numbers, addresses,
    and categories from Google's embedded client-side JSON data.
    Provides instant, 100% accurate website resolution without /goto redirect overhead or rate limits.
    """
    matches = list(re.finditer(r'\[\s*\["([^"]+)",\d+,\d+,\d+,\[[^\]]*\],"Place name"\]', page_source))
    places_map = {}
    for m in matches:
        start_pos = m.start()
        name = m.group(1).replace(r"\u0026", "&").replace(r"\\'", "'").strip()
        chunk = page_source[start_pos:start_pos + 3500]

        web_m = re.search(r'\["(https?://[^"]+)",\d+,\d+,\d+,\[[^\]]*\],"Place website"\]', chunk)
        web = web_m.group(1).replace(r"\u003d", "=").replace(r"\u0026", "&") if web_m else ""

        phone_m = re.search(r'\["([^"]+)",\d+,\d+,\d+,\[[^\]]*\],"Place phone number"\]', chunk)
        phone = phone_m.group(1).strip() if phone_m and "add phone" not in phone_m.group(1).lower() else ""

        addr_m = re.search(r'\["([^"]+)",\d+,\d+,\d+,\[[^\]]*\],"Place location"\]', chunk)
        addr = addr_m.group(1).replace(r"\u0026", "&").strip() if addr_m else ""

        cat_m = re.search(r'\["([^"]+)",\d+,\d+,\d+,\[[^\]]*\],"Place category"\]', chunk)
        cat = cat_m.group(1).replace(r"\u0026", "&").strip() if cat_m else ""

        norm_key = re.sub(r"[^\w\s]", "", name.lower()).strip()
        places_map[norm_key] = {
            "name": name,
            "website_url": web,
            "phone": phone,
            "address": addr,
            "category": cat
        }
    return places_map


def extract_card_website_and_goto(card: Any) -> tuple[str, str]:
    """
    Extract website URL or /goto redirect URL from a Google Local card.
    Handles both direct links (typical in HTTP HTML) and /goto redirects (typical in desktop JS).
    Prioritizes explicit 'Website' buttons over 'Schedule' / appointment links.
    Returns (direct_website_url, goto_url).
    """
    direct_url = ""
    goto_url = ""
    fallback_goto = ""

    for a in card.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(separator=" ", strip=True).lower()
        aria = (a.get("aria-label") or "").lower()
        pcu = (a.get("data-pcu") or "").strip()

        # If data-pcu is present and is external URL
        if pcu.startswith("http") and not any(x in pcu for x in ["google.com", "google.co", "gstatic.com"]):
            direct_url = pcu
            break

        is_website_btn = ("website" in text or "website" in aria)

        # Prioritize explicit Website button
        if is_website_btn:
            if "/goto?url=" in href:
                goto_url = href
                break
            elif href.startswith("http") and not any(x in href for x in ["google.com", "google.co", "gstatic.com", "schema.org"]):
                direct_url = href
                break

        # Fallback /goto link (only if not a maps/directions link)
        if "/goto?url=" in href and not fallback_goto:
            if not any(x in href for x in ["/maps/", "dir/", "google.com/maps"]):
                fallback_goto = href

        # Fallback external link (not google, not directions/maps)
        if href.startswith("http") and not direct_url:
            if not any(x in href for x in ["google.com", "google.co", "gstatic.com", "schema.org", "waze.com", "/maps/"]):
                direct_url = href

    if not goto_url and fallback_goto:
        goto_url = fallback_goto

    return direct_url, goto_url


def parse_maps_feed(page_source: str) -> list[dict[str, Any]]:
    """Parse every place card in a Google Maps search results feed (div[role=feed] > div[role=article])."""
    soup = BeautifulSoup(page_source, "html.parser")
    items = []
    for card in soup.select('div[role="article"]'):
        link = card.select_one("a.hfpxzc")
        name = ((link.get("aria-label") if link else "") or "").strip()
        if not name:
            heading = card.select_one(".qBF1Pd")
            name = heading.get_text(strip=True) if heading else ""
        if not name:
            continue

        website = ""
        web_a = card.select_one('a[data-value="Website"]') or card.select_one('a[aria-label^="Visit"]')
        if web_a and web_a.get("href"):
            website = web_a["href"].strip()
            # Maps sometimes wraps outbound links as /url?q=<target>
            if "/url?" in website:
                website = (urllib.parse.parse_qs(urllib.parse.urlparse(website).query).get("q") or [""])[0]

        rating_el = card.select_one("span.MW4etd")
        try:
            rating = float(rating_el.get_text(strip=True)) if rating_el else 0.0
        except ValueError:
            rating = 0.0
        reviews_el = card.select_one("span.UY7F9")
        reviews_count = int(re.sub(r"[^\d]", "", reviews_el.get_text()) or 0) if reviews_el else 0

        phone_el = card.select_one("span.UsdlK")
        phone = phone_el.get_text(strip=True) if phone_el else ""

        # First detail row reads "<category> · <address>"; icon spans add empty parts
        address = ""
        rows = card.select("div.W4Efsd div.W4Efsd")
        if rows:
            parts = [p.strip() for p in rows[0].get_text(" ", strip=True).split("·") if p.strip()]
            if len(parts) > 1:
                address = parts[-1]

        items.append({
            "name": name,
            "website_url": website,
            "location_url": (link.get("href") or "").strip() if link else "",
            "_goto_url": "",
            "rating": rating,
            "reviews_count": reviews_count,
            "address": address,
            "phone": phone,
        })
    return items


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
            r = self.session.get(goto_url, allow_redirects=False, timeout=5.0)
            loc = r.headers.get("Location")
            if not loc and r.text:
                m = re.search(r'<a\s+[^>]*href=["\']([^"\']+)["\']', r.text, re.IGNORECASE)
                if m:
                    loc = m.group(1).replace("&amp;", "&")
            if loc and not any(x in loc for x in ["google.com", "google.co", "gstatic.com"]):
                if is_safe_public_url(loc):
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
        max_pages: int = 0,
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
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Cookie": cookie_to_use.replace("\n", " ").strip(),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8,"
                "application/signed-exchange;v=b3;q=0.7"
            ),
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-Ch-Ua-Arch": '"x86"',
            "Sec-Ch-Ua-Bitness": '"64"',
            "Sec-Ch-Ua-Full-Version": '"131.0.6778.205"',
            "Sec-Ch-Ua-Full-Version-List": '"Google Chrome";v="131.0.6778.205", "Chromium";v="131.0.6778.205", "Not_A Brand";v="24.0.0.0"',
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

        effective_max = 100 if max_pages <= 0 else max_pages
        all_results = []

        for page in range(1, effective_max + 1):
            start_offset = (page - 1) * 20
            page_label = f"Page {page} (All Pages Mode)" if max_pages <= 0 else f"Page {page}/{max_pages}"
            pct = min(90, int(20 + ((page - 1) * 65 / min(effective_max, 25))))
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

            resp = None
            try:
                for http_attempt in range(3):
                    try:
                        resp = http_session.get(url, timeout=10.0)
                        if resp.status_code == 200 and "sorry/index" not in (resp.url or ""):
                            break
                        if resp.status_code in (429, 503) or "sorry/index" in (resp.url or ""):
                            if http_attempt < 2:
                                backoff = (http_attempt + 1) * 2.5 + random.uniform(0.5, 1.5)
                                self._log(f"[Fast-Path HTTP] Rate-limit (status {resp.status_code}) on {page_label}; backing off {backoff:.1f}s (retry {http_attempt+1}/2)...", pct)
                                time.sleep(backoff)
                                continue
                    except Exception as req_err:
                        if http_attempt < 2:
                            time.sleep(1.5)
                            continue
                        self._log(f"[Fast-Path HTTP Error] on {page_label}: {req_err}", pct)
                        break

                if not resp or resp.status_code != 200 or "sorry/index" in (resp.url or ""):
                    code_str = str(resp.status_code) if resp else "connection_failed"
                    self._log(f"[Fast-Path HTTP] Notice: Status {code_str} or checkpoint on {page_label}.", pct)
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = (
                    soup.find_all("div", class_="VkpGBb")
                    or soup.find_all("div", class_="w7Dbne")
                    or soup.find_all("div", class_="uMdZh")
                    or soup.find_all("div", {"jscontroller": "AtSb"})
                    or soup.find_all("div", class_="cXedhc")
                    or soup.find_all("div", class_="rllt__details")
                    or soup.find_all("div", class_="C8fQm")
                )

                if not cards:
                    self._log(f"[Fast-Path HTTP] Pagination complete: all available listings extracted up to {page_label}.", pct)
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
        max_pages: int = 0,
        gl: str = "in",
        hl: str = "en",
        use_maps: bool = False
    ) -> list[dict[str, Any]]:
        """
        Executes the scraping process.
        Attempts authenticated Fast-Path HTTP first, automatically falling back to Chromium browser.
        With use_maps, also scrolls the full Google Maps feed and merges new domains in.
        """
        self.is_running = True
        self.error = None
        self.results = []
        self.progress = 5

        local_res: list[dict[str, Any]] = []
        blocked = None
        if not (direct_url and "google.com/maps" in direct_url):
            try:
                local_res = self._scrape_local(keyword, city, direct_url, max_pages, gl, hl)
            except GoogleBlockedException as gbe:
                if not use_maps:
                    raise
                blocked = gbe
        if not use_maps:
            return local_res

        maps_res: list[dict[str, Any]] = []
        try:
            maps_res = self._scrape_maps(keyword, city, direct_url, hl)
        except GoogleBlockedException as gbe:
            blocked = blocked or gbe
        except Exception as me:
            self._log(f"Google Maps feed notice: {me}", 95)

        merged = list(local_res)
        seen = {(r.get("domain") or "").lower() for r in merged}
        for item in maps_res:
            if item["domain"] not in seen:
                seen.add(item["domain"])
                merged.append(item)

        if not merged and blocked:
            raise blocked
        if blocked:
            # One source got through, so this run is not a rate-limit failure
            self.error = None
        self._log(
            f"Scraping completed! {len(local_res)} from Google Local + {len(merged) - len(local_res)} new from Google Maps = {len(merged)} companies.",
            100,
        )
        self.results = merged
        return self.results

    def _scrape_local(self, keyword, city, direct_url, max_pages, gl, hl) -> list[dict[str, Any]]:
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

    def _scroll_maps_feed(self, driver) -> tuple[list[dict[str, Any]], bool]:
        """Scroll the open Maps results feed until the end-of-list marker, then parse it."""
        scroll_js = """
            const feed = document.querySelector('div[role="feed"]');
            if (!feed) return [-1, false];
            // Small upward nudge first: Maps sometimes only loads more after a fresh scroll event
            if (arguments[0]) feed.scrollTop = Math.max(0, feed.scrollTop - 400);
            feed.scrollTop = feed.scrollHeight;
            const end = !!document.querySelector('span.HlvSq')
                || feed.innerText.includes("reached the end of the list");
            return [feed.querySelectorAll('div[role="article"]').length, end];
        """
        last, stale, reached_end = -1, 0, False
        # Hard cap ~12 min; one Maps search tops out at about 120 places well before that
        for _ in range(500):
            count, reached_end = driver.execute_script(scroll_js, stale > 0)
            if reached_end:
                break
            stale = stale + 1 if count == last else 0
            # No feed at all (single place page) or no new cards for ~36s: stop
            if stale >= 25 or (count == -1 and stale >= 6):
                break
            last = count
            time.sleep(1.4)
        return parse_maps_feed(driver.page_source), reached_end

    def _open_maps(self, driver, url: str) -> None:
        driver.get(url)
        time.sleep(3.0)
        curr = (driver.current_url or "").lower()
        if "consent.google.com" in curr:
            for sel in ['button[aria-label^="Accept all"]', "form[action*='consent'] button"]:
                try:
                    if driver.is_element_visible(sel):
                        driver.click(sel, timeout=2)
                        time.sleep(2.0)
                        break
                except Exception:
                    pass
            curr = (driver.current_url or "").lower()
        if "/sorry/" in curr:
            raise GoogleBlockedException(f"Google Maps verification challenge active ({curr}).")

    def _scrape_maps(self, keyword: str = "", city: str = "", direct_url: str = "", hl: str = "en") -> list[dict[str, Any]]:
        """
        Open a Google Maps search and scroll the feed to "You've reached the end of the list.".
        Maps stops at about 120 places per search, so when a search hits that cap the same
        query is re-run on a 3x3 grid around the map centre to reach the rest.
        """
        if direct_url and "google.com/maps" in direct_url:
            url = direct_url
            m = re.search(r"(https://www\.google\.[^/]+/maps/search/[^/?]+)", direct_url)
            base = m.group(1) if m else ""
        else:
            query = format_local_query(keyword, city)
            if not query:
                return []
            base = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(query)}"
            url = f"{base}?hl={hl}"

        self._log(f"Opening Google Maps feed: {url}", 92)
        driver = self._open_driver()
        items: list[dict[str, Any]] = []
        try:
            self._open_maps(driver, url)
            found, reached_end = self._scroll_maps_feed(driver)
            items.extend(found)
            self._log(f"Google Maps feed: {len(found)} places ({'end of list' if reached_end else 'feed stopped growing'}).", 93)

            centre = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", driver.current_url or "")
            if base and centre and len(found) >= 100:
                lat, lng = float(centre.group(1)), float(centre.group(2))
                step = 0.06  # ~6.5 km; 3x3 cells at zoom 13 cover a large Indian city
                for dy in (-step, 0, step):
                    for dx in (-step, 0, step):
                        if dy == 0 and dx == 0:
                            continue
                        cell = f"{base}/@{lat + dy:.5f},{lng + dx:.5f},13z?hl={hl}"
                        try:
                            self._open_maps(driver, cell)
                            cell_items, _ = self._scroll_maps_feed(driver)
                        except GoogleBlockedException:
                            raise
                        except Exception as ce:
                            self._log(f"Maps grid cell notice: {ce}", 94)
                            continue
                        items.extend(cell_items)
                        self._log(f"Maps grid cell {lat + dy:.3f},{lng + dx:.3f}: {len(cell_items)} places (running total {len(items)}).", 94)
        finally:
            try:
                driver.quit()
            except Exception:
                pass

        genuine, seen = [], set()
        for item in items:
            dom = self._extract_domain_from_url(item["website_url"])
            if dom and dom not in seen and is_genuine_company_domain(dom):
                seen.add(dom)
                item["domain"] = dom
                genuine.append(item)
        self._log(f"Google Maps total: {len(genuine)} unique companies with websites.", 95)
        return genuine

    def _open_driver(self):
        """Start the UC Chromium driver and pre-load Google session cookies."""
        driver = None
        tmp_profile_dir = None
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
                    "chromium_arg": "--disable-dev-shm-usage,--disable-software-rasterizer,--no-first-run,--start-maximized,--window-size=1920,1080,--disable-blink-features=AutomationControlled",
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

        # Pre-inject anti-abuse Google session cookies into Chromium browser session
        try:
            active_cookie = (os.environ.get("GOOGLE_COOKIE") or "").strip() or VERIFIED_GOOGLE_COOKIE
            if active_cookie:
                driver.get("https://www.google.com/robots.txt")
                time.sleep(0.4)
                for c_part in active_cookie.split(";"):
                    if "=" in c_part:
                        c_k, c_v = c_part.split("=", 1)
                        c_k, c_v = c_k.strip(), c_v.strip()
                        if c_k and c_v:
                            try:
                                driver.add_cookie({
                                    "name": c_k,
                                    "value": c_v,
                                    "domain": ".google.com",
                                    "path": "/",
                                })
                            except Exception:
                                pass
        except Exception:
            pass

        return driver

    def _scrape_browser(
        self,
        keyword: str = "",
        city: str = "",
        direct_url: str = "",
        max_pages: int = 0,
        gl: str = "in",
        hl: str = "en"
    ) -> list[dict[str, Any]]:
        cov_label = "All Available Pages" if max_pages <= 0 else f"{max_pages} Pages"
        self._log(f"Initializing Chromium engine for: {keyword} {city} (Coverage: {cov_label}, Region: {gl})...", 10)

        target_url = self.build_initial_url(keyword, city, direct_url, gl=gl, hl=hl)
        driver = None
        tmp_profile_dir = None

        try:
            driver = self._open_driver()
            use_uc_reconnect = hasattr(driver, "uc_open_with_reconnect") and not bool(os.environ.get("GITHUB_ACTIONS"))
            self._log(f"Navigating to Google Local: {target_url}", 20)
            if use_uc_reconnect:
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

            # Auto-solve Google verification / sorry challenge ONLY if an actual challenge is active
            try:
                curr_url = (driver.current_url or "").lower()
                page_title = (driver.title or "").lower()
                is_challenge = (
                    "sorry/index" in curr_url
                    or "/sorry/" in curr_url
                    or "unusual traffic" in page_title
                    or "sorry" in page_title
                    or (hasattr(driver, "is_element_visible") and (
                        driver.is_element_visible("iframe[src*='recaptcha']")
                        or driver.is_element_visible("form#captcha-form")
                        or driver.is_element_visible("#recaptcha")
                    ))
                )
                if is_challenge:
                    self._log("Detected Google verification challenge; executing automated UC bypass...", 22)
                    for solver_method in ["uc_gui_handle_rc", "uc_gui_click_rc", "uc_gui_click_captcha", "uc_gui_handle_captcha"]:
                        if hasattr(driver, solver_method):
                            try:
                                self._log(f"Attempting {solver_method}()...", 23)
                                getattr(driver, solver_method)()
                                time.sleep(3.5)
                                curr_url = (driver.current_url or "").lower()
                                if "sorry" not in curr_url and "unusual traffic" not in (driver.title or "").lower():
                                    self._log("Automated UC bypass successful!", 25)
                                    break
                            except Exception as ce:
                                self._log(f"{solver_method} notice: {ce}", 23)
            except Exception:
                pass

            is_all_pages = (max_pages <= 0)
            effective_max = 100 if is_all_pages else max_pages
            page = 1

            while page <= effective_max:
                page_label = f"Page {page} (All Pages Mode)" if is_all_pages else f"Page {page}/{max_pages}"
                progress_pct = min(90, int(20 + ((page - 1) * 65 / min(effective_max, 25))))
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
                        or soup.find_all("div", class_="w7Dbne")
                        or soup.find_all("div", class_="uMdZh")
                        or soup.find_all("div", {"jscontroller": "AtSb"})
                        or soup.find_all("div", class_="cXedhc")
                        or soup.find_all("div", class_="rllt__details")
                        or soup.find_all("div", class_="C8fQm")
                    )
                    if cards:
                        break
                    time.sleep(0.4)

                # Retry on Page 1: If udm=local yields 0 cards on initial poll, re-try with udm=local preserved
                if not cards and page == 1:
                    self._log("No cards detected on initial poll; retrying Google Local search...", 26)
                    # Check for any obstructing consent buttons first
                    for accept_sel in ["button#L2AGLb", "button:contains('Accept all')", "button:contains('I agree')", "form[action*='consent'] button"]:
                        try:
                            if driver.is_element_visible(accept_sel):
                                driver.click(accept_sel, timeout=1)
                                time.sleep(1.0)
                                break
                        except Exception:
                            pass

                    # Reconnect to target_url with udm=local strictly preserved
                    if use_uc_reconnect:
                        try:
                            driver.uc_open_with_reconnect(target_url, reconnect_time=3.5)
                        except Exception:
                            driver.get(target_url)
                    else:
                        driver.get(target_url)
                    time.sleep(2.5)

                    for poll_i in range(25):
                        page_source = driver.page_source
                        soup = BeautifulSoup(page_source, "html.parser")
                        cards = (
                            soup.find_all("div", class_="VkpGBb")
                            or soup.find_all("div", class_="w7Dbne")
                            or soup.find_all("div", class_="uMdZh")
                            or soup.find_all("div", {"jscontroller": "AtSb"})
                            or soup.find_all("div", class_="cXedhc")
                            or soup.find_all("div", class_="rllt__details")
                            or soup.find_all("div", class_="C8fQm")
                        )
                        if cards:
                            self._log(f"Found {len(cards)} listings on Google Local retry!", 28)
                            break
                        time.sleep(0.4)

                # Check if search was challenged or blocked by Google anti-bot verification
                if not cards and page == 1:
                    curr_url = (driver.current_url or "").lower()
                    page_title = (driver.title or "").lower()
                    is_blocked = (
                        "sorry/index" in curr_url
                        or "/sorry/" in curr_url
                        or "google.com/sorry" in curr_url
                        or "unusual traffic" in page_title
                        or "sorry" in page_title
                    )

                    # Try fallback to standard Google web search if udm=local was challenged
                    if is_blocked:
                        self._log("Detected Google verification checkpoint (sorry/index). Attempting fallback to standard web search...", 27)
                        fallback_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(keyword)}+in+{urllib.parse.quote_plus(city)}&gl={gl}&hl={hl}"
                        try:
                            if hasattr(driver, "uc_open_with_reconnect"):
                                try:
                                    driver.uc_open_with_reconnect(fallback_url, reconnect_time=3.5)
                                except Exception:
                                    driver.get(fallback_url)
                            else:
                                driver.get(fallback_url)
                            time.sleep(3.0)
                            curr_url = (driver.current_url or "").lower()
                            page_title = (driver.title or "").lower()
                            is_blocked = (
                                "sorry/index" in curr_url
                                or "/sorry/" in curr_url
                                or "google.com/sorry" in curr_url
                                or "unusual traffic" in page_title
                                or "sorry" in page_title
                            )
                            if not is_blocked:
                                for poll_i in range(25):
                                    page_source = driver.page_source
                                    soup = BeautifulSoup(page_source, "html.parser")
                                    cards = (
                                        soup.find_all("div", class_="VkpGBb")
                                        or soup.find_all("div", class_="w7Dbne")
                                        or soup.find_all("div", class_="uMdZh")
                                        or soup.find_all("div", {"jscontroller": "AtSb"})
                                        or soup.find_all("div", class_="cXedhc")
                                        or soup.find_all("div", class_="rllt__details")
                                        or soup.find_all("div", class_="C8fQm")
                                    )
                                    if cards:
                                        self._log(f"Fallback search succeeded! Found {len(cards)} listings on standard search.", 28)
                                        break
                                    time.sleep(0.4)
                        except Exception as fe:
                            self._log(f"Fallback search notice: {fe}", 27)

                    # If still blocked by Google sorry challenge after all bypass attempts, RAISE GoogleBlockedException
                    if is_blocked:
                        self._log(f"Google anti-bot verification challenge active ({curr_url}). Runner IP is temporarily rate-limited; halting search to preserve queue.", 85)
                        raise GoogleBlockedException(f"Google anti-bot verification challenge active ({curr_url}). Runner IP is rate-limited.")

                if not cards:
                    if page > 1:
                        self._log(f"Pagination complete: all available Google Local listings extracted up to Page {page - 1}.", 95)
                    else:
                        page_title = driver.title or "No Title"
                        curr_url = driver.current_url or "No URL"
                        src_preview = (driver.page_source or "")[:250].replace("\n", " ")
                        self._log(f"No listings found on {page_label}. URL: {curr_url} | Title: {page_title} | HTML snippet: {src_preview}", 90)
                    break

                # Extract embedded places data directly from Google Places client script
                embedded_places = extract_embedded_places_data(driver.page_source)

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

                    # Correlate with embedded Places data
                    norm_key = re.sub(r"[^\w\s]", "", name.lower()).strip()
                    emb = embedded_places.get(norm_key)
                    if not emb:
                        for k, v in embedded_places.items():
                            if k.startswith(norm_key[:15]) or norm_key.startswith(k[:15]):
                                emb = v
                                break

                    # Website: prioritize embedded place website if available
                    direct_web = emb.get("website_url") if emb else ""
                    goto_url = ""
                    if not direct_web:
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

                    # Extract real physical address and phone number
                    address_part, phone = extract_address_and_phone(card, name)
                    if emb and emb.get("phone") and not phone:
                        phone = emb["phone"]
                    if emb and emb.get("address") and (not address_part or address_part == "N/A"):
                        address_part = emb["address"]

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
                    if is_all_pages:
                        self._log(f"Completed all {page} available pages of Google Local search results.", page_progress)
                    else:
                        self._log(f"Reached requested limit of {max_pages} pages.", page_progress)
                    break

            self._log(f"Scraping completed! Successfully extracted {len(self.results)} companies.", 100)
            return self.results

        except GoogleBlockedException as gbe:
            self.error = str(gbe)
            self._log(f"Rate-limit error during scrape: {gbe!s}", 100)
            raise
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
