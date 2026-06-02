from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel, Generic[T]):
    total: int
    page: int
    page_size: int
    items: list[T]


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    display_name: str = Field(min_length=1, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    role: str
    is_active: bool
    created_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None


class ProjectOut(ORMModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    status: str
    created_at: datetime


class MemberInvite(BaseModel):
    email: EmailStr
    role: str = "annotator"


class LabelCreate(BaseModel):
    class_id: int
    name: str
    color: str = "#4a6fa5"
    sort_order: int = 0


class LabelOut(ORMModel):
    id: uuid.UUID
    class_id: int
    name: str
    color: str
    sort_order: int


class LabelsUpdate(BaseModel):
    labels: list[LabelCreate]


class ImageOut(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    filename: str
    width: int
    height: int
    file_size: int
    status: str
    version: int
    thumbnail_url: Optional[str] = None
    url: Optional[str] = None
    created_at: datetime


class AnnotationDocument(BaseModel):
    schema_version: int = 2
    image_id: str
    image_width: int
    image_height: int
    annotations: list[dict[str, Any]] = Field(default_factory=list)


class AnnotationSaveRequest(BaseModel):
    base_version: int
    data: AnnotationDocument
    comment: Optional[str] = None
    force: bool = False


class AnnotationSaveResponse(BaseModel):
    version: int
    saved_at: datetime
    saved_by: uuid.UUID


class AnnotationVersionOut(ORMModel):
    id: uuid.UUID
    version: int
    data: dict[str, Any]
    created_by: uuid.UUID
    created_at: datetime
    comment: Optional[str]


class ExportCreate(BaseModel):
    format: str = "yolo"


class ExportJobOut(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    format: str
    status: str
    result_url: Optional[str]
    created_at: datetime


class ReviewRequest(BaseModel):
    action: str
    comment: Optional[str] = None
