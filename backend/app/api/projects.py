import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.models.models import Project, ProjectMember, Environment, User, ProjectInvitation
from app.schemas.schemas import ProjectCreate, ProjectOut, MemberOut
from app.api.deps import get_current_user
from app.core.roles import OWNER_ROLE, MEMBER_ROLE, is_supported_project_role

router = APIRouter(prefix="/api/projects", tags=["Projects"])

# Schemas for direct invite links
class InviteCreateResponse(BaseModel):
    invite_url: str
    token: str
    expires_at: datetime

class AcceptInviteRequest(BaseModel):
    token: str

@router.post("", response_model=ProjectOut)
def create_project(
    project_in: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = Project(name=project_in.name, description=project_in.description)
    db.add(project)
    db.flush()

    # Assign creator as OWNER
    member = ProjectMember(user_id=current_user.id, project_id=project.id, role=OWNER_ROLE)
    db.add(member)

    # Automatically generate default environments
    default_envs = ["Development", "Staging", "Production"]
    for env_name in default_envs:
        db.add(Environment(name=env_name, project_id=project.id))

    db.commit()
    db.refresh(project)
    
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "created_at": project.created_at,
        "role": OWNER_ROLE,
        "environments": project.environments
    }

@router.get("", response_model=List[ProjectOut])
def get_user_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    memberships = (
        db.query(ProjectMember)
        .options(joinedload(ProjectMember.project).joinedload(Project.environments))
        .filter(ProjectMember.user_id == current_user.id)
        .all()
    )
    results = []
    for m in memberships:
        if not is_supported_project_role(m.role):
            raise HTTPException(status_code=403, detail="Unsupported project role")
        p = m.project
        results.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "created_at": p.created_at,
            "role": m.role,
            "environments": p.environments
        })
    return results

@router.get("/{project_id}", response_model=ProjectOut)
def get_project_details(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id
    ).first()

    if not membership:
        raise HTTPException(status_code=403, detail="Access denied to this project")
    if not is_supported_project_role(membership.role):
        raise HTTPException(status_code=403, detail="Unsupported project role")

    p = membership.project
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "created_at": p.created_at,
        "role": membership.role,
        "environments": p.environments
    }

@router.get("/{project_id}/members", response_model=List[MemberOut])
def get_project_members(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieves all members for a project (UI-06)."""
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id
    ).first()

    if not membership:
        raise HTTPException(status_code=403, detail="Access denied to this project")
    if not is_supported_project_role(membership.role):
        raise HTTPException(status_code=403, detail="Unsupported project role")

    members = (
        db.query(ProjectMember)
        .options(joinedload(ProjectMember.user))
        .filter(ProjectMember.project_id == project_id)
        .all()
    )
    return [
        {
            "id": m.id,
            "user_id": m.user_id,
            "role": m.role,
            "name": m.user.name if m.user else "Unknown User",
            "email": m.user.email if m.user else "Unknown Email"
        }
        for m in members
    ]

@router.post("/{project_id}/invites", response_model=InviteCreateResponse)
def create_project_invite(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generates a secure, single-use invite link for the project (Owner only)."""
    membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id
    ).first()

    if not membership or membership.role != OWNER_ROLE:
        raise HTTPException(status_code=403, detail="Only project owners can generate invite links")

    # Cryptographically secure random token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

    invite = ProjectInvitation(
        project_id=project_id,
        token=token,
        role=MEMBER_ROLE,
        expires_at=expires_at,
    )
    db.add(invite)
    db.commit()

    frontend_base = os.getenv("FRONTEND_URL", "https://en-vshare.vercel.app")
    invite_url = f"{frontend_base}?invite={token}"

    return {
        "invite_url": invite_url,
        "token": token,
        "expires_at": expires_at
    }

@router.post("/accept-invite")
def accept_project_invite(
    body: AcceptInviteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accept an invitation using atomic single-use token consumption."""
    invite = db.query(ProjectInvitation).filter(
        ProjectInvitation.token == body.token
    ).first()

    if not invite:
        raise HTTPException(status_code=404, detail="Invalid invitation link")

    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == invite.project_id,
        ProjectMember.user_id == current_user.id
    ).first()

    if existing:
        return {
            "message": "You are already a member of this project",
            "project_id": invite.project_id
        }

    if invite.is_used:
        raise HTTPException(status_code=400, detail="This invitation link has already been used")

    now = datetime.now(timezone.utc)
    exp = invite.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)

    if now > exp:
        raise HTTPException(status_code=400, detail="This invitation link has expired")

    assigned_role = invite.role or MEMBER_ROLE
    if assigned_role != MEMBER_ROLE:
        raise HTTPException(status_code=400, detail="Invitation contains an unsupported project role")

    # Atomic claim: only one request can change this invitation from unused to used.
    claimed = db.query(ProjectInvitation).filter(
        ProjectInvitation.id == invite.id,
        ProjectInvitation.is_used.is_(False)
    ).update(
        {ProjectInvitation.is_used: True},
        synchronize_session=False
    )

    if claimed != 1:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="This invitation link has already been used"
        )

    db.add(ProjectMember(
        user_id=current_user.id,
        project_id=invite.project_id,
        role=assigned_role
    ))

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(ProjectMember).filter(
            ProjectMember.project_id == invite.project_id,
            ProjectMember.user_id == current_user.id
        ).first()
        if existing:
            return {
                "message": "You are already a member of this project",
                "project_id": invite.project_id
            }
        raise HTTPException(status_code=409, detail="Invitation could not be accepted")

    return {"message": "Successfully joined project", "project_id": invite.project_id}