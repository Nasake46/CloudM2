from fastapi import APIRouter, HTTPException
from azure.cosmos.exceptions import CosmosHttpResponseError
from .cosmos import get_cosmos_container
from .models import JobCreateRequest, JobCreateResponse, job_to_entity
from .blob_service import generate_upload_sas

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.post("", response_model=JobCreateResponse, status_code=201)
def create_job(req: JobCreateRequest):
    container = get_cosmos_container()
    entity = job_to_entity(req)
    try:
        container.create_item(body=entity)
    except CosmosHttpResponseError as e:
        raise HTTPException(status_code=500, detail=f"Cosmos error: {getattr(e, 'message', str(e))}")

    blob_path = f"{entity['id']}/{req.fileName}"

    upload_url = generate_upload_sas(blob_path)
    
    return JobCreateResponse(job_id=entity["id"], status=entity["status"], created_at=entity["created_at"], upload_url=upload_url)

@router.get("/{job_id}", summary="Get job details", description="Retrieve the details of a job by its ID")
def get_job(job_id: str):
    container = get_cosmos_container()
    try:
        item = container.read_item(item=job_id, partition_key="JOB")
        return item
    except CosmosHttpResponseError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="Job not found")
        else:
            raise HTTPException(status_code=500, detail=f"Cosmos error: {getattr(e, 'message', str(e))}")