import os
import re
import json
import logging
import time
from urllib.parse import urljoin
from typing import Optional, Dict, Any, List, Tuple

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logging.warning("playwright not available - JS-rendered pages won't be supported")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 8000
M_TAIL_MARGIN = 400
HEAD_MARGIN = 200

HEAD_ANCHORS = [
    r"impressum",
    r"angaben\s+gem[äa]ß\s+§\s*5\s+tm",
    r"angaben\s+gem[äa]ß\s+§\s*5\s+ddg",
    r"anbieter",
    r"diensteanbieter",
    r"anschrift",
    r"kontakt",
    r"firmensitz",
    r"unternehmensgegenstand",
]

TAIL_PATTERNS = [
    (r"(\+49|0049)\s*\d[\d\s\-\/\(\)]{5,}", "phone"),
    (r"\bDE\s?\d{9}\b", "vat"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "email"),
    (r"\b(HRB|HRA)\s*\d+\b", "handelsregister"),
    (r"(registergericht|amtsgericht)\s+[A-ZÄÖÜ][a-zäöüß]+", "register"),
    (r"(verantwortlich|vertreten\s+durch|geschäftsführer|vorstand|inhaltlich\s+verantwortlich|haftung\s+für\s+inhalt)", "responsibility"),
    (r"\b(datenschutz|agb|impressum|haftung|haftungsausschluss|disclaimer|copyright|©|©\s*\d{4}|all\s+rights?\s+reserved)\b", "footer"),
]

BOILERPLATE_PATTERNS = [
    r"^\s*(datenschutz|agb|impressum|haftung|haftungsausschluss|disclaimer|copyright|©|©\s*\d{4}|all\s+rights?\s+reserved)\s*$",
    r"^\s*(menü|menu|navigation|nav)\s*$",
    r"^\s*(cookie|cookie-banner|cookie-banner|einstellungen|settings)\s*$",
    r"^\s*(sprache|language|deutsch|english|français|español|italiano)\s*$",
    r"^\s*(©|©\s*\d{4}|©\s*[A-Za-z\s]+)\s*$",
    r"^\s*(menue|menu|skip\s+to\s+content|zum\s+inhalt\s+springen)\s*$",
]


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url):
        return "https://" + url
    return url


def fetch_page(url: str, timeout: int = 15) -> Optional[requests.Response]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        if response.encoding is None or response.encoding.lower() == 'iso-8859-1':
            response.encoding = response.apparent_encoding
        return response
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def find_impressum_link_with_playwright(url: str, timeout: int = 15) -> Optional[str]:
    if not PLAYWRIGHT_AVAILABLE:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout * 1000)

            impressum_links = page.get_by_text("Impressum", exact=True).all()
            if impressum_links:
                href = impressum_links[0].get_attribute("href")
                if href:
                    return urljoin(url, href)

            impressum_partial = page.get_by_text("impressum", exact=False).all()
            if impressum_partial:
                href = impressum_partial[0].get_attribute("href")
                if href:
                    return urljoin(url, href)

            links = page.locator('a[href*="impressum"], a[href*="imprint"]').all()
            if links:
                href = links[0].get_attribute("href")
                if href:
                    return urljoin(url, href)

            links_en = page.locator('a[href*="imprint"]').all()
            if links_en:
                href = links_en[0].get_attribute("href")
                if href:
                    return urljoin(url, href)

            browser.close()
            return None
    except Exception as e:
        logger.warning(f"Playwright failed to find impressum link for {url}: {e}")
        return None


def find_impressum_link(html: str, base_url: str, url: Optional[str] = None, timeout: int = 15) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True).lower()
        if text in ("impressum", "imprint", "impressum/imprint", "imprint/impressum"):
            href = a["href"]
            return urljoin(base_url, href)

    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if "impressum" in href or "imprint" in href:
            return urljoin(base_url, a["href"])

    if url:
        logger.info(f"Static HTML search failed, trying Playwright for {url}")
        return find_impressum_link_with_playwright(url)

    return None


def extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "form", "aside", "iframe", "meta", "link"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def is_boilerplate_line(line: str) -> bool:
    line_lower = line.lower().strip()
    for pattern in BOILERPLATE_PATTERNS:
        if re.match(pattern, line_lower, re.IGNORECASE):
            return True
    return False


def strip_boilerplate_lines(text: str) -> str:
    lines = text.splitlines()
    filtered = [line for line in text.splitlines() if not is_boilerplate_line(line)]
    return "\n".join(filtered)


