# Notifications temps réel — Azure SignalR

Ce document explique la partie **§7 de l’énoncé** : informer le frontend à chaque étape du pipeline, sans recharger la page.

---

## Rôle dans le projet

| Élément | Valeur |
|---------|--------|
| Service Azure | **Azure SignalR** (mode **Serverless**) |
| Hub | `jobs` |
| Événement reçu par le front | `jobUpdated` |
| Payload | `{ jobId, status, tags?, error? }` |

### Statuts envoyés au frontend

| Statut | Quand |
|--------|--------|
| `UPLOADED` | Fichier reçu dans Blob Storage (`BlobUpload`) |
| `PROCESSING` | Début du traitement IA (`ProcessDocument`) |
| `PROCESSED` | Tags générés et enregistrés |
| `FAILED` | Erreur de traitement ou passage en DLQ |

Le front gère aussi `ERROR` pour rester compatible avec l’énoncé (`FAILED` = équivalent fonctionnel).

---

## Comment ça marche (schéma simple)

```
1. Le navigateur appelle l’API :  POST /signalr/negotiate
2. L’API appelle la Function :     POST /api/negotiate
3. La Function renvoie :           { url, accessToken }
4. Le navigateur ouvre un WebSocket vers Azure SignalR
5. Les Functions publient les mises à jour (binding SignalR)
6. Le front écoute jobUpdated et met à jour l’UI
```

**Pourquoi passer par l’API ?**  
Le navigateur n’appelle pas directement la Function App : cela évite les problèmes **CORS** entre Vercel / localhost et Azure Functions.

Fichiers utiles :

- Function : `signalr_negotiate.py` (`Negotiate`)
- API : `routes_signalr.py`
- Émission des messages : `signalr_messages.py` (utilisé par `BlobUpload`, `ProcessDocument`, `ProcessDeadLetter`)
- Client : `src/frontend/src/App.tsx`

---

## Configuration Azure (portail)

### Étape 1 — Créer SignalR

1. Portail Azure → **Créer une ressource** → **SignalR Service**
2. Même abonnement / groupe de ressources que la Function App
3. **Mode de service** : **Serverless** (obligatoire avec Azure Functions)
4. Après création : **Paramètres** → **Clés** → copier la **chaîne de connexion primaire**

### Étape 2 — Lier à la Function App

Function App **`nasa-function-app`** → **Paramètres** → **Variables d’application** :

| Nom | Valeur |
|-----|--------|
| `AzureSignalRConnectionString` | Chaîne de connexion SignalR (étape 1) |

Enregistrer et redémarrer si nécessaire.

### Étape 3 — Lier à l’API

Sur l’**App Service API** (ou fichier `.env` en local) :

| Nom | Valeur |
|-----|--------|
| `FUNCTIONS_BASE_URL` | URL de la Function App, ex. `https://nasa-function-app-....azurewebsites.net` |

L’API utilise cette URL pour proxyfier `POST /signalr/negotiate`.

### Étape 4 — Frontend (build)

| Nom | Valeur |
|-----|--------|
| `VITE_API_BASE_URL` | URL de l’API FastAPI (pas la Function App) |

Exemple production : `https://api-doc-nasa.azurewebsites.net`  
Le front appelle uniquement `{VITE_API_BASE_URL}/signalr/negotiate`.

### Étape 5 — CORS de l’API

L’origine du front doit être autorisée dans `main.py` (`allow_origins`), par ex. :

- `https://cloud-m2-bice.vercel.app`
- `http://localhost:5173` (dev)

---

## Développement local

1. Copier `src/fonctions/worker/local.settings.json.example` → `local.settings.json`  
   (y mettre `AzureSignalRConnectionString`)
2. Démarrer les Functions : `func start` dans `src/fonctions/worker`
3. Démarrer l’API : uvicorn sur `src/api` avec `FUNCTIONS_BASE_URL=http://localhost:7071`
4. Démarrer le front : `npm run dev` dans `src/frontend` avec `VITE_API_BASE_URL=http://localhost:8000`

Le front appelle l’**API** (`/signalr/negotiate`), pas `localhost:7071` directement.

---

## Vérifier que tout fonctionne

1. **Negotiate**  
   `POST https://<votre-api>/signalr/negotiate`  
   → JSON avec `url` et `accessToken`

2. **Pipeline complet**  
   - Créer un job et uploader un fichier sur le front  
   - Voir les statuts évoluer : `UPLOADED` → `PROCESSING` → `PROCESSED`  
   - Toast avec les tags, sans rafraîchir la page

3. **Logs Function App**  
   Pas d’erreur SignalR sur `BlobUpload` ou `ProcessDocument`

---

## Dépannage rapide

| Problème | Piste de solution |
|----------|-------------------|
| `Connexion SignalR impossible` | Vérifier `AzureSignalRConnectionString` et mode **Serverless** |
| 502 sur `/signalr/negotiate` | Vérifier `FUNCTIONS_BASE_URL` et que `Negotiate` est déployée |
| Pas de mise à jour après upload | Logs `ProcessDocument` ; hub `jobs` ; événement `jobUpdated` |
| CORS en local | `VITE_API_BASE_URL` doit pointer vers l’API (8000), pas vers 7071 |
| Pas de toast en prod | CORS API : origine Vercel dans `allow_origins` |

---

## Résumé pour l’oral / le rapport

> « À chaque changement d’état du job, les Azure Functions envoient un message SignalR. Le frontend ouvre une connexion WebSocket après négociation via notre API, et met à jour l’interface dès réception de `jobUpdated`. »

Voir aussi : [README.md](../README.md) · [SERVICE_BUS_DLQ_AZURE.md](SERVICE_BUS_DLQ_AZURE.md)
