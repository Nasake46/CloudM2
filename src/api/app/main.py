from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes_jobs import router as jobs_router

app = FastAPI(
    title="Doc Processing API", 
    description="API pour faire du traitement de documents avec Azure Cosmos DB", 
    version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://front-doc-nasa-axatcrgwhngjgrdc.francecentral-01.azurewebsites.net"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/echo")
def echo(req: dict):
    return req
