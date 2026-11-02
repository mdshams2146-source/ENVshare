import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from datetime import datetime

from app.core.database import get_db
from app.models.models import Environment, ProjectMember, User, Variable, HistoryLog, EnvironmentSnapshot
from app.api.deps import get_current_user
from app.schemas.schemas import VariableOut

router = APIRouter(prefix="/api/environments/{env_id}/snapshots", tags=["Snapshots"])

class SnapshotCreate(BaseModel):
    name: str

class SnapshotOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    created_by_name: str
    var_count: int

    class Config:
        from_attributes = True

def verify_env_access(env_id: str, user_id: str, db: Session) -> Environment:
    env = db.query(Environment).filter(Environment.id == env_id).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == env.project_id,
        ProjectMember.user_id == user_id
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Access denied")
    return env

@router.get("", response_model=List[SnapshotOut])
def list_snapshots(
    env_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    verify_env_access(env_id, current_user.id, db)
    snaps = (
        db.query(EnvironmentSnapshot)
        .filter(EnvironmentSnapshot.environment_id == env_id)
        .order_by(EnvironmentSnapshot.created_at.desc())
        .all()
    )
    
    out = []
    for s in snaps:
        data = json.loads(s.variables_data)
        out.append(SnapshotOut(
            id=s.id,
            name=s.name,
            created_at=s.created_at,
            created_by_name=s.created_by.name if s.created_by else "System",
            var_count=len(data)
        ))
    return out

@router.post("", response_model=SnapshotOut)
def create_manual_snapshot(
    env_id: str,
    payload: SnapshotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    verify_env_access(env_id, current_user.id, db)
    
    # Capture all active variables exactly as stored (preserving ciphertext and iv)
    current_vars = db.query(Variable).filter(Variable.environment_id == env_id).all()
    snap_data = [
        {
            "key": v.key,
            "value": v.value,
            "iv": v.iv,
            "is_sensitive": v.is_sensitive
        }
        for v in current_vars
    ]

    snapshot = EnvironmentSnapshot(
        environment_id=env_id,
        created_by_id=current_user.id,
        name=payload.name.strip() or f"Backup {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        variables_data=json.dumps(snap_data)
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    return SnapshotOut(
        id=snapshot.id,
        name=snapshot.name,
        created_at=snapshot.created_at,
        created_by_name=current_user.name,
        var_count=len(snap_data)
    )

@router.post("/{snapshot_id}/rollback")
def rollback_to_snapshot(
    env_id: str,
    snapshot_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    env = verify_env_access(env_id, current_user.id, db)

    target_snap = db.query(EnvironmentSnapshot).filter(
        EnvironmentSnapshot.id == snapshot_id,
        EnvironmentSnapshot.environment_id == env_id
    ).first()
    if not target_snap:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    # 1. Take safety pre-rollback snapshot of current state
    active_vars = db.query(Variable).filter(Variable.environment_id == env_id).all()
    pre_rollback_data = [
        {"key": v.key, "value": v.value, "iv": v.iv, "is_sensitive": v.is_sensitive}
        for v in active_vars
    ]
    safety_snap = EnvironmentSnapshot(
        environment_id=env_id,
        created_by_id=current_user.id,
        name=f"Safety Backup (Before Rollback to {target_snap.name})",
        variables_data=json.dumps(pre_rollback_data)
    )
    db.add(safety_snap)

    # 2. Delete all current active variables
    for v in active_vars:
        db.delete(v)
    db.flush()

    # 3. Restore variables from snapshot
    restored_items = json.loads(target_snap.variables_data)
    for item in restored_items:
        new_v = Variable(
            environment_id=env_id,
            key=item["key"],
            value=item["value"],
            iv=item["iv"],
            is_sensitive=item["is_sensitive"]
        )
        db.add(new_v)

    # 4. Log rollback in audit history
    db.add(HistoryLog(
        action="ROLLBACK",
        key=f"Snapshot: {target_snap.name}",
        old_value=f"{len(active_vars)} variables",
        new_value=f"{len(restored_items)} variables restored",
        user_id=current_user.id,
        project_id=env.project_id,
        environment_id=env_id
    ))

    db.commit()
    return {"message": f"Successfully rolled back environment to '{target_snap.name}'"}