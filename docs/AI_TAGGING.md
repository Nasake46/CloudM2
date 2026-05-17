# Azure + OpenAI — Tagging IA des documents

Ce guide décrit la configuration du tagging IA basé sur OpenAI pour l'analyse automatique des documents uploadés.

## 1. Créer une clé API OpenAI

1. Aller sur **https://platform.openai.com** → **API keys**.
2. **Create new secret key** (Org ou User).
3. **Copier la clé** (elle ne s'affichera qu'une fois) → format : `sk-...`.
4. La **stocker de manière sécurisée** (voir section Sécurité en production).

## 2. Lier OpenAI à l'API

Ajouter la clé dans les **variables d'environnement** de l'API (App Service ou `.env` local) :

| Nom | Valeur |
|-----|--------|
| `OPENAI_API_KEY` | `sk-...` (clé secrète OpenAI) |
| `OPENAI_MODEL` | `gpt-4o-mini` (ou autre modèle disponible) |

L'API l'utilise dans `app/routes_jobs.py` pour extraire les tags depuis le contenu du document.

## 3. Lier OpenAI au Worker (Function App)

Le **Function App** peut aussi appeler OpenAI pour affiner les tags avant envoi au front.

Ajouter dans **Paramètres** → **Variables d'environnement** :

| Nom | Valeur |
|-----|--------|
| `OPENAI_API_KEY` | `sk-...` (même clé ou dédiée) |
| `OPENAI_MODEL` | `gpt-4o-mini` |

Ou configurer dans `local.settings.json` pour le dev local.

## 4. Intégration dans le pipeline

Le tagging IA se déclenche après l'upload du document :

1. **Front upload** → Blob Storage
2. **Trigger BlobUpload** → `src/fonctions/worker/blob_upload.py`
3. **Cosmos jobs** → Job statut = `processing`
4. **ProcessDocument** (Worker) → Appelle OpenAI via l'API ou directement
5. **Tags extraits** → Envoyés au front via **SignalR** (`jobUpdated`)

```
Front --upload--> Blob --> BlobUpload trigger --> ProcessDocument
                                                         |
                                         Appel OpenAI (tagging)
                                                         |
                                    Tags --> SignalR --> Front (toast)
```

## 5. Modèle de prompt

Le Worker envoie le contenu du document à OpenAI avec un prompt structuré :

```python
prompt = f"""
Analysez ce document et extrayez 3 à 5 tags pertinents.
Retournez un JSON avec la clé "tags" contenant une liste de chaînes.

Document :
{document_content}

Réponse JSON:
"""
```

Exemple de réponse attendue :
```json
{
  "tags": ["facturation", "client", "Q1-2026"]
}
```

## 6. Variables du front (build)

Aucune clé OpenAI n'est exposée au front — le tagging se fait côté serveur uniquement.

Seule `VITE_API_BASE_URL` est requise pour que l'API reçoive les appels.

## 7. Coûts et quotas

OpenAI facture par **tokens consommés** :
- `gpt-4o-mini` : moins cher que `gpt-4-turbo`
- Input tokens : coût faible
- Chaque document taggé = ~200-500 tokens (estimation)

Surveiller l'usage sur **https://platform.openai.com/usage/overview**.

## 8. Vérifications

1. L'API démarre sans erreur : `python -c "import openai; print(openai.__version__)"`
2. Clé valide : 
   ```bash
   curl -H "Authorization: Bearer sk-..." \
     https://api.openai.com/v1/models | grep gpt-4o-mini
   ```
3. Upload un document depuis le front → Toast avec tags après ~10-30s.
4. Logs API contiennent : `"Tagging with OpenAI"` sans erreur 401/403.
5. Cosmos Jobs enregistre les tags dans le champ `tags[]`.

## 9. Développement local

1. Copier `.env.example` ou créer `.env` à la racine de `src/api/` :
   ```
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4o-mini
   ```

2. La FastAPI l'utilise via `app/config.py` (ou `os.getenv`).

3. Demarrer l'API : `python -m uvicorn app.main:app --reload` dans `src/api/`

4. Upload un fichier depuis le front → voir tags en retour SignalR.

## 10. Déploiement Azure

**App Service (API)** :
1. **Configuration** → **Paramètres d'application**.
2. Ajouter `OPENAI_API_KEY` et `OPENAI_MODEL`.
3. Redémarrer l'app.

**Function App (Worker)** :
1. **Paramètres** → **Variables d'environnement**.
2. Ajouter `OPENAI_API_KEY` et `OPENAI_MODEL`.
3. Redéployer ou redémarrer.

**Keyvault (optionnel, recommandé)** :
- Stocker la clé dans **Azure Key Vault** au lieu du plain text.
- L'API la récupère via l'identité managée.

## 11. Dépannage

| Symptôme | Cause probable | Solution |
|----------|----------------|----------|
| 401 Unauthorized sur OpenAI | Clé invalide ou expirée | Vérifier la clé sur platform.openai.com |
| 429 Too Many Requests | Quota atteint | Réduire la fréquence ou upgrader le plan OpenAI |
| Tags vides dans Cosmos | Prompt mal formé ou réponse non-JSON | Vérifier les logs Worker |
| Pas de toast après upload | SignalR non lié ou tagging échoué | Vérifier les logs API et Worker ; relancer SignalR |
| `OPENAI_API_KEY not found` | Variable d'environnement manquante | Redéployer ou redémarrer l'app |
| Délai long de tagging (>1 min) | Modèle surchargé ou timeout | Augmenter le timeout Function App ou utiliser `gpt-3.5-turbo` |

## 12. Sécurité en production

- **Jamais** mettre la clé en dur dans le code ou Git.
- **Azure Key Vault** : stocker `OPENAI_API_KEY` en secret (accès via identité managée).
- **Audit** : vérifier les logs Azure pour déterminer qui accède à la clé.
- **Rotation** : générer une nouvelle clé régulièrement et supprimer les anciennes sur OpenAI.
- **Quota API** : limiter la consommation de tokens via le dashboard OpenAI.
