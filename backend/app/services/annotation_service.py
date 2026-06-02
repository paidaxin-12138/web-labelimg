from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnnotationVersion, Image, ImageStatus


async def get_latest_annotation(db: AsyncSession, image_id: uuid.UUID) -> Optional[AnnotationVersion]:
    result = await db.execute(
        select(AnnotationVersion)
        .where(AnnotationVersion.image_id == image_id)
        .order_by(AnnotationVersion.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def save_annotation(
    db: AsyncSession,
    image: Image,
    user_id: uuid.UUID,
    data: dict,
    base_version: int,
    comment: Optional[str],
    force: bool,
) -> Tuple[int, datetime]:
    if image.version != base_version and not force:
        raise ValueError("version_conflict")

    new_version = image.version + 1
    image.version = new_version
    image.status = ImageStatus.annotating
    image.annotated_at = datetime.now(timezone.utc)

    record = AnnotationVersion(
        image_id=image.id,
        version=new_version,
        data=data,
        created_by=user_id,
        comment=comment,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return new_version, record.created_at
