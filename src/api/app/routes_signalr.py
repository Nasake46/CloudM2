import requests
from fastapi import APIRouter, HTTPException

from .config import settings

router = APIRouter(tags=["signalr"])


@router.post("/signalr/negotiate")
def signalr_negotiate():
    """Proxy vers la Function negotiate (evite CORS navigateur -> Function App)."""
    url = f"{settings.FUNCTIONS_BASE_URL.rstrip('/')}/api/negotiate"
    try:
        response = requests.post(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Echec de la negotiation SignalR: {exc}",
        ) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Reponse negotiate invalide (JSON attendu).",
        ) from exc
