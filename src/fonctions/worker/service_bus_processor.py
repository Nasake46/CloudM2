import json
import logging
import os
import re
from pathlib import PurePosixPath

import azure.functions as func
import requests

from cosmos_jobs import now_iso, update_job
from signalr_messages import HUB_NAME, job_update_payload, serialize_signalr_messages

service_bus_bp = func.Blueprint()

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def get_file_name(payload: dict) -> str:
    file_name = payload.get("fileName") or payload.get("filename")
    if isinstance(file_name, str) and file_name.strip():
        return file_name.strip()

    blob_name = payload.get("blobName")
    if isinstance(blob_name, str) and blob_name.strip():
        return PurePosixPath(blob_name).name

    return "document"


def normalize_tags(tags: list) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for tag in tags:
        if not isinstance(tag, str):
            continue
        clean_tag = tag.strip().lower()
        if not clean_tag or clean_tag in seen:
            continue
        normalized.append(clean_tag)
        seen.add(clean_tag)
        if len(normalized) == 8:
            break

    return normalized


def parse_ai_tags(content: str) -> list[str]:
    tags = json.loads(content)
    if not isinstance(tags, list):
        raise ValueError("OpenAI response is not a JSON array")

    normalized_tags = normalize_tags(tags)
    if len(normalized_tags) < 3:
        raise ValueError("OpenAI response contains fewer than 3 usable tags")

    return normalized_tags


def generate_ai_tags(file_name: str) -> list[str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")

    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    prompt = (
        "Analyse le nom de fichier suivant et genere entre 3 et 8 tags courts "
        "en francais.\n"
        f"Nom du fichier : {file_name}\n\n"
        "Retourne uniquement un tableau JSON de chaines."
    )

    response = requests.post(
        OPENAI_CHAT_COMPLETIONS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Tu es un assistant qui genere des tags documentaires. "
                        "Tu reponds uniquement avec du JSON valide."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 120,
        },
        timeout=20,
    )
    response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"].strip()
    return parse_ai_tags(content)


def generate_fallback_tags(file_name: str) -> list[str]:
    stem = PurePosixPath(file_name).stem.lower()
    extension = PurePosixPath(file_name).suffix.lstrip(".").lower()
    words = re.split(r"[^0-9A-Za-zÀ-ÖØ-öø-ÿ]+", stem)
    ignored_words = {
        "a",
        "au",
        "aux",
        "de",
        "des",
        "du",
        "en",
        "et",
        "la",
        "le",
        "les",
        "un",
        "une",
    }

    tags = normalize_tags(
        [
            word
            for word in words
            if len(word) >= 2 and word not in ignored_words
        ]
    )
    if extension:
        tags.append(extension)
    tags.extend(["document", "fichier", "cloud"])
    return normalize_tags(tags)[:8]


def generate_tags(file_name: str) -> list[str]:
    try:
        return generate_ai_tags(file_name)
    except Exception:
        logging.exception("OpenAI tag generation failed for file_name=%s", file_name)
        return generate_fallback_tags(file_name)


@service_bus_bp.function_name(name="ProcessDocument")
@service_bus_bp.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="docq",
    connection="docbus",
)
@service_bus_bp.generic_output_binding(
    arg_name="signalRMessages",
    type="signalR",
    hubName=HUB_NAME,
    connectionStringSetting="AzureSignalRConnectionString",
)
def process_document(msg: func.ServiceBusMessage, signalRMessages: func.Out[str]):
    raw_body = msg.get_body().decode("utf-8")
    logging.info("Service Bus message received: %s", raw_body)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logging.exception("Service Bus message is not valid JSON")
        raise

    job_id = payload.get("id") or payload.get("jobId")
    if not job_id:
        raise ValueError("Service Bus message must contain an 'id' or 'jobId' field")

    try:
        update_job(job_id, {"status": "PROCESSING"})
        logging.info("Job %s updated: status=PROCESSING", job_id)

        file_name = get_file_name(payload)
        tags = generate_tags(file_name)

        update_job(
            job_id,
            {
                "status": "PROCESSED",
                "tags": tags,
                "processedAt": now_iso(),
            },
        )
        logging.info("Job %s updated: status=PROCESSED tags=%s", job_id, tags)

        signalRMessages.set(
            serialize_signalr_messages(
                job_update_payload(job_id, "PROCESSING"),
                job_update_payload(job_id, "PROCESSED", tags=tags),
            )
        )
    except Exception:
        logging.exception("Service Bus processing failed for job_id=%s", job_id)
        try:
            update_job(job_id, {"status": "FAILED", "error": "Traitement en erreur."})
            signalRMessages.set(
                serialize_signalr_messages(
                    job_update_payload(
                        job_id,
                        "FAILED",
                        error="Traitement en erreur.",
                    )
                )
            )
        except Exception:
            logging.exception("Failed to publish FAILED status for job_id=%s", job_id)
        raise
