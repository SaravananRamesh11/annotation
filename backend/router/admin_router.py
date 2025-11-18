import traceback
from fastapi import APIRouter, Request, Depends, HTTPException, status,File, UploadFile, Form,Query
from sqlalchemy import and_, func, select, update,delete,exists,not_
from sqlalchemy.orm import Session,aliased
from database import get_db
from sqlalchemy.dialects.postgresql import JSONB
from dotenv import load_dotenv
import  uuid,os,io
from utils import s3_connection
from botocore.exceptions import NoCredentialsError,ClientError
from models import modelsp,database_models
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import bcrypt
from fastapi.responses import JSONResponse
import pandas as pd
from helper_functions import admin_helper
from sqlalchemy.exc import SQLAlchemyError
from uuid import UUID








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

            s3_keyy = f"annotation/{project_name}/working_directory/raw/{unique_name}"


            file.file.seek(0)
            s3_client.upload_fileobj(
                file.file,
                BUCKET_NAME,
                s3_keyy,
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

            file_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_keyy}"
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
            .filter(database_models.Users.id == user.id)
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
            id=user.id,
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
            project_role="annotator"
        )
        db.add(new_member)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print("Error adding project members:", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": "Project members added successfully"}


# delete_project endpoint
@router.delete( "/delete_project/{project_id}")
async def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    s3_client=Depends(s3_connection.get_s3_connection)
):
    """
    Delete a project and all its associated data:
    1. Delete project from database (cascade deletes members, files, annotations)
    2. Delete project folder from S3
    """
    try:
        # 1. Get project details before deletion
        project = db.query(database_models.Project).filter(database_models.Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        project_name = project.name
        print(f"🗑️ Deleting project: {project_name} (ID: {project_id})")
        
        # 2. Delete project from database (cascade will handle related records)
        db.delete(project)
        db.commit()
        print(f"✅ Project {project_name} deleted from database")
        
        # 3. Delete project folder from S3
        BASE_PATH = "annotation/"
        project_prefix = f"{BASE_PATH}{project_name}/"
        
        try:
            # List all objects with the project prefix
            paginator = s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=BUCKET_NAME, Prefix=project_prefix)
            
            objects_to_delete = []
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_delete.append({'Key': obj['Key']})
            
            # Delete all objects in the project folder
            if objects_to_delete:
                s3_client.delete_objects(
                    Bucket=BUCKET_NAME,
                    Delete={
                        'Objects': objects_to_delete,
                        'Quiet': False
                    }
                )
                print(f"✅ Deleted {len(objects_to_delete)} objects from S3 folder: {project_prefix}")
            else:
                print(f"ℹ️ No objects found in S3 folder: {project_prefix}")
                
        except ClientError as e:
            print(f"⚠️ Error deleting S3 folder {project_prefix}: {e}")
            # Don't raise exception here as database deletion was successful
            # Just log the S3 error
        
        return {
            "message": f"Project '{project_name}' deleted successfully",
            "project_id": project_id,
            "project_name": project_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Error deleting project: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Failed to delete project: {str(e)}"
        )


# get_all_users endpoint
@router.get("/get_all_user", response_model=List[modelsp.UserResponse])
async def get_all_user(db: Session = Depends(get_db)):
    users = db.query(database_models.Users).all()
    if not users:
        raise HTTPException(status_code=404, detail="No users found")
    return users


