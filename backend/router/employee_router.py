from datetime import datetime, timezone
import os
import random
import traceback
from fastapi import APIRouter, Request, Depends, HTTPException, status,File, UploadFile, Form,Query
#from pytz import timezone
from sqlalchemy.orm import Session
from helper_functions import admin_helper
from models import modelsp,database_models
from database import get_db
from utils import s3_connection
from models import database_models,modelsp

router = APIRouter(prefix="/api/employee", tags=["auth"])

AWS_ACCESS_KEY =os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION =   os.getenv("AWS_REGION")
BUCKET_NAME =  os.getenv("BUCKET_NAME")




@router.get("/user_projects/{user_id}")
def get_user_projects(user_id: str, db: Session = Depends(get_db)):
    # Step 1: Get all project IDs for this user from ProjectMember
    project_ids = (
        db.query(database_models.ProjectMember.project_id)
        .filter(database_models.ProjectMember.user_id == user_id)
        .all()
    )

    # Flatten list of tuples to a simple list of IDs
    project_ids = [pid[0] for pid in project_ids]

    if not project_ids:
        raise HTTPException(status_code=404, detail="No projects found for this user")

    # Step 2: Fetch all projects using the IDs
    projects = db.query(database_models.Project).filter(database_models.Project.id.in_(project_ids)).all()

    # Step 3: Return detailed project info
    return [
        {
            "project_id": project.id,
            "name": project.name,
            "description": project.description,
            "classes": project.classes,
            "created_at": project.created_at,
            "updated_at": project.updated_at
        }
        for project in projects
    ]



