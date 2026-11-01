import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Project, ProjectMember, Environment, User, ProjectInvitation
from app.schemas.schemas import ProjectCreate, ProjectOut
from app.api.deps import get_current_user

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
    member = ProjectMember(user_id=current_user.id, project_id=project.id, role="OWNER")
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
        "role": "OWNER",
        "environments": project.environments
    }

@router.get("", response_model=List[ProjectOut])
def get_user_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    memberships = db.query(ProjectMember).filter(ProjectMember.user_id == current_user.id).all()
    results = []
    for m in memberships:
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

    p = membership.project
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "created_at": p.created_at,
        "role": membership.role,
        "environments": p.environments
    }

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

    if not membership or membership.role != "OWNER":
        raise HTTPException(status_code=403, detail="Only project owners can generate invite links")

    # Cryptographically secure random token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

    invite = ProjectInvitation(
        project_id=project_id,
        token=token,
        role="MEMBER",
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
    """Validates the invite token and adds the current authenticated user as a MEMBER."""
    invite = db.query(ProjectInvitation).filter(
        ProjectInvitation.token == body.token
    ).first()

    if not invite:
        raise HTTPException(status_code=404, detail="Invalid invitation link")

    if invite.is_used:
        raise HTTPException(status_code=400, detail="This invitation link has already been used")

    # Timezone-aware expiration check
    now = datetime.now(timezone.utc)
    exp = invite.expires_at if invite.expires_at.tzinfo else invite.expires_at.replace(tzinfo=timezone.utc)
    if now > exp:
        raise HTTPException(status_code=400, detail="This invitation link has expired")

    # Check if user is already a member
    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == invite.project_id,
        ProjectMember.user_id == current_user.id
    ).first()

    if existing:
        invite.is_used = True
        db.commit()
        return {"message": "You are already a member of this project", "project_id": invite.project_id}

    # Add as member and mark token used
    new_member = ProjectMember(
        user_id=current_user.id,
        project_id=invite.project_id,
        role=invite.role or "MEMBER"
    )
    invite.is_used = True
    db.add(new_member)
    db.commit()

    return {"message": "Successfully joined project", "project_id": invite.project_id}