@router.get("/projects/{project_id}/files")
def get_project_files(
    project_id: UUID,
    db: Session = Depends(get_db),
    s3_client=Depends(s3_connection.get_s3_connection)
):
    """
    Given a project ID:
    1️⃣ Fetch project name from DB
    2️⃣ List files from S3 working and finished directories with subfolders
    3️⃣ Return signed URLs for all subfolders
    """

    BASE_PATH = "annotation/"

    # 1️⃣ Get project name from DB
    project = db.query(database_models.Project).filter(database_models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project_name = project.name
    print(f"📁 Fetching files for project: {project_name}")

    # 2️⃣ Define subfolder prefixes
    working_prefixes = {
        "raw": f"{BASE_PATH}{project_name}/working_directory/raw/",
        "review": f"{BASE_PATH}{project_name}/working_directory/review/",
        "assigned": f"{BASE_PATH}{project_name}/working_directory/assigned/"
    }

    finished_prefixes = {
        "completed": f"{BASE_PATH}{project_name}/finished_directory/completed/"
    }

    # 3️⃣ List files and generate signed URLs for working subfolders
    working_urls = {}
    for folder_name, prefix in working_prefixes.items():
        files = admin_helper.list_files_in_s3(s3_client, prefix)
        working_urls[folder_name] = [admin_helper.get_presigned_url(s3_client, key) for key in files]

    # 4️⃣ List files and generate signed URLs for finished subfolders
    finished_urls = {}
    for folder_name, prefix in finished_prefixes.items():
        files = admin_helper.list_files_in_s3(s3_client, prefix)
        finished_urls[folder_name] = [admin_helper.get_presigned_url(s3_client, key) for key in files]

    # 5️⃣ Return structured response
    return {
        "project_name": project_name,
        "working_directory": working_urls,
        "finished_directory": finished_urls
    }


@router.get("/projects/{project_id}/task-counts")
def get_task_counts_by_status(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Get task counts for all statuses in a project.
    Useful for displaying counts in the dropdown filter UI.
    """
    # 1️⃣ Verify project exists
    project = db.query(database_models.Project).filter(database_models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 2️⃣ Get counts for each status
    counts = {
        "raw": db.query(database_models.Files).filter(
            database_models.Files.project_id == project_id,
            database_models.Files.status == "pending"
        ).count(),
        "assigned": db.query(database_models.Files).filter(
            database_models.Files.project_id == project_id,
            database_models.Files.status == "assigned"
        ).count(),
        "review": db.query(database_models.Files).filter(
            database_models.Files.project_id == project_id,
            database_models.Files.status == "review"
        ).count(),
        "completed": db.query(database_models.Files).filter(
            database_models.Files.project_id == project_id,
            database_models.Files.status == "completed"
        ).count()
    }
    
    # 3️⃣ Calculate total
    total = sum(counts.values())
    
    return {
        "project_id": project_id,
        "project_name": project.name,
        "counts": counts,
        "total": total
    }


@router.get("/{project_id}/available-users")
def get_users_not_in_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    pm_alias = aliased(database_models.ProjectMember)
    query = (
        db.query(database_models.Users)
        .outerjoin(pm_alias, (pm_alias.user_id == database_models.Users.id) & (pm_alias.project_id == project_id))
        .filter(pm_alias.id.is_(None))
    )
    users = query.all()

    return [
        {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role   
         }
        for user in users
    ]


# Endpoint to assign multiple files to a annotator

#for using this in the frontend, first show all the files in a particular project. 
#side button allows the admin to assign the file to only one person at a time directs the admin to next page
#in the next page it shows all the annotators and reviewers in the project # #they can select one person and assign the file to that person
@router.post("/annotation_table")
def assign_multiple_annotations(
    request: modelsp.AnnotationRequest,
    db: Session = Depends(get_db),
    s3_client=Depends(s3_connection.get_s3_connection)
):
    """
    Assign multiple files to a single employee.
    request.file_ids -> list of file IDs
    request.user_id  -> employee (annotator) ID
    """
    try:
        assigned_annotations = []

        # Loop through each file in the list
        for file_id in request.file_ids:
            # Step 1: Check if this file is already assigned
            existing_annotation = db.execute(
                select(database_models.Annotations).where(database_models.Annotations.file_id == file_id)
            ).scalar_one_or_none()

            if existing_annotation:
                raise HTTPException(
                    status_code=400,
                    detail=f"File ID {file_id} is already assigned to User ID {existing_annotation.user_id}"
                )

            # Step 2: Fetch the file record from DB
            file_record = db.query(database_models.Files).filter(database_models.Files.id == file_id).first()
            if not file_record:
                raise HTTPException(status_code=404, detail=f"File ID {file_id} not found")

            # Step 2b: Fetch the project name from Project table using project_id
            project = db.query(database_models.Project).filter(database_models.Project.id == file_record.project_id).first()
            if not project:
                raise HTTPException(status_code=404, detail=f"Project for File ID {file_id} not found")
            project_name = project.name

            # Step 3: Create new annotation entry
            new_annotation = database_models.Annotations(
                file_id=file_id,
                user_id=request.user_id,
                assigned_at=datetime.now(timezone.utc),
                data=None,
                assigned_by='admin',
                last_saved_at=datetime.now(timezone.utc),
                submitted_at=None
            )
            db.add(new_annotation)

            # Step 4: Update file status to 'assigned'
            db.execute(
                update(database_models.Files)
                .where(database_models.Files.id == file_id)
                .values(status="assigned")
            )

            # --- Step 5: Move file in S3 from raw → assigned ---
            filename = os.path.basename(file_record.s3_key)
            raw_key = f"annotation/{project_name}/working_directory/raw/{filename}"
            assigned_key = f"annotation/{project_name}/working_directory/assigned/{filename}"

            try:
                # Check if raw file exists
                s3_client.head_object(Bucket=BUCKET_NAME, Key=raw_key)

                # Copy to assigned folder
                s3_client.copy_object(
                    Bucket=BUCKET_NAME,
                    CopySource={'Bucket': BUCKET_NAME, 'Key': raw_key},
                    Key=assigned_key
                )

                # Delete from raw folder
                s3_client.delete_object(Bucket=BUCKET_NAME, Key=raw_key)
                print(f"✅ Moved S3 file {raw_key} → {assigned_key}")

            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    raise HTTPException(status_code=404, detail=f"S3 file not found: {raw_key}")
                else:
                    raise HTTPException(status_code=500, detail=f"Failed to move file in S3: {str(e)}")

            assigned_annotations.append(file_id)

        # Step 6: Commit transaction once after all assignments
        db.commit()

        return {
            "message": "Annotations created successfully",
            "total_assigned": len(assigned_annotations),
            "file_ids": assigned_annotations,
            "assigned_to": request.user_id
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))



# end point to get annotators for a project, excluding those with multiple roles(editor)
@router.get("/annotators/{project_id}", response_model=list[modelsp.AnnotatorOut])
def get_annotators(project_id: UUID, db: Session = Depends(get_db)):
    try:
        # Subquery: Find user_ids who have multiple roles in the same project
        multi_role_users = db.query(database_models.ProjectMember.user_id).filter(
            database_models.ProjectMember.project_id == project_id
        ).group_by(database_models.ProjectMember.user_id).having(
            func.count(database_models.ProjectMember.project_role) > 1
        ).subquery()

        # Main query: Get annotators who are NOT in the multi-role list
        annotators = db.query(database_models.ProjectMember).filter(
            database_models.ProjectMember.project_id == project_id,
            database_models.ProjectMember.project_role == "annotator",
            ~database_models.ProjectMember.user_id.in_(multi_role_users)
        ).all()

        if not annotators:
            raise HTTPException(status_code=404, detail="No annotators found for this project")

        return [modelsp.AnnotatorOut.from_orm(a) for a in annotators]

    except Exception as e:
        print("❌ ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))
    
# endpoint for promoting multiple annotators
@router.put("/annotators/{project_id}/promote", response_model=dict)
def promote_multiple_annotators_to_editors(project_id: UUID, request: modelsp.PromoteRequest, db: Session = Depends(get_db)):
    try:
        # Update all annotators in the given list
        updated_count = db.query(database_models.ProjectMember).filter(
            database_models.ProjectMember.project_id == project_id,
            database_models.ProjectMember.user_id.in_(request.user_ids),
            database_models.ProjectMember.project_role == "annotator"
        ).update({database_models.ProjectMember.project_role: "editor"}, synchronize_session=False)

        if updated_count == 0:
            raise HTTPException(status_code=404, detail="No matching annotators found to update")

        db.commit()

        return {"message": f"{updated_count} annotator(s) promoted to editor successfully"}

    except Exception as e:
        print("❌ ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))
    

# endpoint to display all the members in project    
@router.get("/{project_id}/members", response_model=dict)
def get_project_members(project_id:UUID, db: Session = Depends(get_db)):
    try:
        # Step 1: Join ProjectMember and Users tables
        members = (
            db.query(
                database_models.ProjectMember.user_id,
                database_models.Users.name,
                database_models.ProjectMember.project_role
            )
            .join(
                database_models.Users,
                database_models.Users.id == database_models.ProjectMember.user_id
            )
            .filter(database_models.ProjectMember.project_id == project_id)
            .all()
        )

        # Step 2: Handle no results found
        if not members:
            raise HTTPException(status_code=404, detail="No members found for this project")

        # Step 3: Format members list
        member_list = [
            {
                "user_id": member.user_id,
                "name": member.name,
                "project_role": member.project_role
            }
            for member in members
        ]

        # Step 4: Return both count and members
        return {
            
            "members": member_list
        }

    except Exception as e:
        print("❌ ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))



@router.delete("/remove_members")
def remove_members(request: modelsp.DeleteMembersRequest, db: Session = Depends(get_db)):
    if not request.user_ids:
        return {"message": "No user IDs provided."}

    result = db.execute(
        delete(database_models.ProjectMember)
        .where(database_models.ProjectMember.project_id == request.project_id)
        .where(database_models.ProjectMember.user_id.in_(request.user_ids))
    )
    db.commit()
    return {"message": f"{result.rowcount} members deleted successfully."}



############################################################################reviewer##############################################################

@router.get("/project/{project_id}/unassigned-reviews")
def get_unassigned_review_files(
    project_id: UUID,
    db: Session = Depends(get_db)
):
    # Fetch files that are in review and not yet reviewed
    results = (
        db.query(database_models.Files)
        .join(
            database_models.Annotations,
            database_models.Files.id == database_models.Annotations.file_id
        )
        .filter(
            database_models.Files.project_id == project_id,
            database_models.Files.status == "review",
            database_models.Annotations.review_state == "not_reviewed"
        )
        .all()
    )

    # Build actual S3 URL for each file
    file_urls = []
    for file in results:
        if not file.s3_key:
            continue  # skip invalid rows

        # file.s3_key only holds "abc123.png" — you must rebuild the full path
        # review files live inside: annotation/<project_name>/working_directory/review/<filename>

        project = (
            db.query(database_models.Project)
            .filter(database_models.Project.id == project_id)
            .first()
        )
        if not project:
            continue

        project_name = project.name

        # Construct full S3 path
        s3_key_full = f"annotation/{project_name}/working_directory/review/{file.s3_key}"

        # Construct public S3 URL
        file_url = (
            f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key_full}"
        )

        file_urls.append(file_url)

    return {
        "project_id": project_id,
        "count": len(file_urls),
        "unassigned_review_files": file_urls
    }



@router.get("/projects/{project_id}/editors")
def get_project_editors(project_id: UUID, db: Session = Depends(get_db)):
    """
    Fetch all editors (user_id and name) for a given project.
    Uses subquery approach instead of join to ensure all reviewers are returned.
    """
    try:
        # Step 1: Get all user_ids with role "reviewer" for this project
        reviewer_user_ids = (
            db.query(database_models.ProjectMember.user_id)
            .filter(
                and_(
                    database_models.ProjectMember.project_id == project_id,
                    database_models.ProjectMember.project_role == "reviewer"
                )
            )
            .all()
        )

        print("from sarva",reviewer_user_ids )

        # Flatten list of tuples -> list of IDs
        reviewer_user_ids = [r[0] for r in reviewer_user_ids]

        if not reviewer_user_ids:
            raise HTTPException(status_code=404, detail="No editors found for this project")

        # Step 2: Fetch user details for those IDs
        editors = (
            db.query(database_models.Users.id.label("user_id"), database_models.Users.name)
            .filter(database_models.Users.id.in_(reviewer_user_ids))
            .all()
        )

        if not editors:
            raise HTTPException(status_code=404, detail="No editor users found in Users table")

        # Step 3: Format output
        result = [{"user_id": e.user_id, "name": e.name} for e in editors]

        return {"project_id": project_id, "editors": result}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Endpoint to assign multiple files to reviewer
@router.post("/reviews/link/{reviewer_id}")
def link_multiple_annotations_to_reviewer(
    reviewer_id: str,
    file_ids: List[int],
    db: Session = Depends(get_db)
):
    """
    Assign multiple files to a reviewer by linking each file's annotation
    to the reviewer in the annotation_reviews table.
    """

    try:
        if not file_ids:
            raise HTTPException(status_code=400, detail="file_ids list cannot be empty")

        created_links = []

        for file_id in file_ids:
            # Step 1️⃣: Find the annotation for each file_id
            annotation = (
                db.query(database_models.Annotations)
                .filter(database_models.Annotations.file_id == file_id)
                .first()
            )

            if not annotation:
                # Skip missing annotations, but continue for others
                continue

            # Step 2️⃣: Check if this reviewer is already linked to this annotation
            existing_review = (
                db.query(database_models.AnnotationReviews)
                .filter(
                    database_models.AnnotationReviews.annotation_id == annotation.id,
                    database_models.AnnotationReviews.reviewer_id == reviewer_id
                )
                .first()
            )

            if existing_review:
                # Avoid duplicate entries
                continue

            # Step 3️⃣: Create new review entry
            new_review = database_models.AnnotationReviews(
                annotation_id=annotation.id,
                reviewer_id=reviewer_id
            )

            db.add(new_review)
            created_links.append({
                "annotation_id": annotation.id,
                "file_id": file_id
            })

        # Step 4️⃣: Commit all changes
        db.commit()

        if not created_links:
            raise HTTPException(status_code=400, detail="No new annotation links were created (may already exist or invalid file_ids)")

        return {
            "message": f"Successfully linked {len(created_links)} annotation(s) to reviewer {reviewer_id}",
            "created_links": created_links
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    



@router.get("/assign_review/{file_id}/{reviewer_id}")
def assign_file_for_review(
    file_id:int, reviewer_id:str,db: Session = Depends(get_db)
):
    """
    Admin assigns a file to a reviewer.
    Creates an entry in AnnotationReviews and updates annotation state.
    """
    print("hello world")
    try:
        # 1️⃣ Fetch the annotation record for the given file
        annotation = (
            db.query(database_models.Annotations)
            .filter(database_models.Annotations.file_id == file_id)
            .first()
        )
        if not annotation:
            raise HTTPException(status_code=404, detail="Annotation record not found for this file.")

        # # 2️⃣ Fetch reviewer (user)
        # reviewer = (
        #     db.query(database_models.Users)
        #     .filter(database_models.Users.id == reviewer_id)
        #     .first()
        # )
        # if not reviewer:
        #     raise HTTPException(status_code=404, detail="Reviewer not found.")

        # if reviewer.role != "reviewer":
        #     raise HTTPException(status_code=400, detail="Given user is not a reviewer.")

        # 3️⃣ Prevent multiple active reviews for the same annotation
        existing_review = (
            db.query(database_models.AnnotationReviews)
            .filter(
                database_models.AnnotationReviews.annotation_id == annotation.id,
                database_models.AnnotationReviews.decision.is_(None)
            )
            .first()
        )
        if existing_review:
            raise HTTPException(
                status_code=400,
                detail=f"Annotation {annotation.id} already has an active review assignment."
            )

        # 4️⃣ Create new AnnotationReviews record
        new_review = database_models.AnnotationReviews(
            annotation_id=annotation.id,
            reviewer_id=reviewer_id,
            decision=None,  # reviewer hasn’t decided yet
        )
        db.add(new_review)

        # 5️⃣ Update annotation review_state
        if annotation.review_state == "not_reviewed":
            annotation.review_state = "in_review"

        db.commit()

        return {
            "message": f"File ID {file_id} assigned to Reviewer ID {reviewer_id} successfully.",
            "annotation_id": annotation.id,
            "review_state": annotation.review_state
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    

@router.get("/project_name/{projectId}")
def project_name(projectId:UUID,db: Session = Depends(get_db)):
    project_name = (
    db.query(database_models.Project.name)
      .filter(database_models.Project.id == projectId)
      .scalar()
            )
    return project_name