from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, List

from flask import Request, jsonify
from google.api_core.exceptions import RetryError
from requests import exceptions as requests_exceptions

from utils import get_env, prepare_documents
from vectorstore import upsert_documents

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Gereksiz gizli bilgileri maskeler."""
    redacted = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in {"authorization", "x-ingest-token"}:
            redacted[key] = "***REDACTED***"
        else:
            redacted[key] = value
    return redacted


def _unwrap_retry_http_error(exc: RetryError) -> requests_exceptions.HTTPError | None:
    """RetryError içindeki HTTPError (varsa) nesnesini çıkarır."""
    last_attempt = getattr(exc, "last_attempt", None)
    if not last_attempt:
        return None

    root_exc = last_attempt.exception()
    if isinstance(root_exc, requests_exceptions.HTTPError):
        return root_exc
    return None


def _skip_url(url: str, status: str, detail: str | None = None) -> Dict[str, str]:
    """Atlanan URL için log kaydı ve sonuç sözlüğü oluşturur."""
    logger.warning(
        "URL skipped",
        extra={"url": url, "status": status, "detail": detail},
    )
    return {"url": url, "status": status}


def ingest_stripe_docs(request: Request) -> Any:
    logger.info(
        "Ingest request received",
        extra={"headers": _redact_headers(dict(request.headers))},
    )

    try:
        auth_header = request.headers.get("X-Ingest-Token")
        expected_token = get_env("INGEST_FUNCTION_TOKEN", required=False)
        if expected_token:
            if auth_header != expected_token:
                logger.warning("Unauthorized request: missing or invalid X-Ingest-Token")
                return jsonify({"error": "Unauthorized"}), 401

        urls_csv = get_env("STRIPE_DOC_URLS")
        chunk_size = int(get_env("CHUNK_SIZE"))
        overlap = int(get_env("CHUNK_OVERLAP"))

        urls = [url.strip() for url in urls_csv.split(",") if url.strip()]
        if not urls:
            logger.warning("No URLs provided after parsing STRIPE_DOC_URLS env")
            return jsonify({"error": "No URLs provided"}), 400

        logger.info(
            "Preparing documents",
            extra={"url_count": len(urls), "chunk_size": chunk_size, "overlap": overlap},
        )

        all_documents: List[Any] = []
        skipped_urls: List[Dict[str, str]] = []

        for url in urls:
            try:
                docs = prepare_documents([url], chunk_size=chunk_size, overlap=overlap)
                all_documents.extend(docs)
                logger.info(
                    "Prepared documents for URL",
                    extra={"url": url, "document_count": len(docs)},
                )
            except RetryError as exc:
                http_error = _unwrap_retry_http_error(exc)
                if (
                    http_error
                    and http_error.response is not None
                    and http_error.response.status_code == 404
                ):
                    skipped_urls.append(
                        _skip_url(url, "404", detail=str(http_error))
                    )
                    continue

                logger.exception(
                    "RetryError raised during document preparation",
                    extra={"url": url},
                )
                raise
            except requests_exceptions.HTTPError as exc:
                status_code = (
                    exc.response.status_code if exc.response is not None else "unknown"
                )
                if status_code == 404:
                    skipped_urls.append(
                        _skip_url(url, "404", detail=str(exc))
                    )
                    continue

                logger.exception(
                    "HTTPError raised during document preparation",
                    extra={"url": url, "status_code": status_code},
                )
                raise
            except requests_exceptions.RequestException as exc:
                logger.exception(
                    "RequestException raised during document preparation",
                    extra={"url": url},
                )
                raise

        if not all_documents and skipped_urls:
            logger.warning(
                "No documents ingested; every URL failed and was skipped",
                extra={"skipped_count": len(skipped_urls)},
            )
            return (
                jsonify(
                    {
                        "status": "skipped",
                        "ingested": 0,
                        "skipped": skipped_urls,
                    }
                ),
                207,
            )

        logger.info(
            "Upserting documents",
            extra={"document_count": len(all_documents), "skipped_count": len(skipped_urls)},
        )
        upsert_documents(all_documents)

        logger.info(
            "Ingestion completed successfully",
            extra={
                "ingested_documents": len(all_documents),
                "skipped_urls": skipped_urls,
            },
        )
        return jsonify(
            {
                "status": "ok",
                "ingested": len(all_documents),
                "skipped": skipped_urls,
            }
        )

    except RetryError as exc:
        logger.exception("RetryError raised during document ingestion")

        last_attempt = getattr(exc, "last_attempt", None)
        if last_attempt and last_attempt.exception():
            root_exc = last_attempt.exception()
            logger.error("Underlying exception for RetryError: %s", root_exc)
            logger.error(
                "Underlying traceback:\n%s",
                "".join(
                    traceback.format_exception(
                        type(root_exc),
                        root_exc,
                        root_exc.__traceback__,
                    )
                ),
            )

        return jsonify({"error": "RetryError", "details": str(exc)}), 500

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled exception during ingestion")
        return jsonify({"error": str(exc)}), 500