from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.models import HistoryLog, Environment, ProjectMember, User, Variable
from app.schemas.schemas import HistoryLogOut
from app.api.deps import get_current_user
from app.core.crypto import encrypt_value
from app.services.parser import is_sensitive_key
from app.core.roles import OWNER_ROLE

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

    if member.role not in {OWNER_ROLE, "MEMBER"}:
        raise HTTPException(status_code=403, detail="Unsupported project role")

    logs = (
        db.query(HistoryLog)
        .filter(HistoryLog.environment_id == env_id)
        .order_by(HistoryLog.created_at.desc())
        .all()
    )

    sensitive_keys = {
        variable.key
        for variable in db.query(Variable).filter(
            Variable.environment_id == env_id,
            Variable.is_sensitive.is_(True)
        ).all()
    }

    results = []
    for log in logs:
        # Mask values using key heuristics and stored sensitivity metadata.
        is_sensitive = bool(log.key) and (
            is_sensitive_key(log.key) or log.key in sensitive_keys
        )
        display_old = "[ENCRYPTED]" if (is_sensitive and log.old_value and log.old_value != "[REDACTED]") else log.old_value
        display_new = "[ENCRYPTED]" if (is_sensitive and log.new_value and log.new_value != "[REDACTED]") else log.new_value

        results.append({
            "id": log.id,
            "action": log.action,
            "key": log.key,
            "old_value": display_old,
            "new_value": display_new,
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

    # 2. Check project membership and require OWNER role for revert actions (SEC-03, AUTHZ-01)
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == env.project_id,
        ProjectMember.user_id == current_user.id
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Access denied")
    if member.role != OWNER_ROLE:
        raise HTTPException(
            status_code=403,
            detail="Only project owners are authorized to revert environment history."
        )

    # 3. Locate target history log
    log = db.query(HistoryLog).filter(
        HistoryLog.id == log_id,
        HistoryLog.environment_id == env_id
    ).first()
    if not log:
        raise HTTPException(status_code=404, detail="Audit log entry not found")

    if not log.key:
        raise HTTPException(status_code=400, detail="Cannot revert a bulk log with no associated key")

    # 4. Check whether value is recoverable (FUNC-04, SEC-05)
    if log.old_value in ["[ENCRYPTED]", "[REDACTED]"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot revert: sensitive secret values are masked in audit logs. Please restore the environment from a snapshot."
        )

    var = db.query(Variable).filter(
        Variable.environment_id == env_id,
        Variable.key == log.key
    ).first()

    # 5. Apply the rollback based on log action
    if log.action == "UPDATE":
        if not log.old_value:
            raise HTTPException(status_code=400, detail="No previous value recorded to restore")
        
        should_encrypt = is_sensitive_key(log.key) or bool(var and var.is_sensitive)
        stored_val = log.old_value
        stored_iv = None
        if should_encrypt:
            enc = encrypt_value(log.old_value)
            stored_val = enc["ciphertext"]
            stored_iv = enc["iv"]

        if not var:
            var = Variable(
                key=log.key,
                value=stored_val,
                iv=stored_iv,
                is_sensitive=should_encrypt,
                environment_id=env_id
            )
            db.add(var)
        else:
            var.value = stored_val
            var.is_sensitive = should_encrypt
            var.iv = stored_iv

        db.add(HistoryLog(
            action="UPDATE",
            key=log.key,
            old_value="[ENCRYPTED]" if should_encrypt else (var.value if var else "[DELETED]"),
            new_value="[ENCRYPTED]" if should_encrypt else log.old_value,
            user_id=current_user.id,
            project_id=env.project_id,
            environment_id=env_id
        ))

    elif log.action == "DELETE":
        if not log.old_value:
            raise HTTPException(status_code=400, detail="No previous value recorded to restore")

        should_encrypt = is_sensitive_key(log.key) or bool(var and var.is_sensitive)
        stored_val = log.old_value
        stored_iv = None
        if should_encrypt:
            enc = encrypt_value(log.old_value)
            stored_val = enc["ciphertext"]
            stored_iv = enc["iv"]

        if var:
            var.value = stored_val
            var.is_sensitive = should_encrypt
            var.iv = stored_iv
        else:
            var = Variable(
                key=log.key,
                value=stored_val,
                iv=stored_iv,
                is_sensitive=should_encrypt,
                environment_id=env_id
            )
            db.add(var)

        db.add(HistoryLog(
            action="CREATE",
            key=log.key,
            old_value=None,
            new_value="[ENCRYPTED]" if should_encrypt else log.old_value,
            user_id=current_user.id,
            project_id=env.project_id,
            environment_id=env_id
        ))

    elif log.action == "CREATE":
        # Check if newer modifications exist for this variable (FUNC-03)
        newer_log = db.query(HistoryLog).filter(
            HistoryLog.environment_id == env_id,
            HistoryLog.key == log.key,
            HistoryLog.created_at > log.created_at
        ).first()

        if newer_log:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot revert '{log.key}' creation because subsequent modifications exist for this variable."
            )

        if var:
            db.add(HistoryLog(
                action="DELETE",
                key=var.key,
                old_value="[ENCRYPTED]" if var.is_sensitive else var.value,
                new_value=None,
                user_id=current_user.id,
                project_id=env.project_id,
                environment_id=env_id
            ))
            db.delete(var)

    db.commit()
    return {"message": f"Successfully reverted '{log.key}'"}
