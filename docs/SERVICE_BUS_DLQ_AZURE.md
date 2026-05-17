# Service Bus, retries et Dead Letter Queue (DLQ)

Ce document explique la partie **§3, §4 et §6 de l’énoncé** : file d’attente, traitement asynchrone et gestion des erreurs.

---

## Rôle dans le projet

| Élément | Valeur |
|---------|--------|
| File Service Bus | `docq` |
| DLQ (sous-file morte) | `docq/$DeadLetterQueue` |
| Function consommatrice | `ProcessDocument` |
| Function DLQ | `ProcessDeadLetter` |
| Retries Azure | **3** livraisons max (`Max delivery count`) |
| Retries IA (dans une exécution) | **3** (`OPENAI_MAX_ATTEMPTS`) |

### Pourquoi une file ?

- **Découpler** l’upload (rapide) du traitement IA (plus lent)
- **Absorber la charge** si plusieurs fichiers arrivent en même temps
- **Réessayer** en cas d’échec temporaire
- **Isoler** les messages en échec définitif dans la **DLQ**

---

## Parcours d’un message (schéma simple)

```
BlobUpload
    → envoie un message JSON dans docq
         → ProcessDocument traite le message
              → succès : statut PROCESSED + SignalR
              → échec : message abandonné, nouvelle tentative
                   → après 3 échecs : message en DLQ
                        → ProcessDeadLetter : statut FAILED + SignalR
```

Contenu typique du message :

```json
{
  "id": "<job_id>",
  "blobName": "doc-storage/<job_id>/fichier.pdf",
  "size": 12345
}
```

---

## Cas qui provoquent une erreur puis la DLQ

| Cas (énoncé) | Dans le code | Effet |
|--------------|--------------|--------|
| Message mal formé | `MalformedMessageError` | JSON invalide ou `id` manquant |
| Document introuvable | `DocumentNotFoundError` | Job absent dans Cosmos ou blob absent |
| Échec répété de l’IA | `AiProcessingError` | 3 appels OpenAI échoués dans la même exécution |
| Exception non gérée | Remontée telle quelle | Toute autre erreur dans `ProcessDocument` |

À chaque échec, la Function **lève une exception** → Service Bus **réessaie** → après **3 livraisons**, le message part en **DLQ**.

La Function **`ProcessDeadLetter`** :

1. Lit le message en DLQ  
2. Met le job en **`FAILED`** dans Cosmos (équivalent de **`ERROR`** dans l’énoncé)  
3. Enregistre un message d’erreur (sans exposer de secrets)  
4. Notifie le frontend via **SignalR**

Fichiers utiles : `blob_upload.py`, `service_bus_processor.py`, `service_bus_dlq.py`, `service_bus_errors.py`

---

## Configuration Azure (portail)

### 1. File `docq` — nombre de tentatives

La DLQ est **toujours disponible** sur une file Service Bus : rien à « activer ».

1. Portail Azure → **Service Bus** → votre namespace → **Files d’attente** → **`docq`**
2. **Paramètres** / **Configuration**
3. **Nombre maximal de livraisons** (`Max delivery count`) : **`3`**
4. **Enregistrer**

Règle : quand `DeliveryCount` ≥ 3, le message va dans **`docq/$DeadLetterQueue`**.

### 2. Function App — variables d’application

Function App **`nasa-function-app`** → **Configuration** :

| Paramètre | Rôle |
|-----------|------|
| `docbus` | Connexion Service Bus (`docq` + DLQ) |
| `dockstorage` | Vérifier que le blob existe |
| `BLOB_CONTAINER` | `doc-storage` |
| `OPENAI_API_KEY` | Appels IA (secret, jamais côté front) |
| `OPENAI_MODEL` | ex. `gpt-4o-mini` |
| `OPENAI_MAX_ATTEMPTS` | `3` |
| `COSMOS_*` | Mise à jour des statuts job |
| `AzureSignalRConnectionString` | Notification `FAILED` |

Redéployer le worker après modification du code (workflow `main_nasa-function-app.yml` sur `main`).

### 3. Vérifier la DLQ

1. Service Bus → file **`docq`** → explorateur / Service Bus Explorer  
2. Ouvrir **`$DeadLetterQueue`**  
3. Après un test d’erreur : message présent + exécution de **`ProcessDeadLetter`** dans les logs

### 4. Identité managée (optionnel)

Avec une **chaîne de connexion** (`docbus`) : aucun réglage IAM en plus.

Sans clé : rôle **`Azure Service Bus Data Receiver`** sur le namespace pour lire `docq` et la DLQ.

---

## Deux niveaux de « 3 tentatives »

| Niveau | Paramètre | Où |
|--------|-----------|-----|
| OpenAI dans une exécution | `OPENAI_MAX_ATTEMPTS=3` | Function App |
| Nouvelle livraison du message | `Max delivery count=3` | File `docq` Azure |

Exemple : l’IA échoue 3 fois → la Function échoue → Service Bus réessaie jusqu’à 3 fois → puis DLQ.

> Avec le trigger Python classique, on ne peut pas envoyer un message **directement** en DLQ sans retry : toute exception déclenche des nouvelles tentatives jusqu’au max.

---

## Tester la DLQ (manuel)

| Test | Action | Résultat attendu |
|------|--------|------------------|
| JSON invalide | Envoyer `{pas-du-json` sur `docq` | DLQ après 3 livraisons |
| Job inconnu | `id` UUID inexistant + `blobName` fictif | DLQ |
| Blob manquant | `id` valide, `blobName` qui n’existe pas | DLQ |
| IA indisponible | Retirer ou invalider `OPENAI_API_KEY` | DLQ |

Ensuite : job en **`FAILED`**, notification SignalR, message visible dans **`$DeadLetterQueue`**.

---

## Dépannage rapide

| Problème | Piste de solution |
|----------|-------------------|
| Message bloqué en boucle | Vérifier `Max delivery count` sur `docq` |
| DLQ vide après erreur | Attendre 3 livraisons ; vérifier les logs `ProcessDocument` |
| `ProcessDeadLetter` ne part pas | `docbus` correct ; code déployé ; sous-file `$DeadLetterQueue` |
| Job reste `PROCESSING` | Erreur avant mise à jour ; vérifier DLQ + handler |
| Pas de notif front | SignalR : voir [SIGNALR_AZURE.md](SIGNALR_AZURE.md) |

---

## Résumé pour l’oral / le rapport

> « Après l’upload, le job est mis en file Service Bus. Une Function traite le document et génère les tags. Si le traitement échoue trois fois, le message part en dead letter queue ; une Function dédiée marque le job en erreur et prévient le frontend en temps réel. »

Voir aussi : [README.md](../README.md) · [SIGNALR_AZURE.md](SIGNALR_AZURE.md)
