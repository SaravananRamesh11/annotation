from fastapi import APIRouter, Request, Depends, HTTPException, status,File, UploadFile, Form,Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from database import get_db
from sqlalchemy.dialects.postgresql import JSONB
from models import database_models
from dotenv import load_dotenv
import  uuid,os,io
from utils import s3_connection
from botocore.exceptions import NoCredentialsError,ClientError
from typing import List
from models import modelsp,database_models
from typing import List, Optional
from datetime import datetime, timedelta
import bcrypt
from fastapi.responses import JSONResponse
import pandas as pd
from helper_functions import admin_helper



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
    db: Session = Depends(get_db)
):
    uploaded_files = []

    try:
        print("🟢 Received form fields:")
        print(f"id={id}")
        print(f"project_name={project_name}")
        print(f"proofImages count={len(proofImages)}")

        # --- Create directory structure for the project ---
        # Create working_directory subdirectories
        working_raw_dir = f"annotation/{project_name}/working_directory/raw/"
        working_assigned_dir = f"annotation/{project_name}/working_directory/assigned/"
        working_review_dir = f"annotation/{project_name}/working_directory/review/"
        
        # Create finished_directory subdirectories
        finished_completed_dir = f"annotation/{project_name}/finished_directory/completed/"
        
        # Create all directories
        s3_client.put_object(Bucket=BUCKET_NAME, Key=working_raw_dir)
        s3_client.put_object(Bucket=BUCKET_NAME, Key=working_assigned_dir)
        s3_client.put_object(Bucket=BUCKET_NAME, Key=working_review_dir)
        s3_client.put_object(Bucket=BUCKET_NAME, Key=finished_completed_dir)
        
        print(f"✅ Created directory structure:")
        print(f"  - {working_raw_dir}")
        print(f"  - {working_assigned_dir}")
        print(f"  - {working_review_dir}")
        print(f"  - {finished_completed_dir}")

        # --- Get project_id from project_name ---
        project = db.query(database_models.Project).filter(database_models.Project.name == project_name).first()
        if not project:
            raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
        
        project_id = project.id
        print(f"📁 Found project: {project_name} (ID: {project_id})")

        # --- Upload files to working_directory/raw/ and save to database ---
        for file in proofImages:
            if not file.filename:
                continue

            file_extension = os.path.splitext(file.filename)[1]
            unique_name = f"{uuid.uuid4().hex}{file_extension}"

            s3_key = f"annotation/{project_name}/working_directory/raw/{unique_name}"

            file.file.seek(0)
            s3_client.upload_fileobj(
                file.file,
                BUCKET_NAME,
                s3_key,
                ExtraArgs={'ContentType': file.content_type}
            )

            # --- Create Files record in database ---
            try:
                new_file = database_models.Files(
                    project_id=project_id,
                    s3_key=unique_name,  # Store only the hexadecimal filename
                    type='image',
                    status='pending'
                )
                
                db.add(new_file)
                db.commit()
                db.refresh(new_file)
                
                print(f"💾 Saved file record: ID={new_file.id}, s3_key={unique_name}")
                
            except Exception as db_error:
                db.rollback()
                print(f"❌ Database error for file {unique_name}: {str(db_error)}")
                # Continue with other files even if one fails
                continue

            file_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
            uploaded_files.append(file_url)

        return {
            "message": "Files uploaded successfully!",
            "ticket_id": id,
            "project_name": project_name,
            "project_id": project_id,
            "files_uploaded": len(uploaded_files),
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

   




#Add User end point


@router.post("/add-user")
async def add_user(user: modelsp.Users, db: Session = Depends(get_db)):
    try:
        # Check if email already exists
        existing_user_email = (
            db.query(database_models.Users)
            .filter(database_models.Users.email == user.email)
            .first()
        )
        if existing_user_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists.",
            )

        # Check if user ID already exists
        existing_user_id = (
            db.query(database_models.Users)
            .filter(database_models.Users.id == user.user_id)
            .first()
        )
        if existing_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this ID already exists.",
            )

        # Hash password
        hashed_password = bcrypt.hashpw(user.password.encode("utf-8"), bcrypt.gensalt())

        # Handle OTP safely
        otp_value = user.otp.strip() if user.otp and user.otp.strip().lower() != "string" else None

        # Handle OTP expiry safely
        otp_expiry_value = None
        if user.otpExpiry and user.otpExpiry.strip().lower() not in ["", "string", "null"]:
            try:
                otp_expiry_value = datetime.fromisoformat(user.otpExpiry)
            except ValueError:
                try:
                    otp_expiry_value = datetime.strptime(user.otpExpiry, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    otp_expiry_value = None  # Invalid format, store as NULL

        # Create new user
        new_user = database_models.Users(
            id=user.user_id,
            name=user.name,
            email=user.email,
            role=user.role,
            password=hashed_password.decode("utf-8"),
            otp=otp_value,
            otpExpiry=otp_expiry_value,
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {
            "message": "User added successfully!",
            "user": {
                "id": new_user.id,
                "name": new_user.name,
                "email": new_user.email,
                "role": new_user.role,
                "otp": new_user.otp,
                "otpExpiry": new_user.otpExpiry,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print("Error adding user:", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
    
# add_project_members endpoint

@router.post("/add_project_members")
async def add_project_members(data: modelsp.AddProjectMembers, db: Session = Depends(get_db)):
    project = db.query(database_models.Project).filter(database_models.Project.name == data.project_name).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    for member in data.members:
        user = db.query(database_models.Users).filter(database_models.Users.id == member.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User {member.user_id} not found")

        new_member = database_models.ProjectMember(
            project_id=project.id,
            user_id=member.user_id,
            project_role=member.project_role
        )
        db.add(new_member)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print("Error adding project members:", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": "Project members added successfully"}


# get_all_users endpoint
@router.get("/get_all_user", response_model=List[modelsp.UserResponse])
async def get_all_user(db: Session = Depends(get_db)):
    users = db.query(database_models.Users).all()
    if not users:
        raise HTTPException(status_code=404, detail="No users found")
    return users



@router.get("/projects/{project_id}/files")
def get_project_files(
    project_id: int,
    db: Session = Depends(get_db),
    s3_client=Depends(s3_connection.get_s3_connection)  # ⬅ Inject S3 client from your utils module
):
    """
    Given a project ID:
    1️⃣ Fetch project name from DB
    2️⃣ List files from S3 working and finished directories
    3️⃣ Return signed URLs for both
    """

    BASE_PATH = "annotation/"

    # 1️⃣ Get project name from DB
    project = db.query(database_models.Project).filter(database_models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_name = project.name
    print(f"📁 Fetching files for project: {project_name}")

    # 2️⃣ Build S3 prefixes
    working_prefix = f"{BASE_PATH}{project_name}/working_directory/"
    finished_prefix = f"{BASE_PATH}{project_name}/finished_directory/"

    # 3️⃣ List files from both directories
    working_files = admin_helper.list_files_in_s3(s3_client, working_prefix)
    finished_files = admin_helper.list_files_in_s3(s3_client, finished_prefix)

    # 4️⃣ Generate signed URLs
    working_urls = [admin_helper.get_presigned_url(s3_client, key) for key in working_files]
    finished_urls = [admin_helper.get_presigned_url(s3_client, key) for key in finished_files]

    return {
        "project_name": project_name,
        "working_directory": working_urls,
        "finished_directory": finished_urls
    }