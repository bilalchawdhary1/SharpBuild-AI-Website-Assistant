"""Stage 3a: discover and download SharpBuild pages as raw HTML.

Run from the backend root:  python -m ingestion.crawl
"""
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://sharpbuild.io"
USER_AGENT = "SharpBuildAssistantBot/0.1 (portfolio learning project)"
RAW_DIR = Path("data/raw")
DELAY_SECONDS = 1.0   # be polite: one request per second
MAX_PAGES = 150       # safety cap so a bug can't crawl forever
SKIP_EXT = re.compile(
    r"\.(png|jpe?g|gif|webp|svg|ico|pdf|zip|css|js|xml|json|txt|mp4|woff2?)$", re.I
)


def normalize(url: str) -> str | None:
    """Return one canonical form per page, or None if it's not a crawlable page."""
    url, _ = urldefrag(url)                      # drop #fragment
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return None
    if p.netloc.lower() != urlparse(BASE_URL).netloc:
        return None                              # stay on sharpbuild.io
    path = p.path or "/"
    if SKIP_EXT.search(path):
        return None
    if path != "/":
        path = path.rstrip("/")
    return f"{p.scheme}://{p.netloc.lower()}{path}"   # query string dropped on purpose


def canonical_url(html: str, final_url: str) -> str:
    """Prefer the page's own <link rel="canonical">; fall back to the fetched URL."""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("link", rel="canonical")
    if tag and tag.get("href"):
        n = normalize(urljoin(final_url, tag["href"]))
        if n:
            return n
    return normalize(final_url) or final_url


def slug(url: str) -> str:
    path = urlparse(url).path.lower()
    return re.sub(r"[^a-z0-9]+", "_", path).strip("_") or "home"


def load_robots(client: httpx.Client) -> RobotFileParser:
    rp = RobotFileParser()
    try:
        r = client.get(f"{BASE_URL}/robots.txt")
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    except httpx.HTTPError:
        rp.parse([])
    return rp


def fetch_with_retries(client: httpx.Client, url: str, *,
                       attempts: int = 3, base_delay: float = 1.0,
                       sleep=time.sleep) -> httpx.Response:
    """Retry transient HTTP failures once or twice instead of skipping the page."""
    for attempt in range(attempts):
        try:
            response = client.get(url)
        except httpx.HTTPError:
            if attempt == attempts - 1:
                raise
        else:
            if response.status_code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                return response
        sleep(base_delay * (2 ** attempt))
    raise RuntimeError("unreachable")


def sitemap_urls(client: httpx.Client, sitemap_url: str = f"{BASE_URL}/sitemap.xml",
                 depth: int = 0) -> dict[str, float]:
    try:
        r = fetch_with_retries(client, sitemap_url)
    except httpx.HTTPError:
        return {}
    if r.status_code != 200:
        return {}
    found: dict[str, float] = {}
    host = urlparse(BASE_URL).netloc
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        return found

    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name == "sitemap":
            loc = next((c for c in element if c.tag.rsplit("}", 1)[-1] == "loc"), None)
            if loc is not None and loc.text and depth < 2:
                loc_url = loc.text.strip()
                if urlparse(loc_url).netloc == host:
                    found.update(sitemap_urls(client, loc_url, depth + 1))
        if name == "url":
            loc = next((c for c in element if c.tag.rsplit("}", 1)[-1] == "loc"), None)
            priority_element = next(
                (c for c in element if c.tag.rsplit("}", 1)[-1] == "priority"),
                None,
            )
            if loc is None or not loc.text:
                continue
            normalized = normalize(loc.text.strip())
            if not normalized:
                continue
            priority = 0.5
            if priority_element is not None and priority_element.text:
                try:
                    priority = float(priority_element.text)
                except ValueError:
                    pass
            found[normalized] = priority
    return found


def internal_links(html: str, page_url: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        n = normalize(urljoin(page_url, a["href"]))
        if n:
            links.add(n)
    return links


def crawl() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    pages: dict[str, dict] = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT},
                      follow_redirects=True, timeout=15) as client:
        robots = load_robots(client)
        from_sitemap = sitemap_urls(client)
        print(f"sitemap.xml URLs found: {len(from_sitemap)}")
        queue = (
            sorted(from_sitemap, key=lambda url: (-from_sitemap[url], url))
            if from_sitemap
            else [normalize(BASE_URL)]
        )
        seen: set[str] = set()

        while queue and len(pages) < MAX_PAGES:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if not robots.can_fetch(USER_AGENT, url):
                print(f"SKIP (robots.txt): {url}")
                continue
            time.sleep(DELAY_SECONDS)
            try:
                r = fetch_with_retries(client, url)
            except httpx.HTTPError as e:
                print(f"ERROR {url}: {e}")
                continue
            if r.status_code != 200 or "text/html" not in r.headers.get("content-type", ""):
                print(f"SKIP ({r.status_code}): {url}")
                continue

            canon = canonical_url(r.text, str(r.url))
            if canon in pages:
                continue
            fname = f"{slug(canon)}.html"
            (RAW_DIR / fname).write_text(r.text, encoding="utf-8")
            pages[canon] = {
                "file": fname,
                "requested_url": url,
                "final_url": str(r.url),
                "in_sitemap": canon in from_sitemap,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            print(f"OK  {canon}" + ("" if canon in from_sitemap else "   (found via link, not in sitemap)"))
            queue.extend(l for l in internal_links(r.text, str(r.url)) if l not in seen)

    (RAW_DIR / "index.json").write_text(json.dumps(pages, indent=2), encoding="utf-8")
    print(f"\nSaved {len(pages)} pages to {RAW_DIR}/")


if __name__ == "__main__":
    crawl()
