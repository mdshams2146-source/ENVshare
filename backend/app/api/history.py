from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.models import HistoryLog, Environment, ProjectMember, User, Variable
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

@router.post("/{log_id}/revert")
def revert_history_log(
    env_id: str,
    log_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Verify environment existence
    env = db.query(Environment).filter(Environment.id == env_id).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")

    # 2. Check project membership
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == env.project_id,
        ProjectMember.user_id == current_user.id
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Access denied")

    # 3. Locate target history log
    log = db.query(HistoryLog).filter(
        HistoryLog.id == log_id,
        HistoryLog.environment_id == env_id
    ).first()
    if not log:
        raise HTTPException(status_code=404, detail="Audit log entry not found")

    if not log.key:
        raise HTTPException(status_code=400, detail="Cannot revert a bulk log with no associated key")

    # 4. Check whether value is recoverable
    if log.old_value == "[ENCRYPTED]":
        raise HTTPException(
            status_code=400,
            detail="Cannot revert: sensitive secret values are masked in the audit log."
        )

    var = db.query(Variable).filter(
        Variable.environment_id == env_id,
        Variable.key == log.key
    ).first()

    # 5. Apply the rollback based on log action
    if log.action == "UPDATE":
        if not log.old_value:
            raise HTTPException(status_code=400, detail="No previous value recorded to restore")
        
        current_val_for_log = var.value if var else "[DELETED]"
        if not var:
            var = Variable(
                key=log.key,
                value=log.old_value,
                is_sensitive=False,
                environment_id=env_id
            )
            db.add(var)
        else:
            var.value = log.old_value
            var.is_sensitive = False
            var.iv = None

        db.add(HistoryLog(
            action="UPDATE",
            key=log.key,
            old_value=current_val_for_log,
            new_value=log.old_value,
            user_id=current_user.id,
            project_id=env.project_id,
            environment_id=env_id
        ))

    elif log.action == "DELETE":
        if not log.old_value:
            raise HTTPException(status_code=400, detail="No previous value recorded to restore")

        if var:
            var.value = log.old_value
            var.is_sensitive = False
            var.iv = None
        else:
            var = Variable(
                key=log.key,
                value=log.old_value,
                is_sensitive=False,
                environment_id=env_id
            )
            db.add(var)

        db.add(HistoryLog(
            action="CREATE",
            key=log.key,
            old_value=None,
            new_value=log.old_value,
            user_id=current_user.id,
            project_id=env.project_id,
            environment_id=env_id
        ))

    elif log.action == "CREATE":
        if var:
            db.add(HistoryLog(
                action="DELETE",
                key=var.key,
                old_value=var.value,
                new_value=None,
                user_id=current_user.id,
                project_id=env.project_id,
                environment_id=env_id
            ))
            db.delete(var)

    db.commit()
    return {"message": f"Successfully reverted '{log.key}'"}