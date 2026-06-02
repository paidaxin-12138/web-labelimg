from __future__ import annotations

import io
import uuid
import zipfile
from typing import Optional

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnnotationVersion, ExportFormat, ExportJob, ExportStatus, Image, Label, ProjectMember
from app.storage import get_storage


async def ensure_project_access(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    result = await db.execute(
        select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise PermissionError("No access to project")


def bbox_to_yolo(ann: dict, width: int, height: int, class_id: int) -> Optional[str]:
    if ann.get("type") != "bbox":
        return None
    geom = ann.get("geometry", {})
    x, y, w, h = geom.get("x", 0), geom.get("y", 0), geom.get("width", 0), geom.get("height", 0)
    x_center = (x + w / 2) / width
    y_center = (y + h / 2) / height
    w_norm = w / width
    h_norm = h / height
    return f"{class_id} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}"


async def run_yolo_export(db: AsyncSession, job_id: uuid.UUID) -> None:
    result = await db.execute(select(ExportJob).where(ExportJob.id == job_id))
    job = result.scalar_one()
    job.status = ExportStatus.running
    await db.commit()

    try:
        labels_result = await db.execute(select(Label).where(Label.project_id == job.project_id))
        label_rows = labels_result.scalars().all()
        labels = {str(label.id): label.class_id for label in label_rows}

        images_result = await db.execute(select(Image).where(Image.project_id == job.project_id))
        images = images_result.scalars().all()

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            class_names = [label.name for label in sorted(label_rows, key=lambda x: x.class_id)]
            zf.writestr("classes.txt", "\n".join(class_names))

            for image in images:
                version_result = await db.execute(
                    select(AnnotationVersion)
                    .where(AnnotationVersion.image_id == image.id)
                    .order_by(AnnotationVersion.version.desc())
                    .limit(1)
                )
                version = version_result.scalar_one_or_none()
                if not version:
                    continue

                lines = []
                for ann in version.data.get("annotations", []):
                    label_id = ann.get("label_id")
                    class_id = labels.get(label_id, 0)
                    line = bbox_to_yolo(ann, image.width, image.height, class_id)
                    if line:
                        lines.append(line)

                base = image.filename.rsplit(".", 1)[0]
                zf.writestr(f"labels/{base}.txt", "\n".join(lines))

        storage = get_storage()
        key = f"exports/{job.project_id}/{job.id}.zip"
        await storage.upload(key, buffer.getvalue(), "application/zip")

        job.status = ExportStatus.done
        job.result_url = storage.get_url(key)
    except Exception as exc:
        job.status = ExportStatus.failed
        job.error_message = str(exc)
    await db.commit()


async def create_thumbnail(data: bytes, max_size: int) -> bytes:
    with Image.open(io.BytesIO(data)) as img:
        img.thumbnail((max_size, max_size))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=85)
        return out.getvalue()
