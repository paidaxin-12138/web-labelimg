import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.core.deps import get_current_user
from app.models import ExportFormat, ExportJob, ExportStatus, Image, User
from app.schemas import (
    AnnotationSaveRequest,
    AnnotationSaveResponse,
    AnnotationVersionOut,
    ExportCreate,
    ExportJobOut,
)
from app.services.annotation_service import get_latest_annotation, save_annotation
from app.services.export_service import ensure_project_access, run_yolo_export

router = APIRouter(tags=["annotations"])


@router.get("/images/{image_id}/annotations")
async def get_annotations(
    image_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Image).where(Image.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    await ensure_project_access(db, image.project_id, user.id)

    latest = await get_latest_annotation(db, image_id)
    return {
        "version": image.version,
        "data": latest.data if latest else {
            "schema_version": 2,
            "image_id": str(image_id),
            "image_width": image.width,
            "image_height": image.height,
            "annotations": [],
        },
    }


@router.put("/images/{image_id}/annotations", response_model=AnnotationSaveResponse)
async def put_annotations(
    image_id: uuid.UUID,
    payload: AnnotationSaveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Image).where(Image.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    await ensure_project_access(db, image.project_id, user.id)

    try:
        version, saved_at = await save_annotation(
            db,
            image,
            user.id,
            payload.data.model_dump(),
            payload.base_version,
            payload.comment,
            payload.force,
        )
    except ValueError:
        latest = await get_latest_annotation(db, image_id)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Version conflict",
                "current_version": image.version,
                "server_data": latest.data if latest else None,
            },
        ) from None

    return AnnotationSaveResponse(version=version, saved_at=saved_at, saved_by=user.id)


@router.get("/images/{image_id}/annotations/history", response_model=list[AnnotationVersionOut])
async def annotation_history(
    image_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Image).where(Image.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    await ensure_project_access(db, image.project_id, user.id)

    from app.models import AnnotationVersion

    rows = await db.execute(
        select(AnnotationVersion)
        .where(AnnotationVersion.image_id == image_id)
        .order_by(AnnotationVersion.version.desc())
    )
    return rows.scalars().all()


@router.post("/projects/{project_id}/exports", response_model=ExportJobOut)
async def create_export(
    project_id: uuid.UUID,
    payload: ExportCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await ensure_project_access(db, project_id, user.id)
    job = ExportJob(
        project_id=project_id,
        format=ExportFormat(payload.format),
        status=ExportStatus.pending,
        created_by=user.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    async def _run(job_id: uuid.UUID):
        async with AsyncSessionLocal() as session:
            await run_yolo_export(session, job_id)

    background_tasks.add_task(_run, job.id)
    return job


@router.get("/exports/{job_id}", response_model=ExportJobOut)
async def get_export(job_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ExportJob).where(ExportJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    await ensure_project_access(db, job.project_id, user.id)
    return job