@router.get("/{project_id}/assign-file/{employee_id}")
def assign_random_file(
    project_id: int,
    employee_id: str,
    db: Session = Depends(get_db),
    s3=Depends(s3_connection.get_s3_connection)
):
    # Step 1: Validate project
    project = db.query(database_models.Project).filter(database_models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Step 2: Validate user
    user = db.query(database_models.Users).filter(database_models.Users.id == employee_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Step 3: Ensure user is part of the project
    project_member = (
        db.query(database_models.ProjectMember)
        .filter(
            database_models.ProjectMember.project_id == project_id,
            database_models.ProjectMember.user_id == employee_id
        )
        .first()
    )
    if not project_member:
        raise HTTPException(status_code=400, detail="User is not part of this project")

    # Step 4: List available raw files in S3
    project_prefix = f"annotation/{project.name}/working_directory/raw/"
    response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=project_prefix)
    contents = response.get("Contents")

    if not contents:
        raise HTTPException(status_code=404, detail="No files available in raw folder")

    # Step 5: Pick a random file
    selected_file = random.choice(contents)
    print("selected_file is",selected_file)
    file_key = selected_file["Key"]
    print("file_key is ",file_key)
    filename = os.path.basename(file_key)#actual file name in s3
    print("filename is",filename)
    assigned_key = f"annotation/{project.name}/working_directory/assigned/{filename}"
    print("assigned_key is",assigned_key) # same as file_key without annotation/ in the path

    



    

    # Step 6: Move file in S3 (copy + delete)
    try:
        s3.copy_object(
            Bucket=BUCKET_NAME,
            CopySource={"Bucket": BUCKET_NAME, "Key": file_key},
            Key=assigned_key
        )
        s3.delete_object(Bucket=BUCKET_NAME, Key=file_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to move file in S3: {str(e)}")

    # Step 7: Update the existing file record
    file_record = (
        db.query(database_models.Files)
        .filter(
            database_models.Files.project_id == project_id,
            database_models.Files.s3_key == filename
        )
        .first()
    )

    if not file_record:
        raise HTTPException(status_code=404, detail="File record not found in database")

    file_record.s3_key = assigned_key
    file_record.status = "assigned"
    db.commit()
    db.refresh(file_record)

    # Step 8: Create new annotation record
    new_annotation = database_models.Annotations(
        file_id=file_record.id,
        user_id=user.id,
        assigned_by="random"
    )
    db.add(new_annotation)
    db.commit()
    db.refresh(new_annotation)

    # Step 9: Return success response
    file_url = f"https://{BUCKET_NAME}.s3.eu-north-1.amazonaws.com/{assigned_key}"

    return {
        "message": "File assigned successfully",
        "employee_id": employee_id,
        "file_assigned": assigned_key,
        "file_url": file_url,
        "file_id": file_record.id,
        "annotation_id": new_annotation.id
    }






@router.get("/user/{user_id}/assigned-files")
def get_user_assigned_files(
    user_id: str,
    db: Session = Depends(get_db),
    s3=Depends(s3_connection.get_s3_connection)
):
    try:
        # Step 1: Validate user
        user = db.query(database_models.Users).filter(database_models.Users.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Step 2: Get all annotations created for this user
        annotations = (
            db.query(database_models.Annotations)
            .filter(database_models.Annotations.user_id == user_id)
            .all()
        )

        if not annotations:
            raise HTTPException(status_code=404, detail="No assigned files found for this user")

        result = []

        # Step 3: Iterate through annotations and fetch related file & project info
        for annotation in annotations:
            file = annotation.file
            if not file:
                continue

            project = file.project
            if not project:
                continue

            s3_key = file.s3_key  # already stores the full S3 path

            # Generate presigned S3 URL safely
            try:
                file_url = admin_helper.get_presigned_url(s3, s3_key)
            except Exception as e:
                print(f"Error generating presigned URL for {s3_key}: {e}")
                continue

            filename = os.path.basename(s3_key)

            # ✅ Include assigned_by and assigned_at fields
            result.append({
                "file_id": file.id,
                "filename": filename,
                "project_id": project.id,
                "project_name": project.name,
                "assigned_by": annotation.assigned_by,
                "assigned_at": annotation.assigned_at,
                "status": file.status,
                "object_url": file_url
            })

        if not result:
            raise HTTPException(status_code=404, detail="No assigned files found for this user")

        return result

    except HTTPException as he:
        raise he
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
    
# Endpoint to save annotation data for a file
@router.put("/save_annotation/{file_id}")
async def save_annotation(
    file_id: int,
    request: modelsp.SaveAnnotationData,
    db: Session = Depends(get_db)
):
    try:
        # Step 1: Find the annotation record with the given file_id
        annotation_record = db.query(database_models.Annotations).filter(
            database_models.Annotations.file_id == file_id
        ).first()

        if not annotation_record:
            raise HTTPException(status_code=404, detail="Record not found for given file_id")

        # Step 2: Convert Pydantic models to dict and update data + timestamp
        annotation_record.data = [bbox.dict() for bbox in request.data]
        annotation_record.last_saved_at = datetime.now(timezone.utc)

        # Step 3: Commit changes
        db.commit()
        db.refresh(annotation_record)

        return {
            "message": "Annotation data saved successfully",
            "last_saved_at": annotation_record.last_saved_at
        }

    except HTTPException:
        # Re-raise FastAPI HTTPExceptions (like 404)
        raise
    except Exception as e:
        db.rollback()
        print("Error saving annotation:", e)
        raise HTTPException(status_code=500, detail=f"Error saving annotation data: {str(e)}")

# Endpoint to get the saved annotation data for a file   
@router.get("/file/{file_id}/data")
def get_file_data(file_id: int, db: Session = Depends(get_db)):
    """
    Fetch the 'data' and 'last_saved_at' fields for a given file_id.
    """
    try:
        # Fetch the record by file_id
        record = (
            db.query(database_models.Annotations)
            .filter(database_models.Annotations.file_id == file_id)
            .first()
        )

        if not record:
            raise HTTPException(status_code=404, detail="File not found")

        return {
            "file_id": file_id,
            "data": record.data,
            "last_saved_at": record.last_saved_at
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
