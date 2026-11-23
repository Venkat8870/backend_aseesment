from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services import simulator_engine as engine

router = APIRouter(prefix="/v1/simulator", tags=["simulator"])


class DownloadRequest(BaseModel):
    machine_id: str
    last_processed_cursor: int = Field(ge=0)


@router.post("/download")
def latest_file_metadata(req: DownloadRequest):
    meta = engine.create_file(req.machine_id, req.last_processed_cursor)
    if meta is None:
        return Response(status_code=204)  # nothing new yet
    return meta


@router.get("/files/{file_name}")
def download_file(file_name: str):
    # block path tricks like ../../secret
    if Path(file_name).name != file_name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    path = engine.FILES_DIR / file_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, media_type="text/csv", filename=file_name)