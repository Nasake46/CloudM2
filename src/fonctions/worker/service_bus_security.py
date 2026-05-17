import re

import requests

from service_bus_errors import ProcessingError

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"OPENAI_API_KEY\s*[=:]\s*\S+", re.IGNORECASE),
)

_GENERIC_ERROR = "Traitement en erreur."


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def sanitize_error_text(text: str | None, *, max_length: int = 500) -> str:
    if not text or not text.strip():
        return _GENERIC_ERROR
    cleaned = text.strip()
    if contains_secret(cleaned):
        return _GENERIC_ERROR
    return cleaned[:max_length]


def public_error_message(exc: Exception) -> str:
    if isinstance(exc, ProcessingError):
        return sanitize_error_text(str(exc))

    if isinstance(exc, RuntimeError) and "OPENAI_API_KEY" in str(exc):
        return "Configuration du traitement IA incomplète."

    if isinstance(exc, requests.RequestException):
        return "Échec du traitement IA."

    return _GENERIC_ERROR
