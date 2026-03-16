import { FormEvent, useState } from "react";

type JobCreateResponse = {
  job_id: string;
  status: string;
  created_at: string;
  upload_url: string;
};

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

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
          </div>
        )}
      </section>
    </main>
  );
}
