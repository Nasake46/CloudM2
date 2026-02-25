from fastapi import FastAPI
from .routes_jobs import router as jobs_router

app = FastAPI(
    title="Doc Processing API", 
    description="API pour faire du traitement de documents avec Azure Cosmos DB", 
    version="1.0.0")

app.include_router(jobs_router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/echo")
def echo(req: dict):
    return req