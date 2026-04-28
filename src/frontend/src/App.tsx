import { FormEvent, useEffect, useRef, useState } from "react";

type JobCreateResponse = {
  job_id: string;
  status: string;
  created_at: string;
  upload_url: string;
};

type JobDetail = {
  id: string;
  status: string;
  tags?: string[];
  fileName?: string;
  error?: string | null;
};

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_MS = 10 * 60 * 1000;

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

async function fetchJob(jobId: string): Promise<JobDetail> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`);
  if (!response.ok) {
    throw new Error("Impossible de recuperer le statut du job.");
  }
  return response.json();
}

async function pollUntilProcessed(jobId: string, signal: AbortSignal): Promise<JobDetail> {
  const deadline = Date.now() + POLL_MAX_MS;
  while (Date.now() < deadline) {
    if (signal.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    const job = await fetchJob(jobId);
    if (job.status === "PROCESSED") {
      return job;
    }
    if (job.status === "ERROR" || job.status === "FAILED") {
      throw new Error(typeof job.error === "string" ? job.error : "Traitement en erreur.");
    }
    await new Promise<void>((resolve) => {
      const t = setTimeout(resolve, POLL_INTERVAL_MS);
      signal.addEventListener("abort", () => clearTimeout(t), { once: true });
    });
  }
  throw new Error("Delai depasse en attendant la fin du traitement.");
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
  const pollAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => pollAbortRef.current?.abort();
  }, []);

  useEffect(() => {
    if (!success?.job_id) {
      return;
    }

    setToast(null);
    setToastError(null);
    setIsWaitingProcessed(true);
    pollAbortRef.current?.abort();
    const controller = new AbortController();
    pollAbortRef.current = controller;

    let cancelled = false;

    (async () => {
      try {
        const job = await pollUntilProcessed(success.job_id, controller.signal);
        if (cancelled) return;
        setToast({
          title: "Document traite",
          tags: Array.isArray(job.tags) ? job.tags : []
        });
      } catch (e) {
        if (cancelled || (e instanceof DOMException && e.name === "AbortError")) return;
        setToastError(e instanceof Error ? e.message : "Echec du suivi du traitement.");
      } finally {
        if (!cancelled) setIsWaitingProcessed(false);
      }
    })();

    return () => {
      cancelled = true;
      controller.abort();
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
          Le front cree un job via l&apos;API, recupere une URL SAS puis envoie le fichier
          directement dans le conteneur Blob.
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
              <p className="processing-hint">Traitement du document en cours…</p>
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
