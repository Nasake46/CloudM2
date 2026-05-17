# Azure SignalR — configuration portail

Ce guide décrit les actions à faire **dans Azure** après déploiement du code SignalR du repo.

## 1. Créer Azure SignalR Service

1. Portail Azure → **Créer une ressource** → **SignalR Service**.
2. Choisir le même abonnement / groupe de ressources que le Function App `nasa-function-app`.
3. **Mode de service** : **Serverless** (obligatoire avec Azure Functions).
4. Créer la ressource, puis **Paramètres** → **Clés** → copier la **Chaîne de connexion primaire**.

## 2. Lier SignalR au Function App

1. Ouvrir **nasa-function-app** (Function App).
2. **Paramètres** → **Variables d’environnement** (ou Configuration → Application settings).
3. Ajouter :

| Nom | Valeur |
|-----|--------|
| `AzureSignalRConnectionString` | Chaîne de connexion SignalR (étape 1) |

4. **Enregistrer** et redémarrer l’app si demandé.

## 3. CORS sur le Function App

Le front appelle `POST /api/negotiate` sur le Function App.

1. Function App → **Paramètres** → **CORS**.
2. Origines autorisées :
   - `http://localhost:5173`
   - `http://127.0.0.1:5173`
   - URL du front déployé (ex. `https://front-doc-nasa-....azurewebsites.net`)
3. Désactiver « Credentials » sauf besoin explicite (le front n’envoie pas de cookies).

## 4. Variables du front (build)

Lors du build Docker / CI, définir :

| Variable | Exemple |
|----------|---------|
| `VITE_API_BASE_URL` | `https://api-doc-nasa.azurewebsites.net` |
| `VITE_FUNCTIONS_BASE_URL` | `https://nasa-function-app.azurewebsites.net` |

En local, copier `src/frontend/.env.example` vers `.env` et adapter les URLs.

Secret GitHub Actions suggéré : `FRONTEND_FUNCTIONS_BASE_URL` (à ajouter au workflow comme pour l’API).

## 5. Vérifications

1. `POST https://<function-app>.azurewebsites.net/api/negotiate`  
   → réponse JSON avec `url` et `accessToken`.
2. Uploader un document depuis le front.
3. Dans les logs Function App : `Negotiate`, `BlobUpload`, `ProcessDocument` sans erreur SignalR.
4. Toast avec tags après traitement, sans polling.

## 6. Developpement local (CORS)

Le front Vite (`localhost:5173`) ne doit **pas** appeler directement `http://localhost:7071` (CORS bloque).

**Solution dans le repo** : proxy Vite (`vite.config.ts`) redirige `/api` vers `localhost:7071`. En mode `npm run dev`, les appels passent par `/api/negotiate` (meme origine).

1. Demarrer les Functions : `func start` dans `src/fonctions/worker`
2. Demarrer le front : `npm run dev` dans `src/frontend`
3. Copier `local.settings.json.example` vers `local.settings.json` (CORS + `AzureSignalRConnectionString`)

Si vous testez sans proxy, ajoutez CORS dans `host.json` ou `local.settings.json` sous `Host.CORS`.

## 7. Depannage

| Symptome | Cause probable |
|----------|----------------|
| Erreur CORS sur negotiate (local) | Front appele 7071 directement ; relancer `npm run dev` (proxy) ou configurer CORS |
| Erreur CORS sur negotiate (Azure) | Origine front absente du CORS Function App |
| `Connexion SignalR impossible` | `AzureSignalRConnectionString` manquante ou mode SignalR != Serverless |
| URL Functions sans `https://` | Corriger `VITE_FUNCTIONS_BASE_URL=https://...` |
| Pas de toast après upload | Binding SignalR ou hub `jobs` ; vérifier logs `ProcessDocument` |
| 404 sur `/api/negotiate` | Function `Negotiate` non déployée ; redéployer le worker |

## Architecture

```
Front --POST /api/negotiate--> Function App --token--> Azure SignalR
Front <--WebSocket jobUpdated-- Azure SignalR <--binding-- Worker (BlobUpload, ProcessDocument)
```

Hub SignalR : `jobs`  
Événement client : `jobUpdated`  
Payload : `{ jobId, status, tags?, error? }`
