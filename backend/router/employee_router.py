from fastapi import APIRouter, Request, Depends, HTTPException, status,File, UploadFile, Form,Query
from sqlalchemy.orm import Session
from models import modelsp,database_models
from database import get_db

router = APIRouter(prefix="/api/employee", tags=["auth"])

# Get all projects assigned to a user
@router.get("/api/admin/user_projects/{user_id}")
def get_user_projects(user_id: str, db: Session = Depends(get_db)):
    from models.database_models import Project, ProjectMember

    results = (
        db.query(Project.name)
        .select_from(ProjectMember)
        .join(Project, Project.id == ProjectMember.project_id)
        .filter(ProjectMember.user_id == user_id)
        .all()
    )

    if not results:
        raise HTTPException(status_code=404, detail="No projects found for this user")

    return [r.name for r in results]
