import json
import time
import logging
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SEED_URLS = [
    # Handbook top-level sections
    "https://handbook.gitlab.com/handbook/",
    "https://handbook.gitlab.com/handbook/values/",
    "https://handbook.gitlab.com/handbook/company/",
    "https://handbook.gitlab.com/handbook/people-group/",
    "https://handbook.gitlab.com/handbook/engineering/",
    "https://handbook.gitlab.com/handbook/product/",
    "https://handbook.gitlab.com/handbook/marketing/",
    "https://handbook.gitlab.com/handbook/sales/",
    "https://handbook.gitlab.com/handbook/finance/",
    "https://handbook.gitlab.com/handbook/legal/",
    "https://handbook.gitlab.com/handbook/security/",
    "https://handbook.gitlab.com/handbook/support/",
    "https://handbook.gitlab.com/handbook/communication/",
    "https://handbook.gitlab.com/handbook/leadership/",
    "https://handbook.gitlab.com/handbook/hiring/",
    "https://handbook.gitlab.com/handbook/total-rewards/",
    # Direction pages
    "https://about.gitlab.com/direction/",
    "https://about.gitlab.com/direction/create/",
    "https://about.gitlab.com/direction/plan/",
    "https://about.gitlab.com/direction/verify/",
    "https://about.gitlab.com/direction/deploy/",
    "https://about.gitlab.com/direction/secure/",
    "https://about.gitlab.com/direction/monitor/",
    "https://about.gitlab.com/direction/modelops/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; GitLabHandbookBot/1.0; "
        "+https://github.com/yourusername/gitlab-chatbot)"
    )
}

DATA_PATH = Path("data/scraped_pages.json")


def _fetch_html(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch raw HTML, returning None on any error."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return resp.text
    except Exception as exc:
        logger.warning(f"Failed to fetch {url}: {exc}")
        return None


def _parse_page(html: str, url: str) -> Optional[dict]:
   
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                     "form", "noscript", "svg", "img"]):
        tag.decompose()
    
    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"

    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=lambda c: c and "content" in c.lower())
        or soup.body
    )
    if not main:
        return None

    chunks = []
    current_section = ""
    current_text = []

    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "td"]):
        tag_name = el.name
        text = el.get_text(" ", strip=True)
        if not text or len(text) < 10:
            continue

        if tag_name in ("h1", "h2", "h3", "h4"):
            if current_text:
                chunks.append({
                    "section": current_section,
                    "text": " ".join(current_text),
                })
                current_text = []
            current_section = text
        else:
            current_text.append(text)


    if current_text:
        chunks.append({
            "section": current_section,
            "text": " ".join(current_text),
        })

    if not chunks:
        return None

    source_type = "handbook" if "handbook.gitlab.com" in url else "direction"

    return {
        "url": url,
        "title": title,
        "source_type": source_type,
        "chunks": chunks,
    }


def _discover_child_links(html: str, base_url: str) -> list[str]:
    """
    From a seed page, find internal links one level deeper.
    Stays within the same domain + path prefix to avoid crawling all of GitLab.
    """
    soup = BeautifulSoup(html, "lxml")
    from urllib.parse import urljoin, urlparse

    base_parsed = urlparse(base_url)
    prefix = base_parsed.scheme + "://" + base_parsed.netloc + base_parsed.path

    links = set()
    for a in soup.find_all("a", href=True):
        full = urljoin(base_url, a["href"])
        parsed = urlparse(full)
       
        if (
            parsed.netloc == base_parsed.netloc
            and parsed.path.startswith(base_parsed.path)
            and not parsed.fragment
            and full != base_url
        ):
            clean = full.rstrip("/")
            links.add(clean)

    return list(links)


def scrape_all(max_pages: int = 80, force: bool = False) -> list[dict]:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    if DATA_PATH.exists() and not force:
        logger.info("Loading cached scraped data from %s", DATA_PATH)
        with open(DATA_PATH, encoding="utf-8") as f:
            return json.load(f)

    logger.info("Starting scrape of GitLab Handbook and Direction pages...")
    visited: set[str] = set()
    pages: list[dict] = []
    queue: list[str] = list(SEED_URLS)

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        logger.info("[%d/%d] Scraping: %s", len(visited), max_pages, url)
        html = _fetch_html(url)
        if not html:
            continue

        page = _parse_page(html, url)
        if page:
            pages.append(page)

            if url in SEED_URLS and len(visited) < max_pages:
                children = _discover_child_links(html, url)
                for child in children:
                    if child not in visited:
                        queue.append(child)

        time.sleep(0.5)

    logger.info("Scraping complete. %d pages collected.", len(pages))
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(pages, f, indent=2, ensure_ascii=False)
    logger.info("Saved to %s", DATA_PATH)
    return pages


if __name__ == "__main__":
    pages = scrape_all(force=True)
    print(f"Total pages scraped: {len(pages)}")
    total_chunks = sum(len(p["chunks"]) for p in pages)
    print(f"Total content chunks: {total_chunks}")
