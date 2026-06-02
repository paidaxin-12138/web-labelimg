import io
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image as PILImage

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Image, User
from app.schemas import ImageOut, PaginatedResponse
from app.services.export_service import create_thumbnail, ensure_project_access
from app.storage import get_storage

router = APIRouter(tags=["images"])


def image_to_out(image: Image, storage) -> ImageOut:
    return ImageOut(
        id=image.id,
        project_id=image.project_id,
        filename=image.filename,
        width=image.width,
        height=image.height,
        file_size=image.file_size,
        status=image.status.value,
        version=image.version,
        thumbnail_url=storage.get_url(image.thumbnail_key) if image.thumbnail_key else None,
        url=storage.get_url(image.storage_key),
        created_at=image.created_at,
    )


@router.get("/projects/{project_id}/images", response_model=PaginatedResponse[ImageOut])
async def list_images(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await ensure_project_access(db, project_id, user.id)
    total = await db.scalar(
        select(func.count()).select_from(Image).where(Image.project_id == project_id)
    )
    result = await db.execute(
        select(Image)
        .where(Image.project_id == project_id)
        .order_by(Image.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    storage = get_storage()
    items = [image_to_out(img, storage) for img in result.scalars().all()]
    return PaginatedResponse(total=total or 0, page=page, page_size=page_size, items=items)


@router.post("/projects/{project_id}/images/upload", response_model=list[ImageOut])
async def upload_images(
    project_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await ensure_project_access(db, project_id, user.id)
    settings = get_settings()
    storage = get_storage()
    created: list[ImageOut] = []

    for upload in files:
        data = await upload.read()
        if not data:
            continue
        with PILImage.open(io.BytesIO(data)) as img:
            width, height = img.size

        image_id = uuid.uuid4()
        ext = (upload.filename or "image.jpg").split(".")[-1].lower()
        storage_key = f"projects/{project_id}/images/{image_id}/original.{ext}"
        thumb_key = f"projects/{project_id}/images/{image_id}/thumb.jpg"

        await storage.upload(storage_key, data, upload.content_type or "image/jpeg")
        thumb_data = await create_thumbnail(data, settings.THUMBNAIL_MAX_SIZE)
        await storage.upload(thumb_key, thumb_data, "image/jpeg")

        record = Image(
            id=image_id,
            project_id=project_id,
            filename=upload.filename or f"{image_id}.{ext}",
            storage_key=storage_key,
            thumbnail_key=thumb_key,
            width=width,
            height=height,
            file_size=len(data),
        )
        db.add(record)
        await db.flush()
        created.append(image_to_out(record, storage))

    await db.commit()
    return created


@router.get("/images/{image_id}", response_model=ImageOut)
async def get_image(
    image_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Image).where(Image.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    await ensure_project_access(db, image.project_id, user.id)
    return image_to_out(image, get_storage())
