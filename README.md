# CloudM2 — Pipeline de traitement de documents Azure

Projet réalisé dans le cadre du cours **Cloud** (Ynov M2).

L’utilisateur envoie un fichier via une interface web. Le système détecte l’upload, génère des tags par IA, et met à jour l’interface **en temps réel** à chaque étape.

**Frontend déployé :** https://cloud-m2-bice.vercel.app/

---

## 1. Upload du fichier

- **Frontend** : React + Vite (`src/frontend/`).
- L’utilisateur choisit un fichier et crée un job.
- **API** FastAPI (`src/api/`) : `POST /jobs` crée le job dans **Cosmos DB** (statut `CREATED`) et renvoie une **URL SAS** (15 min).
- Le navigateur envoie le fichier **directement** vers **Azure Blob Storage** (pas de passage par l’API pour le binaire).

Fichiers concernés : `routes_jobs.py`, `blob_service.py`, `App.tsx`.

---

## 2. Détection automatique du fichier

Dès que le blob arrive dans le conteneur `doc-storage` :

- La Function **`BlobUpload`** se déclenche (`blob_upload.py`).
- Le statut Cosmos passe à **`UPLOADED`**.
- Une notification **SignalR** est envoyée au frontend (`jobUpdated`).
- Un message JSON est publié dans la file Service Bus **`docq`**.

> L’énoncé mentionne un statut `QUEUED` : ici la mise en file est **immédiate** après l’upload ; le statut affiché reste `UPLOADED` jusqu’au début du traitement (`PROCESSING`).

---

## 3. Mise en file d’attente

- File Azure Service Bus : **`docq`**.
- Rôle : découpler l’upload du traitement, absorber la charge, permettre les **retries** et la **DLQ**.

Configuration Azure : voir [docs/SERVICE_BUS_DLQ_AZURE.md](docs/SERVICE_BUS_DLQ_AZURE.md) (`Max delivery count` = 3).

---

## 4. Traitement du document

La Function **`ProcessDocument`** (`service_bus_processor.py`) consomme `docq` :

1. Valide le message (JSON, `id`, blob existant, job Cosmos).
2. Passe le statut à **`PROCESSING`** + notification SignalR.
3. Appelle **OpenAI** (`gpt-4o-mini` par défaut) sur le **nom du fichier**.
4. Génère **3 à 8 tags** en français.

La clé `OPENAI_API_KEY` reste **uniquement** dans la Function App (jamais exposée au front).

---

## 5. Résultat final

- Statut Cosmos : **`PROCESSED`**.
- Tags enregistrés sur le document job.
- Le frontend reçoit `jobUpdated` avec la liste des tags (toast « Document traité »).

---

## 6. Gestion des erreurs

En cas d’échec, le message est **réessayé** puis envoyé en **Dead Letter Queue** (`docq/$DeadLetterQueue`).

| Cas | Comportement |
|-----|----------------|
| Message mal formé | Exception → retries → DLQ |
| Job ou blob introuvable | `DocumentNotFoundError` → DLQ |
| 3 échecs OpenAI d’affilée | `AiProcessingError` → DLQ |
| Exception non gérée | Remontée → DLQ |

La Function **`ProcessDeadLetter`** (`service_bus_dlq.py`) :

- Lit la DLQ ;
- Met le job en **`FAILED`** (équivalent fonctionnel de `ERROR` dans l’énoncé) ;
- Enregistre un message d’erreur (sanitisé, sans fuite de secrets) ;
- Notifie le frontend via SignalR.

Détails : [docs/SERVICE_BUS_DLQ_AZURE.md](docs/SERVICE_BUS_DLQ_AZURE.md).

---

## 7. Notifications temps réel

**Azure SignalR** — hub `jobs`, événement `jobUpdated`.

Statuts notifiés au frontend :

| Statut | Moment |
|--------|--------|
| `UPLOADED` | Blob reçu |
| `PROCESSING` | Début du traitement IA |
| `PROCESSED` | Tags disponibles |
| `FAILED` | Erreur (traitement ou DLQ) |

Le front écoute aussi `ERROR` pour compatibilité avec l’énoncé.

Négociation SignalR : `POST /signalr/negotiate` sur l’API — voir [docs/SIGNALR_AZURE.md](docs/SIGNALR_AZURE.md).

---

## Flux des statuts

```
CREATED → UPLOADED → PROCESSING → PROCESSED
                └─ (erreur) → FAILED
```

(`CREATED` : à la création du job par l’API ; le fichier n’est pas encore dans le storage.)

---

## Services Azure utilisés

| Service | Rôle |
|---------|------|
| **Blob Storage** | Fichiers uploadés (`doc-storage`) |
| **Cosmos DB** | État des jobs (NoSQL) |
| **Service Bus** | File `docq` + DLQ |
| **Functions** | `BlobUpload`, `ProcessDocument`, `ProcessDeadLetter`, negotiate SignalR |
| **SignalR** | WebSocket vers le frontend |
| **App Service** | API FastAPI (Docker) |
| **Vercel** | Frontend React (à la place de Static Web Apps / Next.js de l’énoncé) |

