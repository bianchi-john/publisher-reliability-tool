"""Deterministic URL, publisher, and model identities."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from urllib.parse import unquote_plus, urlsplit, urlunsplit

try:
    import idna
except ImportError:  # pragma: no cover - dependency is present in installed app
    idna = None

from .errors import AppError


NAMESPACE = uuid.UUID("6f63a5f4-97aa-4bb8-a73f-2a30fc9fcf31")
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "homepageposition"}
BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_url(raw_url: str) -> str:
    if not isinstance(raw_url, str):
        raise AppError("INVALID_URL", "URL must be a string.")
    value = raw_url.strip()
    if not value or len(value.encode("utf-8")) > 8192:
        raise AppError("INVALID_URL", "URL is empty or exceeds 8,192 bytes.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise AppError("INVALID_URL", "URL contains control characters.")
    if BAD_PERCENT.search(value):
        raise AppError("INVALID_URL", "URL contains malformed percent encoding.")

    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise AppError("INVALID_URL", "URL syntax is invalid.") from exc
    if parts.scheme.lower() not in {"http", "https"}:
        raise AppError("INVALID_URL", "URL scheme must be HTTP or HTTPS.")
    if not parts.hostname or parts.username is not None or parts.password is not None:
        raise AppError("INVALID_URL", "URL must have a DNS hostname and no user info.")

    try:
        if idna is not None:
            hostname = idna.encode(
                parts.hostname, uts46=True, transitional=False
            ).decode("ascii").lower()
        else:
            hostname = parts.hostname.encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError) as exc:
        raise AppError("INVALID_URL", "URL hostname is invalid.") from exc
    if "." not in hostname and hostname != "localhost":
        raise AppError("INVALID_URL", "URL must use a DNS hostname.")

    default_port = (parts.scheme.lower() == "http" and port == 80) or (
        parts.scheme.lower() == "https" and port == 443
    )
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"
    path = parts.path or "/"

    retained: list[str] = []
    for component in parts.query.split("&") if parts.query else []:
        encoded_key = component.split("=", 1)[0]
        try:
            key = unquote_plus(encoded_key).lower()
        except UnicodeDecodeError as exc:
            raise AppError("INVALID_URL", "URL query encoding is invalid.") from exc
        if key.startswith("utm_") or key in TRACKING_KEYS:
            continue
        retained.append(component)

    return urlunsplit(
        (parts.scheme.lower(), netloc, path, "&".join(retained), "")
    )


def normalized_hostname(canonical_url: str) -> str:
    host = urlsplit(canonical_url).hostname
    if host is None:
        raise AppError("INVALID_URL", "URL has no hostname.")
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def article_id(canonical_url: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"article:{canonical_url}"))


def publisher_id(hostname: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"publisher:{hostname}"))


def imported_run_id(article: str, model: str, import_identifier: str) -> str:
    value = f"prediction-run:{article}:{model}:import:{import_identifier}"
    return str(uuid.uuid5(NAMESPACE, value))


def import_id(content_sha256: str, schema_version: str = "1") -> str:
    return str(uuid.uuid5(NAMESPACE, f"import:{content_sha256}:{schema_version}"))

