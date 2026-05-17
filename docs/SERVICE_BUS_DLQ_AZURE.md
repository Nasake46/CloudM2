# Service Bus — file d'attente, retries et DLQ

Ce projet utilise la file **`docq`** et une Function **`ProcessDeadLetter`** branchée sur la sous-file morte **`docq/$DeadLetterQueue`**.

## Modifications à faire dans le portail Azure

La DLQ est **toujours active** sur une file Service Bus Standard/Premium : il n’y a pas de case à cocher. Ce qui compte, c’est le **nombre maximal de livraisons** (`Max delivery count`).

### 1. File `docq`

1. Portail Azure → **Service Bus** (votre namespace) → **Files d'attente** → **`docq`**
2. Onglet **Paramètres** (ou **Configuration** selon l’UI) :
   - **Nombre maximal de livraisons** (`Max delivery count`) : **`3`** (recommandé, aligné avec `OPENAI_MAX_ATTEMPTS`)
   - Conserver la file **activée**
3. **Enregistrer**

Comportement :

- À chaque échec de `ProcessDocument`, le message est **abandonné** et `DeliveryCount` augmente.
- Quand `DeliveryCount` ≥ `Max delivery count`, le message part automatiquement dans **`docq/$DeadLetterQueue`**.

### 2. Function App `nasa-function-app`

Dans **Configuration** → **Paramètres d'application**, vérifier :

| Paramètre | Rôle |
|-----------|------|
| `docbus` | Chaîne de connexion Service Bus (écoute `docq` + DLQ) |
| `dockstorage` | Storage pour vérifier l’existence du blob |
| `BLOB_CONTAINER` | `doc-storage` |
| `OPENAI_API_KEY` | Appels IA |
| `OPENAI_MODEL` | ex. `gpt-4o-mini` |
| `OPENAI_MAX_ATTEMPTS` | `3` (tentatives IA **dans** une exécution) |
| `COSMOS_*` | Mise à jour des jobs |

Redéployer la Function App après modification du code (`main` → workflow GitHub Actions).

### 3. Vérifier la DLQ (optionnel)

1. Service Bus → file **`docq`** → **Explorateur Service Bus** (ou Service Bus Explorer)
2. Ouvrir la sous-file **`$DeadLetterQueue`**
3. Après un scénario d’erreur, le message doit apparaître ici et **`ProcessDeadLetter`** doit s’exécuter (logs Application Insights / Flux de journaux).

### 4. Droits IAM (si connexion sans clé)

Si vous utilisez une identité managée au lieu de `docbus` :

- Rôle **`Azure Service Bus Data Receiver`** sur le namespace ou la file, pour lire `docq` et `docq/$DeadLetterQueue`.

Avec une **chaîne de connexion** (`docbus`), aucun changement IAM supplémentaire n’est nécessaire.

## Cartographie des erreurs → DLQ

| Cas | Comportement code | Vers DLQ |
|-----|-------------------|----------|
| Message mal formé (JSON, `id` manquant) | `MalformedMessageError` | Oui, après épuisement des livraisons |
| Document introuvable (Cosmos / blob) | `DocumentNotFoundError` | Oui |
| Échec répété OpenAI | `AiProcessingError` (3 tentatives locales) | Oui |
| Exception non gérée | Remontée telle quelle | Oui |

`ProcessDeadLetter` marque le job **`FAILED`** dans Cosmos, notifie SignalR et journalise la raison DLQ (`DeadLetterReason` / description).

## Paramètres non modifiables dans Azure

- Le **dead-letter immédiat** sans retry n’est pas disponible nativement avec le trigger Python classique : toute exception entraîne des **nouvelles tentatives** jusqu’au `Max delivery count`.
- Les tentatives IA **intra-fonction** sont pilotées par `OPENAI_MAX_ATTEMPTS` ; les tentatives **Service Bus** par `Max delivery count` sur la file.

## Tests manuels rapides

1. **JSON invalide** : envoyer `{not-json` sur `docq` → DLQ après 3 livraisons.
2. **Job inconnu** : message `{"id":"00000000-0000-0000-0000-000000000000","blobName":"doc-storage/x/y.pdf"}` → DLQ.
3. **Blob manquant** : `id` valide mais `blobName` inexistant → DLQ.
4. **OpenAI** : retirer ou invalider `OPENAI_API_KEY` → DLQ après échecs IA.
