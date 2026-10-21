"""
OutreachPilot - Google Local Scraper Engine
Module: scraper_engine.py
Architecture: SeleniumBase (Undetected Chrome) + ThreadPoolExecutor for Parallel Website Resolution
"""

import os
import re
import shutil
import tempfile
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
        if row_text.startswith('"') or row_text.startswith("“"):
            continue

        # Skip rows that are purely rating & category (e.g. "4.8 (269) · Software company")
        if re.search(r"^\d\.\d\s*\(\d+\)", row_text):
            continue

        parts = [p.strip() for p in row_text.split("·")]

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
            if item.get("_goto_url")
        ]

        if not goto_indices:
            for item in items:
                if "website_url" not in item or not item["website_url"]:
                    item["website_url"] = ""
                item.pop("_goto_url", None)
            return items

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
        Executes the scraping process synchronously with progress state updates.
        """
        self.is_running = True
        self.error = None
        self.results = []
        self.progress = 5
        self._log(f"Initializing browser engine for: {keyword} {city} (Pages: {max_pages}, Region: {gl})...", 10)

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

                    # Under Xvfb (DISPLAY environment variable set by xvfb-run in GitHub Actions),
                    # Chrome runs with headless=False in a virtual desktop, allowing full UC Mode
                    # without 127.0.0.1:9222 socket errors and completely avoiding Google bot challenges.
                    has_display = bool(os.environ.get("DISPLAY"))
                    driver_kwargs = {
                        "uc": True,
                        "headless": not has_display and self.headless,
                        "user_data_dir": tmp_profile_dir,
                        "disable_gpu": True,
                        "no_sandbox": True,
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
                driver.uc_open_with_reconnect(target_url, reconnect_time=4.0)
            else:
                driver.get(target_url)

            # Auto-solve Google verification / sorry challenge if triggered on cloud IP
            if "sorry" in (driver.current_url or "").lower():
                self._log("Detected Google verification challenge; executing automated UC bypass...", 21)
                if hasattr(driver, "uc_gui_click_captcha"):
                    try:
                        driver.uc_gui_click_captcha()
                        time.sleep(3.0)
                    except Exception as ce:
                        self._log(f"Captcha click attempt: {ce}")

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

                    # Website goto link
                    goto_a = card.find("a", href=lambda h: h and "/goto?url=" in h)
                    goto_url = goto_a["href"] if goto_a else ""

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
                        "domain": "",
                        "website_url": "",
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
                        driver.uc_open_with_reconnect(next_url, reconnect_time=3.0)
                    else:
                        driver.get(next_url)
                    time.sleep(1.2)
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
