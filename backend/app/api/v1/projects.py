import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Label, Project, ProjectMember, ProjectMemberRole, User
from app.schemas import LabelCreate, LabelOut, LabelsUpdate, MemberInvite, ProjectCreate, ProjectOut
from app.services.export_service import ensure_project_access

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
async def list_projects(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project).join(ProjectMember).where(ProjectMember.user_id == user.id)
    )
    return result.scalars().all()


@router.post("", response_model=ProjectOut)
async def create_project(
    payload: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = Project(name=payload.name, description=payload.description, created_by=user.id)
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=ProjectMemberRole.admin))
    defaults = [
        Label(project_id=project.id, class_id=0, name="object", color="#e74c3c", sort_order=0),
    ]
    db.add_all(defaults)
    await db.commit()
    await db.refresh(project)
    return project


@router.post("/{project_id}/members", response_model=dict)
async def invite_member(
    project_id: uuid.UUID,
    payload: MemberInvite,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await ensure_project_access(db, project_id, user.id)
    target = await db.execute(select(User).where(User.email == payload.email))
    member_user = target.scalar_one_or_none()
    if not member_user:
        raise HTTPException(status_code=404, detail="User not found")
    role = ProjectMemberRole(payload.role)
    db.add(ProjectMember(project_id=project_id, user_id=member_user.id, role=role))
    await db.commit()
    return {"message": "Member added"}


@router.get("/{project_id}/labels", response_model=list[LabelOut])
async def get_labels(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await ensure_project_access(db, project_id, user.id)
    result = await db.execute(select(Label).where(Label.project_id == project_id).order_by(Label.sort_order))
    return result.scalars().all()


@router.put("/{project_id}/labels", response_model=list[LabelOut])
async def update_labels(
    project_id: uuid.UUID,
    payload: LabelsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await ensure_project_access(db, project_id, user.id)
    existing = await db.execute(select(Label).where(Label.project_id == project_id))
    for label in existing.scalars().all():
        await db.delete(label)
    new_labels = [
        Label(
            project_id=project_id,
            class_id=item.class_id,
            name=item.name,
            color=item.color,
            sort_order=item.sort_order,
        )
        for item in payload.labels
    ]
    db.add_all(new_labels)
    await db.commit()
    result = await db.execute(select(Label).where(Label.project_id == project_id).order_by(Label.sort_order))
    return result.scalars().all()
