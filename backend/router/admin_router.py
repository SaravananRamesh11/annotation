from fastapi import APIRouter, Request, Depends, HTTPException, status,File, UploadFile, Form
from sqlalchemy.orm import Session
from database import get_db
from sqlalchemy.dialects.postgresql import JSONB
from models import database_models
from dotenv import load_dotenv
import  uuid,os
from utils import s3_connection
from botocore.exceptions import NoCredentialsError
from typing import List
from models import modelsp


load_dotenv()


AWS_ACCESS_KEY =os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION =   os.getenv("AWS_REGION")
BUCKET_NAME =  os.getenv("BUCKET_NAME")


router = APIRouter(prefix="/api/admin", tags=["auth"])



@router.post("/upload-to-s3")
async def upload_files_to_s3(
    id: str = Form(...),
    project_name: str = Form(...),
    proofImages: List[UploadFile] = File(...),
    s3_client=Depends(s3_connection.get_s3_connection),
):
    uploaded_files = []

    try:
        print("🟢 Received form fields:")
        print(f"id={id}")
        print(f"project_name={project_name}")
        print(f"proofImages count={len(proofImages)}")

        # --- Create finished_directory for the project ---
        finished_dir_key = f"annotation/{project_name}/finished_directory/"
        s3_client.put_object(Bucket=BUCKET_NAME, Key=finished_dir_key)
        print(f"✅ Created empty directory: {finished_dir_key}")

        # --- Upload files to working_directory ---
        for file in proofImages:
            if not file.filename:
                continue

            file_extension = os.path.splitext(file.filename)[1]
            unique_name = f"{uuid.uuid4().hex}{file_extension}"

            s3_key = f"annotation/{project_name}/working_directory/{unique_name}"

            file.file.seek(0)
            s3_client.upload_fileobj(
                file.file,
                BUCKET_NAME,
                s3_key,
                ExtraArgs={'ContentType': file.content_type}
            )

            file_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
            uploaded_files.append(file_url)

        return {
            "message": "Files uploaded successfully!",
            "ticket_id": id,
            "project_name": project_name,
            "file_urls": uploaded_files,
        }

    except NoCredentialsError:
        raise HTTPException(status_code=403, detail="AWS credentials not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create_project")
def create_project(request: modelsp.ProjectCreate, db: Session = Depends(get_db)):
    # Check if a project with the same name exists (optional)
    existing = db.query(database_models.Project).filter(database_models.Project.name == request.project_name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project name already exists")

    new_project = database_models.Project(
        name=request.project_name,
        description=request.description,
        classes=request.classes
    )
    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    return {
        "message": "Project created successfully",
        "project": {
            "id": new_project.id,
            "name": new_project.name,
            "description": new_project.description,
            "classes": new_project.classes,
            "created_at": new_project.created_at
        }
    }


@router.get("/get_all_projects")
def get_all_projects(db: Session = Depends(get_db)):
    projects = db.query(database_models.Project).all()
    return [
        {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "classes": project.classes,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        }
        for project in projects
    ]

   