def find_head_anchor(text: str) -> Optional[int]:
    text_lower = text.lower()
    best_pos = None

    for pattern in HEAD_ANCHORS:
        matches = list(re.finditer(pattern, text_lower, re.IGNORECASE))
        for match in matches:
            pos = match.start()
            if best_pos is None or pos < best_pos:
                best_pos = pos

    return best_pos


def find_tail_anchors(text: str) -> List[Tuple[int, str]]:
    matches = []
    text_lower = text.lower()

    for pattern, label in TAIL_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            matches.append((match.end(), label))

    matches.sort(key=lambda x: x[0])
    return matches


def optimize_text(text: str) -> Tuple[str, Dict[str, Any]]:
    original_len = len(text)
    original_tokens_est = len(text) // 4

    text = strip_boilerplate_lines(text)

    if len(text) <= MAX_TEXT_CHARS:
        return text, {
            "original_chars": original_len,
            "optimized_chars": len(text),
            "original_tokens_est": original_tokens_est,
            "optimized_tokens_est": len(text) // 4,
            "method": "under_threshold",
            "reduction_pct": 0.0,
        }

    head_pos = find_head_anchor(text)
    tail_matches = find_tail_anchors(text)

    head_start = 0
    if head_pos is not None:
        head_start = max(0, head_pos - HEAD_MARGIN)

    tail_end = len(text)
    if tail_matches:
        last_tail_end = tail_matches[-1][0]
        tail_end = min(len(text), last_tail_end + M_TAIL_MARGIN)

    if head_pos is not None and tail_matches:
        if head_pos < tail_matches[-1][0]:
            optimized = text[head_start:tail_end]
            method = "sandwich"
        else:
            optimized = text[max(0, tail_matches[-1][0] - MAX_TEXT_CHARS):]
            method = "tail_only"
    elif head_pos is not None:
        optimized = text[head_start:head_start + MAX_TEXT_CHARS]
        method = "head_only"
    elif tail_matches:
        optimized = text[max(0, tail_matches[-1][0] - MAX_TEXT_CHARS):]
        method = "tail_only"
    else:
        half = MAX_TEXT_CHARS // 2
        optimized = text[:half] + "\n...\n" + text[-half:]
        method = "head_tail_window"

    optimized = verify_optimized_text(text, optimized)

    if len(optimized) > MAX_TEXT_CHARS:
        half = MAX_TEXT_CHARS // 2
        optimized = optimized[:MAX_TEXT_CHARS // 2] + "\n...\n" + optimized[-MAX_TEXT_CHARS // 2:]
        method += "_truncated"

    stats = {
        "original_chars": original_len,
        "optimized_chars": len(optimized),
        "original_tokens_est": original_tokens_est,
        "optimized_tokens_est": len(optimized) // 4,
        "method": method,
        "reduction_pct": round((1 - len(optimized) / original_len) * 100, 1) if original_len > 0 else 0,
    }

    return optimized, stats


def verify_optimized_text(original: str, optimized: str) -> str:
    signals = [
        r"impressum",
        r"angaben\s+gem[äa]ß\s+§\s*5\s+tm",
        r"anbieter|diensteanbieter",
        r"(\+49|0049)\s*\d",
        r"\bDE\s?\d{9}\b",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        r"\b(HRB|HRA)\s*\d+\b",
        r"(verantwortlich|geschäftsführer|vorstand)",
    ]

    has_signal = any(re.search(p, original, re.IGNORECASE) for p in signals)
    if not has_signal:
        return original

    has_signal_optimized = any(re.search(p, optimized, re.IGNORECASE) for p in [
        r"(\+49|0049)\s*\d",
        r"\bDE\s?\d{9}\b",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        r"\b(HRB|HRA)\s*\d+\b",
        r"(verantwortlich|geschäftsführer|vorstand)",
    ])

    if not has_signal_optimized:
        logger.warning("Optimization removed all legal signals, using original text")
        return original

    return optimized


def resolve_impressum_url(home_url: str, html: str) -> Optional[str]:
    return find_impressum_link(html, home_url)


def fetch_and_process_impressum(company_name: str, web_url: str, timeout: int = 15) -> Dict[str, Any]:
    result = {
        "impressum_url": None,
        "optimized_text": None,
        "stats": {},
        "error": None,
        "status": None,
    }

    home_url = normalize_url(web_url)
    if not home_url:
        return {"error": "No website URL", "status": 5}

    logger.info(f"Fetching home page: {home_url}")
    home_response = fetch_page(home_url)
    if not home_response:
        return {"error": "Failed to fetch home page", "status": 4}

    impressum_url = find_impressum_link(home_response.text, home_url, home_url)
    if not impressum_url:
        logger.warning(f"No Impressum link found for {home_url}")
        return {"error": "No Impressum/Imprint link found", "status": 1}

    result["impressum_url"] = impressum_url
    logger.info(f"Found Impressum URL: {impressum_url}")

    logger.info(f"Fetching Impressum page: {impressum_url}")
    impressum_response = fetch_page(impressum_url)
    if not impressum_response:
        return {"error": "Failed to fetch Impressum page", "status": 4}

    visible_text = extract_visible_text(impressum_response.text)
    if not visible_text.strip():
        return {"error": "Impressum page has no visible text", "status": 2}

    optimized_text, stats = optimize_text(visible_text)
    logger.info(f"Text optimization: {len(visible_text)} -> {stats.get('optimized_chars', 0)} chars ({stats.get('reduction_pct', 0):.1f}% reduction)")

    return {
        "impressum_url": impressum_url,
        "optimized_text": optimized_text,
        "stats": stats,
        "error": None,
        "status": None,
    }


def get_deepseek_client():
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY environment variable not set")

    return {
        "api_key": api_key,
        "base_url": "https://api.deepseek.com",
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
    }


SYSTEM_PROMPT = """\
You extract legally required company information ("Impressum" / "Imprint") from
German-language website text.
Return ONLY a valid JSON object (no markdown fences, no commentary) that parses
with json.loads. The JSON must have exactly these keys:
{
  "company_name": "<string or null>",
  "postal_address": {
    "street": "<string or null>",
    "house_no": "<string or null>",
    "postcode": "<string or null>",
    "city": "<string or null>",
    "country": "<string or null>"
  },
  "handelsregister": "<string or null>",
  "vat_number": "<string or null>",
  "phone": "<string or null>",
  "email": "<string or null>",
  "responsible_person": "<string or null>"
}
Rules:
- Extract ONLY information actually present in the text; use null when absent.
- Do not invent or guess values.
- phone: keep the international format when possible (e.g. +49 ...).
- vat_number: German VAT ids look like DE followed by 9 digits.
- email: lowercase.
- responsible_person: the named person or role legally responsible for the
  content (e.g. Geschaeftsfuehrer, Vorstand, "inhaltlich verantwortlich").
- Output valid JSON only.
Example:
{
  "company_name": "Muster GmbH",
  "postal_address": {
    "street": "Musterstraße",
    "house_no": "12",
    "postcode": "10115",
    "city": "Berlin",
    "country": "Germany"
  },
  "handelsregister": "HRB 123456",
  "vat_number": "DE123456789",
  "phone": "+49 30 12345678",
  "email": "info@example.de",
  "responsible_person": "Max Mustermann, Geschäftsführer"
}"""


def call_deepseek(optimized_text: str, max_retries: int = 3, backoff_base: float = 1.0) -> Dict[str, Any]:
    client_config = get_deepseek_client()
    api_key = client_config["api_key"]
    model = client_config["model"]

    user_prompt = f"Extract the Impressum data from the text below and return JSON:\n\n{optimized_text}"

    payload = {
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract the Impressum data from the text below and return JSON:\n\n{optimized_text}"},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 1024,
        "temperature": 0,
    }

    headers = {
        "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
        "Content-Type": "application/json",
    }

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}", "Content-Type": "application/json"},
                json={
                    "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Extract the Impressum data from the text below and return JSON:\n\n{optimized_text}"},
                    ],
                    "response_format": {"type": "json_object"},
                    "max_tokens": 1024,
                    "temperature": 0,
                },
                timeout=60,
            )

            if resp.status_code == 429:
                wait_time = backoff_base * (2 ** attempt)
                logger.warning(f"Rate limited, waiting {wait_time}s before retry {attempt + 1}")
                time.sleep(wait_time)
                continue

            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"]
            if not content or not content.strip():
                raise ValueError("Empty response from DeepSeek")

            parsed = json.loads(content)

            required_keys = [
                "company_name", "postal_address", "handelsregister",
                "vat_number", "phone", "email", "responsible_person"
            ]
            for key in required_keys:
                if key not in parsed:
                    parsed[key] = None

            if not isinstance(parsed.get("postal_address"), dict):
                parsed["postal_address"] = {
                    "street": None, "house_no": None,
                    "postcode": None, "city": None, "country": None
                }

            return parsed

        except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"DeepSeek call failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1 * (2 ** attempt))
            else:
                raise

    raise RuntimeError("DeepSeek API failed after retries")


def extract_with_deepseek(optimized_text: str) -> Dict[str, Any]:
    try:
        return call_deepseek(optimized_text)
    except Exception as e:
        logger.error(f"DeepSeek extraction failed: {e}")
        raise