import json
import logging
import os
import hashlib
from typing import List, Dict, Any, Iterable, Optional
from urllib.parse import urljoin
from uuid import uuid5, NAMESPACE_URL

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_env(name: str, default: Optional[str] = None, required: bool = True) -> str:
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_text_from_html(markup: str, base_url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(markup, "html.parser")

    title_tag = soup.find("h1")
    title = normalize_whitespace(title_tag.get_text()) if title_tag else "Untitled"

    article = soup.find("article") or soup.body
    paragraphs: List[str] = []
    headings: List[str] = []
    sections: List[Dict[str, Any]] = []

    if article:
        current_heading = title
        for elem in article.descendants:
            if elem.name in {"h1", "h2", "h3"}:
                current_heading = normalize_whitespace(elem.get_text())
                headings.append(current_heading)
            elif elem.name == "p":
                text = normalize_whitespace(elem.get_text())
                if text:
                    paragraphs.append(text)
                    sections.append({"heading": current_heading, "text": text})

    links = [
        urljoin(base_url, a.get("href"))
        for a in soup.find_all("a", href=True)
    ]

    return {
        "title": title,
        "paragraphs": paragraphs,
        "sections": sections,
        "links": links,
    }


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> List[str]:
    words = text.split()
    if not words:
        return []

    chunks: List[str] = []
    start = 0
    step = chunk_size - overlap

    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += step

    return chunks


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_url(url: str, timeout: int = 30) -> Optional[str]:
    headers = {
        "User-Agent": "StripeRAGBot/1.0 (+https://example.com)"
    }
    response = requests.get(url, headers=headers, timeout=timeout)

    if response.status_code == 404:
        logger.warning("URL %s 404 döndü, atlanıyor.", url)
        return None

    response.raise_for_status()
    return response.text


def prepare_documents(urls: Iterable[str], chunk_size: int, overlap: int) -> List[Dict[str, Any]]:
    documents: List[Dict[str, Any]] = []

    for url in urls:
        html = fetch_url(url)
        if html is None:
            logger.info("URL %s ingest listesinde atlandı.", url)
            continue

        parsed = extract_text_from_html(html, url)

        full_text = " ".join(parsed["paragraphs"])
        chunks = chunk_text(full_text, chunk_size=chunk_size, overlap=overlap)

        for idx, chunk in enumerate(chunks):
            doc_uuid_source = f"{url}-{idx}-{chunk[:100]}"
            doc_id = str(uuid5(NAMESPACE_URL, doc_uuid_source))
            heading = parsed["sections"][idx]["heading"] if idx < len(parsed["sections"]) else parsed["title"]
            documents.append(
                {
                    "id": doc_id,
                    "title": parsed["title"],
                    "url": url,
                    "content": chunk,
                    "section": heading,
                    "chunk_index": idx,
                }
            )
    return documents