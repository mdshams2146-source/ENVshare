from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.models import Project, ProjectMember, Environment, User, HistoryLog
from app.schemas.schemas import ProjectCreate, ProjectOut, AddMemberRequest, MemberOut
from app.api.deps import get_current_user
from app.services.email_service import send_project_invite_email

router = APIRouter(prefix="/api/projects", tags=["Projects"])

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

@router.post("/{project_id}/members")
def add_project_member(
    project_id: str,
    member_in: AddMemberRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    caller_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id
    ).first()

    if not caller_member or caller_member.role != "OWNER":
        raise HTTPException(status_code=403, detail="Only project owners can invite members")

    invitee = db.query(User).filter(User.email == member_in.email).first()
    if not invitee:
        raise HTTPException(status_code=404, detail="No registered user found with this email")

    existing_membership = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == invitee.id
    ).first()

    if existing_membership:
        raise HTTPException(status_code=400, detail="User is already a project member")

    new_member = ProjectMember(user_id=invitee.id, project_id=project_id, role="MEMBER")
    db.add(new_member)
    db.commit()

    send_project_invite_email(invitee.email, caller_member.project.name, current_user.name)

    return {"message": f"User {invitee.email} successfully added to project"}