---

## Structure du projet

```
CloudM2/
├── src/
│   ├── api/app/              # FastAPI
│   │   ├── main.py
│   │   ├── routes_jobs.py
│   │   ├── routes_signalr.py
│   │   ├── models.py
│   │   ├── cosmos.py
│   │   ├── blob_service.py
│   │   └── config.py
│   ├── fonctions/worker/     # Azure Functions (Python v2)
│   │   ├── function_app.py
│   │   ├── blob_upload.py
│   │   ├── service_bus_processor.py
│   │   ├── service_bus_dlq.py
│   │   ├── signalr_negotiate.py
│   │   └── host.json
│   └── frontend/             # React + Vite
│       └── src/App.tsx
├── docs/
│   ├── SIGNALR_AZURE.md
│   └── SERVICE_BUS_DLQ_AZURE.md
├── .github/workflows/        # CI/CD
└── TP.md                     # Énoncé du TP
```

---

## Prérequis

- Compte Azure actif  
- Python 3.12+  
- Node.js 18+  
- Docker (API en local)  
- Azure Functions Core Tools (tests worker en local)

---

## Variables d’environnement

### Function App (`nasa-function-app`)

| Variable | Description |
|----------|-------------|
| `dockstorage` | Chaîne de connexion Blob Storage |
| `docbus` | Chaîne de connexion Service Bus |
| `AzureSignalRConnectionString` | SignalR |
| `COSMOS_ENDPOINT` / `COSMOS_KEY` | Cosmos DB |
| `COSMOS_DATABASE` / `COSMOS_CONTAINER` | Base et conteneur |
| `BLOB_CONTAINER` | `doc-storage` |
| `OPENAI_API_KEY` | Clé API OpenAI (secrète) |
| `OPENAI_MODEL` | ex. `gpt-4o-mini` |
| `OPENAI_MAX_ATTEMPTS` | `3` |

Modèle local : copier `src/fonctions/worker/local.settings.json.example` → `local.settings.json` (fichier ignoré par Git).

### API FastAPI

| Variable | Description |
|----------|-------------|
| `COSMOS_*` | Cosmos DB |
| `BLOB_CONNECTION_STRING` | Storage |
| `BLOB_CONTAINER` | Conteneur blob |
| `FUNCTIONS_BASE_URL` | URL de la Function App (negotiate SignalR) |

### Frontend

| Variable | Description |
|----------|-------------|
| `VITE_API_BASE_URL` | URL de l’API (ex. App Service) |

---

## Déploiement (GitHub Actions)

| Workflow | Cible |
|----------|--------|
| `main_nasa-function-app.yml` | Function App Python |
| `api-build-push.yml` | API Docker → App Service |
| `frontend-build-push.yml` | Image frontend (registry) |

Déploiement frontend public : **Vercel** (hors workflows Azure Static Web Apps de l’énoncé).

---

## Tester le pipeline

1. Ouvrir le frontend déployé.  
2. Saisir un nom de fichier et sélectionner un PDF (ou autre).  
3. Créer le job et laisser l’upload se faire.  
4. Observer les mises à jour SignalR :  
   - **UPLOADED** — blob reçu  
   - **PROCESSING** — IA en cours  
   - **PROCESSED** — tags affichés  

---

## Tester la Dead Letter Queue

1. Dans Azure, vérifier `Max delivery count` = **3** sur la file `docq`.  
2. Provoquer une erreur (ex. message invalide, blob inexistant, `OPENAI_API_KEY` absente).  
3. Après 3 tentatives, le message part en **DLQ**.  
4. **`ProcessDeadLetter`** passe le job en **FAILED** et notifie le front.

Scénarios détaillés : [docs/SERVICE_BUS_DLQ_AZURE.md](docs/SERVICE_BUS_DLQ_AZURE.md).

---

## Points techniques

**Upload SAS** — Le fichier ne transite pas par l’API : URL signée 15 minutes, upload direct navigateur → Blob.

**OpenAI** — Appel depuis la Function uniquement ; messages d’erreur filtrés (`service_bus_security.py`) pour ne pas exposer la clé dans Cosmos, SignalR ou les logs.

**SignalR** — Binding `signalR` côté Functions pour l’émission ; négociation via l’API (`routes_signalr.py`) pour le client web.

**DLQ** — Retries Service Bus + handler dédié ; pas de fallback silencieux sur l’IA (un échec IA compte comme erreur).

---

## Documentation complémentaire

- [SignalR sur Azure](docs/SIGNALR_AZURE.md)  
- [Service Bus et DLQ](docs/SERVICE_BUS_DLQ_AZURE.md)  
- [Tagging IA](docs/AI_TAGGING.md)
