from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.models import HistoryLog, Environment, ProjectMember, User
from app.schemas.schemas import HistoryLogOut
from app.api.deps import get_current_user

router = APIRouter(prefix="/api/environments/{env_id}/history", tags=["History"])

@router.get("", response_model=List[HistoryLogOut])
def get_environment_history(
    env_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    env = db.query(Environment).filter(Environment.id == env_id).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")

    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == env.project_id,
        ProjectMember.user_id == current_user.id
    ).first()

    if not member:
        raise HTTPException(status_code=403, detail="Access denied")

    logs = (
        db.query(HistoryLog)
        .filter(HistoryLog.environment_id == env_id)
        .order_by(HistoryLog.created_at.desc())
        .all()
    )

    results = []
    for log in logs:
        results.append({
            "id": log.id,
            "action": log.action,
            "key": log.key,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "user_name": log.user.name if log.user else "Unknown User",
            "created_at": log.created_at
        })

    return results