class ProcessingError(Exception):
    """Erreur métier : abandon du message et retries Service Bus jusqu'à la DLQ."""


class MalformedMessageError(ProcessingError):
    """JSON invalide ou champs obligatoires manquants."""


class DocumentNotFoundError(ProcessingError):
    """Job Cosmos ou blob Storage introuvable."""


class AiProcessingError(ProcessingError):
    """Échec de l'appel OpenAI (après épuisement des tentatives côté code)."""
