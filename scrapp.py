import csv
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from seleniumbase import Driver

# Ensure UTF-8 output on Windows terminal
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


class UltraFastGoogleLocalScraper:
    """High-performance scraper for Google Local listings with parallel resolution."""

    def __init__(self, headless: bool = True, max_workers: int = 20):
        self.headless = headless
        self.max_workers = max_workers
        self.driver = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        })

    def __enter__(self):
        # Disable images, stylesheets, media, and heavy assets for blazing fast loading
        self.driver = Driver(
            uc=True,
            headless=self.headless,
            block_images=True,
            disable_csp=True,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()
        if self.driver:
            self.driver.quit()

    def _resolve_single_website(self, goto_url: str) -> str:
        """Resolve a single /goto URL redirect via thread-safe HTTP connection pool."""
        if not goto_url:
            return "N/A"
        if not goto_url.startswith("http"):
            goto_url = "https://www.google.com" + goto_url

        try:
            r = self.session.get(
                goto_url,
                allow_redirects=False,
                timeout=4.0,
            )
            return r.headers.get("Location") or goto_url
        except Exception:
            return goto_url

    def _resolve_websites_parallel(self, items: list) -> list:
        """Resolve all company websites in parallel across worker threads."""
        goto_indices = [
            (idx, item["_goto_url"])
            for idx, item in enumerate(items)
            if item.get("_goto_url")
        ]

        if not goto_indices:
            for item in items:
                item["website"] = "N/A"
                item.pop("_goto_url", None)
            return items

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(goto_indices))) as executor:
            future_to_idx = {
                executor.submit(self._resolve_single_website, url): idx
                for idx, url in goto_indices
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    items[idx]["website"] = future.result()
                except Exception:
                    items[idx]["website"] = items[idx]["_goto_url"]

        for item in items:
            if "website" not in item:
                item["website"] = "N/A"
            item.pop("_goto_url", None)

        return items

    def _extract_location(self, card, maps_link: str) -> str:
        """Extract clean address from Maps URL or card details."""
        if maps_link and "/maps/dir//" in maps_link:
            try:
                raw = maps_link.split("/maps/dir//")[1].split("/data=")[0]
                unquoted = urllib.parse.unquote_plus(raw)
                parts = [p.strip() for p in unquoted.split(",") if p.strip()]
                if len(parts) > 1:
                    return ", ".join(parts[1:])
                return unquoted
            except Exception:
                pass

        details_div = card.find("div", class_="rllt__details")
        if details_div:
            rows = details_div.find_all("div", recursive=False)
            for row in rows:
                text = row.get_text(strip=True)
                if (
                    "·" in text
                    and not re.search(r"^\d\.\d", text)
                    and "Open" not in text
                    and "Closed" not in text
                ):
                    parts = text.split("·")
                    address_part = parts[0].strip()
                    if "years in business" in address_part and len(parts) > 1:
                        address_part = parts[1].strip()
                    return address_part

        return "N/A"

    def search_local(
        self, query: str, max_pages: int = 5, gl: str = "in", hl: str = "en"
    ):
        """Ultra-fast local search with instant polling and concurrent resolution."""
        all_results = []
        encoded_query = urllib.parse.quote_plus(query)
        initial_url = (
            f"https://www.google.com/search?q={encoded_query}"
            f"&udm=local&gl={gl}&hl={hl}"
        )

        t_start = time.time()
        print(f"[+] Navigating to Google Local search: '{query}'")
        self.driver.get(initial_url)

        for page in range(1, max_pages + 1):
            page_start_time = time.time()
            print(f"\n[+] Processing Page {page}/{max_pages}...")

            # Fast polling for cards (0.2s interval)
            cards = []
            soup = None
            for _ in range(25):  # Max 5s wait
                soup = BeautifulSoup(self.driver.page_source, "html.parser")
                cards = soup.find_all("div", class_="VkpGBb")
                if cards:
                    break
                time.sleep(0.2)

            if not cards:
                print(f"[-] No business listings found on page {page}.")
                break

            page_raw_items = []
            for card in cards:
                name_el = card.find("span", class_="OSrXXb")
                name = name_el.get_text(strip=True) if name_el else None
                if not name:
                    continue

                # Goto link for website
                goto_a = card.find("a", href=lambda h: h and "/goto?url=" in h)
                goto_url = goto_a["href"] if goto_a else None

                # Maps Link
                maps_a = card.find("a", href=lambda h: h and "/maps/dir/" in h)
                maps_link = (
                    ("https://www.google.com" + maps_a["href"])
                    if maps_a
                    else None
                )

                # Location
                location = self._extract_location(card, maps_link)

                # Rating and Reviews
                rating_el = card.find("span", class_="yi40Hd")
                rating = rating_el.get_text(strip=True) if rating_el else "N/A"

                reviews_el = card.find("span", class_="RDApEe")
                reviews = (
                    reviews_el.get_text(strip=True).strip("()")
                    if reviews_el
                    else "N/A"
                )

                page_raw_items.append({
                    "company_name": name,
                    "location": location,
                    "_goto_url": goto_url,
                    "rating": rating,
                    "reviews": reviews,
                    "maps_link": maps_link if maps_link else "N/A",
                })

            # Parallel resolution of all websites on this page
            page_results = self._resolve_websites_parallel(page_raw_items)
            elapsed_page = time.time() - page_start_time
            print(
                f"[OK] Page {page}: Extracted {len(page_results)} companies in {elapsed_page:.2f}s"
            )
            all_results.extend(page_results)

            # Next Page navigation
            if page < max_pages:
                next_btn = soup.find("a", id="pnnext") if soup else None
                if next_btn and next_btn.get("href"):
                    next_url = "https://www.google.com" + next_btn["href"]
                    self.driver.get(next_url)
                else:
                    print("[i] Reached the last page of results.")
                    break

        total_time = time.time() - t_start
        print(f"\n[🚀] Completed {len(all_results)} companies in {total_time:.2f}s total!")
        return all_results


def export_to_csv(results, filename="companies.csv"):
    """Export the extracted companies with name, location, and website link to CSV."""
    if not results:
        print("[-] No results to export.")
        return

    fieldnames = [
        "company_name",
        "location",
        "website",
        "rating",
        "reviews",
        "maps_link",
    ]

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"[+] Successfully saved {len(results)} companies to '{filename}'")


if __name__ == "__main__":
    query = "PHP based companies in Surat"
    max_pages = 5  # Scrapes 5 pages (~100 companies)
    csv_file = "surat_php_companies.csv"

    print(f"Starting Ultra-Fast Google Local Scraper for: '{query}' (Pages: {max_pages})")
    with UltraFastGoogleLocalScraper(headless=True, max_workers=25) as scraper:
        results = scraper.search_local(query=query, max_pages=max_pages)

    print("\n" + "=" * 90)
    print(f"{'Company Name':<35} | {'Location':<30} | {'Website'}")
    print("=" * 90)
    for item in results[:15]:
        name = (item["company_name"][:32] + "..") if len(item["company_name"]) > 34 else item["company_name"]
        loc = (item["location"][:27] + "..") if len(item["location"]) > 29 else item["location"]
        print(f"{name:<35} | {loc:<30} | {item['website']}")
    if len(results) > 15:
        print(f"... and {len(results) - 15} more companies.")

    # Save output to CSV
    export_to_csv(results, csv_file)
