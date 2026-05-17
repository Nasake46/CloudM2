import json
import logging
import os
import re
from pathlib import PurePosixPath

import azure.functions as func
import requests
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from blob_storage import blob_exists
from cosmos_jobs import get_job, now_iso, update_job
from service_bus_errors import (
    AiProcessingError,
    DocumentNotFoundError,
    MalformedMessageError,
)
from service_bus_security import public_error_message
from signalr_messages import HUB_NAME, job_update_payload, serialize_signalr_messages

service_bus_bp = func.Blueprint()

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
OPENAI_MAX_ATTEMPTS = int(os.getenv("OPENAI_MAX_ATTEMPTS", "3"))


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

    last_error: Exception | None = None
    for attempt in range(1, OPENAI_MAX_ATTEMPTS + 1):
        try:
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
        except Exception as exc:
            last_error = exc
            logging.warning(
                "OpenAI attempt %s/%s failed for file_name=%s",
                attempt,
                OPENAI_MAX_ATTEMPTS,
                file_name,
            )

    raise AiProcessingError(
        f"Échec répété de l'appel IA après {OPENAI_MAX_ATTEMPTS} tentatives."
    ) from None


def parse_queue_message(raw_body: str) -> tuple[dict, str]:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise MalformedMessageError("Le message Service Bus n'est pas du JSON valide.") from exc

    if not isinstance(payload, dict):
        raise MalformedMessageError("Le corps du message doit être un objet JSON.")

    job_id = payload.get("id") or payload.get("jobId")
    if not isinstance(job_id, str) or not job_id.strip():
        raise MalformedMessageError("Le message doit contenir un champ 'id' ou 'jobId'.")

    return payload, job_id.strip()


def ensure_document_exists(payload: dict, job_id: str) -> None:
    try:
        get_job(job_id)
    except CosmosResourceNotFoundError as exc:
        raise DocumentNotFoundError(f"Job Cosmos introuvable : {job_id}") from exc

    blob_name = payload.get("blobName")
    if not isinstance(blob_name, str) or not blob_name.strip():
        raise DocumentNotFoundError("Le message ne contient pas de 'blobName' valide.")

    if not blob_exists(blob_name.strip()):
        raise DocumentNotFoundError(f"Blob introuvable : {blob_name.strip()}")


def publish_processing_failure(
    job_id: str,
    error_message: str,
    signalRMessages: func.Out[str],
) -> None:
    update_job(job_id, {"status": "FAILED", "error": error_message})
    signalRMessages.set(
        serialize_signalr_messages(
            job_update_payload(job_id, "FAILED", error=error_message)
        )
    )


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
    delivery_count = getattr(msg, "delivery_count", None)
    logging.info(
        "Service Bus message received delivery_count=%s body=%s",
        delivery_count,
        raw_body,
    )

    payload, job_id = parse_queue_message(raw_body)

    try:
        ensure_document_exists(payload, job_id)

        update_job(job_id, {"status": "PROCESSING"})
        logging.info("Job %s updated: status=PROCESSING", job_id)

        file_name = get_file_name(payload)
        tags = generate_ai_tags(file_name)

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
    except Exception as exc:
        error_message = public_error_message(exc)
        logging.error(
            "Service Bus processing failed for job_id=%s error_type=%s",
            job_id,
            type(exc).__name__,
        )
        try:
            publish_processing_failure(job_id, error_message, signalRMessages)
        except Exception:
            logging.exception("Failed to publish FAILED status for job_id=%s", job_id)
        raise
