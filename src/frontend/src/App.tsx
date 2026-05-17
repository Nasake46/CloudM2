import { FormEvent, useEffect, useState } from "react";
import * as signalR from "@microsoft/signalr";

type JobCreateResponse = {
  job_id: string;
  status: string;
  created_at: string;
  upload_url: string;
};

type JobUpdatedMessage = {
  jobId: string;
  status: string;
  tags?: string[];
  error?: string;
};

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

const FUNCTIONS_BASE_URL =
  import.meta.env.VITE_FUNCTIONS_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:7071";

const SIGNALR_WAIT_MS = 10 * 60 * 1000;

function createJobHubConnection(): signalR.HubConnection {
  return new signalR.HubConnectionBuilder()
    .withUrl(`${FUNCTIONS_BASE_URL}/api`, {
      accessTokenFactory: async () => {
        const response = await fetch(`${FUNCTIONS_BASE_URL}/api/negotiate`, {
          method: "POST"
        });
        if (!response.ok) {
          throw new Error("Negotiation SignalR echouee.");
        }
        const data = (await response.json()) as { accessToken: string };
        return data.accessToken;
      }
    })
    .withAutomaticReconnect()
    .configureLogging(signalR.LogLevel.Warning)
    .build();
}

async function createJob(file: File): Promise<JobCreateResponse> {
  const response = await fetch(`${API_BASE_URL}/jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      fileName: file.name,
      contentType: file.type || "application/octet-stream"
    })
  });

  if (!response.ok) {
    throw new Error("La creation du job a echoue.");
  }

  return response.json();
}

async function uploadToBlob(uploadUrl: string, file: File): Promise<void> {
  const response = await fetch(uploadUrl, {
    method: "PUT",
    headers: {
      "x-ms-blob-type": "BlockBlob",
      "Content-Type": file.type || "application/octet-stream"
    },
    body: file
  });

  if (!response.ok) {
    throw new Error("L'upload vers Azure Blob a echoue.");
  }
}

export default function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<JobCreateResponse | null>(null);
  const [toast, setToast] = useState<{ title: string; tags: string[] } | null>(null);
  const [toastError, setToastError] = useState<string | null>(null);
  const [isWaitingProcessed, setIsWaitingProcessed] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!success?.job_id) {
      return;
    }

    const jobId = success.job_id;
    setToast(null);
    setToastError(null);
    setIsWaitingProcessed(true);
    setPipelineStatus("Connexion SignalR…");

    let cancelled = false;
    const connection = createJobHubConnection();

    const timeoutId = window.setTimeout(() => {
      if (!cancelled) {
        setToastError("Delai depasse en attendant la fin du traitement.");
        setIsWaitingProcessed(false);
        void connection.stop();
      }
    }, SIGNALR_WAIT_MS);

    const handleJobUpdated = (payload: JobUpdatedMessage) => {
      if (cancelled || payload.jobId !== jobId) {
        return;
      }

      setPipelineStatus(payload.status);

      if (payload.status === "PROCESSED") {
        setToast({
          title: "Document traite",
          tags: Array.isArray(payload.tags) ? payload.tags : []
        });
        setIsWaitingProcessed(false);
        window.clearTimeout(timeoutId);
        void connection.stop();
        return;
      }

      if (payload.status === "ERROR" || payload.status === "FAILED") {
        setToastError(
          typeof payload.error === "string" ? payload.error : "Traitement en erreur."
        );
        setIsWaitingProcessed(false);
        window.clearTimeout(timeoutId);
        void connection.stop();
      }
    };

    connection.on("jobUpdated", handleJobUpdated);

    void (async () => {
      try {
        await connection.start();
        if (!cancelled) {
          setPipelineStatus("En attente du traitement…");
        }
      } catch (connectionError) {
        if (cancelled) {
          return;
        }
        setToastError(
          connectionError instanceof Error
            ? connectionError.message
            : "Connexion SignalR impossible."
        );
        setIsWaitingProcessed(false);
        window.clearTimeout(timeoutId);
      }
    })();

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
      connection.off("jobUpdated", handleJobUpdated);
      void connection.stop();
    };
  }, [success?.job_id]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedFile) {
      setError("Selectionne un fichier avant de lancer l'upload.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setSuccess(null);
    setPipelineStatus(null);

    try {
      const job = await createJob(selectedFile);
      await uploadToBlob(job.upload_url, selectedFile);
      setSuccess(job);
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Une erreur inconnue est survenue."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="page-shell">
      <section className="upload-panel">
        <p className="eyebrow">CloudM2</p>
        <h1>Uploader un document vers Azure Blob</h1>
        <p className="intro">
          Le front cree un job via l&apos;API, uploade le fichier vers Blob, puis recoit les
          mises a jour en temps reel via Azure SignalR (hub <code>jobs</code>).
        </p>

        <form className="upload-form" onSubmit={handleSubmit}>
          <label className="file-field" htmlFor="file">
            <span>Document</span>
            <input
              id="file"
              type="file"
              onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
            />
          </label>

          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Upload en cours..." : "Creer le job et uploader"}
          </button>
        </form>

        {selectedFile && (
          <div className="info-card">
            <strong>Fichier selectionne</strong>
            <span>{selectedFile.name}</span>
            <span>{selectedFile.type || "application/octet-stream"}</span>
            <span>{Math.round(selectedFile.size / 1024)} KB</span>
          </div>
        )}

        {error && <p className="status error">{error}</p>}

        {success && (
          <div className="status success">
            <p>Upload termine.</p>
            <p>Job ID: {success.job_id}</p>
            <p>Statut initial: {success.status}</p>
            <p>Cree le: {new Date(success.created_at).toLocaleString("fr-FR")}</p>
            {isWaitingProcessed && (
              <p className="processing-hint">
                Traitement du document en cours…
                {pipelineStatus ? ` (${pipelineStatus})` : ""}
              </p>
            )}
          </div>
        )}
      </section>

      {toast && (
        <div className="toast toast-success" role="status" aria-live="polite">
          <div className="toast-header">
            <strong>{toast.title}</strong>
            <button type="button" className="toast-close" onClick={() => setToast(null)}>
              Fermer
            </button>
          </div>
          <p className="toast-tags-label">Tags du document</p>
          {toast.tags.length === 0 ? (
            <p className="toast-tags-empty">Aucun tag associe.</p>
          ) : (
            <ul className="toast-tags">
              {toast.tags.map((tag) => (
                <li key={tag}>{tag}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {toastError && (
        <div className="toast toast-error" role="alert">
          <p>{toastError}</p>
          <button type="button" className="toast-close" onClick={() => setToastError(null)}>
            Fermer
          </button>
        </div>
      )}
    </main>
  );
}
