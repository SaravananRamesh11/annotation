from datetime import datetime, timezone, timedelta
import os
import random
from sqlalchemy.exc import SQLAlchemyError
import traceback
from fastapi import APIRouter, Request, Depends, HTTPException, status,File, UploadFile, Form,Query,Body
from botocore.exceptions import NoCredentialsError,ClientError
from sqlalchemy.orm import Session
from helper_functions import admin_helper
from models import modelsp,database_models
from database import get_db
from utils import s3_connection
from sqlalchemy import func, cast, Date


router = APIRouter(prefix="/api/employee", tags=["auth"])

AWS_ACCESS_KEY =os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION =   os.getenv("AWS_REGION")
BUCKET_NAME =  os.getenv("BUCKET_NAME")

IST = timezone(timedelta(hours=5, minutes=30))


@router.get("/user_projects/{user_id}")
def get_user_projects(user_id: str, db: Session = Depends(get_db)):

    # Join Projects with ProjectMember to pick up project_role too
    results = (
        db.query(
            database_models.Project,
            database_models.ProjectMember.project_role
        )
        .join(
            database_models.ProjectMember,
            database_models.Project.id == database_models.ProjectMember.project_id
        )
        .filter(database_models.ProjectMember.user_id == user_id)
        .all()
    )

    if not results:
        raise HTTPException(status_code=404, detail="No projects found for this user")

    # Build the response
    response = []
    for project, role in results:
        response.append({
            "project_id": project.id,
            "name": project.name,
            "description": project.description,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "role": role                
        })

    return response






@router.get("/{project_id}/assign-file/{employee_id}")
def assign_random_file(
    project_id: str,
    employee_id: str,
    db: Session = Depends(get_db),
    s3=Depends(s3_connection.get_s3_connection)
):
    # Step 1: Validate project
    project = (
        db.query(database_models.Project)
        .filter(database_models.Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Step 2: Validate user
    user = (
        db.query(database_models.Users)
        .filter(database_models.Users.id == employee_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Step 3: Ensure user is part of project
    member = (
        db.query(database_models.ProjectMember)
        .filter(
            database_models.ProjectMember.project_id == project_id,
            database_models.ProjectMember.user_id == employee_id
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=400, detail="User not part of this project")

    # Step 4: List RAW files from S3
    raw_prefix = f"annotation/{project.name}/working_directory/raw/"
    response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=raw_prefix)
    contents = response.get("Contents")

    if not contents:
        raise HTTPException(status_code=404, detail="No raw files available")

    # Step 5: Pick one file
    selected = random.choice(contents)
    raw_key = selected["Key"]                           # full path
    filename = os.path.basename(raw_key)
    assigned_key = f"annotation/{project.name}/working_directory/assigned/{filename}"

    # Step 6: Move raw → assigned in S3
    try:
        s3.copy_object(
            Bucket=BUCKET_NAME,
            CopySource={"Bucket": BUCKET_NAME, "Key": raw_key},
            Key=assigned_key
        )
        s3.delete_object(Bucket=BUCKET_NAME, Key=raw_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 move failed: {str(e)}")

    # Step 7: Update DB file record (use full key)
    file_record = (
        db.query(database_models.Files)
        .filter(
            database_models.Files.project_id == project_id,
            database_models.Files.s3_key == raw_key  # FULL PATH CHECK
        )
        .first()
    )

    if not file_record:
        raise HTTPException(status_code=404, detail="File record not found")

    file_record.s3_key = assigned_key   # SAVE full path
    file_record.status = "assigned"
    db.commit()
    db.refresh(file_record)

    # Step 8: Create annotation
    annotation = database_models.Annotations(
        file_id=file_record.id,
        user_id=user.id,
        assigned_by="random",
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)

    # Step 9: Return final URL
    file_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{assigned_key}"

    return {
        "message": "File assigned successfully",
        "employee_id": employee_id,
        "file_id": file_record.id,
        "annotation_id": annotation.id,
        "file_key": assigned_key,
        "file_url": file_url
    }


@router.get("/user/{user_id}/assigned-files")
def get_user_assigned_files(
    user_id: str,
    db: Session = Depends(get_db)
):
    try:
        # 1. Validate user
        user = (
            db.query(database_models.Users)
            .filter(database_models.Users.id == user_id)
            .first()
        )
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # 2. Fetch actionable annotations
        # Only files the employee needs to work on:
        # belief = False  → not submitted OR rejected
        annotations = (
            db.query(database_models.Annotations)
            .filter(
                database_models.Annotations.user_id == user_id,
                database_models.Annotations.belief == False
            )
            .all()
        )

        if not annotations:
            return []

        result = []

        # 3. Build response
        for annotation in annotations:
            file = annotation.file
            if not file:
                continue

            project = file.project
            if not project:
                continue

            full_s3_key = file.s3_key
            filename = os.path.basename(full_s3_key)

            object_url = (
                f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{full_s3_key}"
            )

            result.append({
                "file_id": file.id,
                "filename": filename,
                "project_id": project.id,
                "project_name": project.name,
                "assigned_by": annotation.assigned_by,
                "assigned_at": annotation.assigned_at,
                "review_cycle": annotation.review_cycle,
                "review_state": annotation.review_state,
                "object_url": object_url,
                "s3_key": full_s3_key
            })

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(e)}"
        )




@router.put("/save_annotation/{file_id}")
async def save_annotation(
    file_id: int,
    request: dict = Body(...),     # <= accept ANY JSON object
    db: Session = Depends(get_db)
):
    try:
        # Step 1: Fetch row for this file_id
        annotation_record = db.query(database_models.Annotations).filter(
            database_models.Annotations.file_id == file_id
        ).first()

        if not annotation_record:
            raise HTTPException(status_code=404, detail="Record not found for given file_id")

        # Step 2: Save raw data (supports all shapes: rectangle, polygon, polyline, etc.)
        annotation_record.data = request.get("data", [])   # <-- keep array as-is
        annotation_record.last_saved_at = datetime.now(timezone.utc)

        # Step 3: Commit
        db.commit()
        db.refresh(annotation_record)

        return {
            "message": "Annotation data saved successfully",
            "last_saved_at": annotation_record.last_saved_at
        }

    except Exception as e:
        db.rollback()
        print("Error saving annotation:", e)
        raise HTTPException(status_code=500, detail=f"Error saving annotation data: {str(e)}")



# Endpoint to get the saved annotation data for a file   
@router.get("/file/{file_id}/data")
def get_file_data(file_id: str, db: Session = Depends(get_db)):
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
    



@router.get("/projects/{project_id}/classes")
def get_project_classes(project_id: str, db: Session = Depends(get_db)):
    """
    Get all class names from a specific project by ID.
    """
    project = db.query(database_models.Project).filter(database_models.Project.id == project_id).first()
    print(project)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Return the list of classes
    return project.classes







@router.post("/submit")
def submit_file_for_review(
    request: modelsp.SubmitFileToReview,
    db: Session = Depends(get_db),
    s3=Depends(s3_connection.get_s3_connection)
):
    """
    Annotator submits or resubmits a file for review.
    Moves file from assigned → review folder in S3 only on first submission.
    """

    try:
        # 1️⃣ Fetch annotation entry
        annotation = (
            db.query(database_models.Annotations)
            .filter(
                database_models.Annotations.file_id == request.file_id,
                database_models.Annotations.user_id == request.user_id
            )
            .first()
        )
        if not annotation:
            raise HTTPException(status_code=404, detail="Annotation not found for this file and user.")

        # 2️⃣ Get project & file info
        file_obj = db.query(database_models.Files).filter(database_models.Files.id == request.file_id).first()
        if not file_obj:
            raise HTTPException(status_code=404, detail="File not found.")

        project = db.query(database_models.Project).filter(database_models.Project.id == request.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found.")

        # full S3 key directly stored in DB
        old_key = file_obj.s3_key
        filename = os.path.basename(old_key)

        # 3️⃣ Detect first submission
        is_first_submission = (
            annotation.review_cycle == 0 and
            annotation.review_state in ['not_reviewed']
            #annotation.review_state in ['not_reviewed', 'in_review']
        )

        # 4️⃣ Update annotation DB info
        if is_first_submission:
            annotation.review_state = 'not_reviewed'
            annotation.belief = True
            annotation.submitted_at = datetime.now(IST)
            if  annotation.review_cycle==0:
                print("the label count is",len(annotation.data))
                annotation.label_count=len(annotation.data)
            annotation.review_cycle += 1

            # 5️⃣ Move file in S3 — assigned → review
            new_key = f"annotation/{project.name}/working_directory/review/{filename}"

            try:
                s3.copy_object(
                    Bucket=BUCKET_NAME,
                    CopySource={"Bucket": BUCKET_NAME, "Key": old_key},
                    Key=new_key
                )
                s3.delete_object(Bucket=BUCKET_NAME, Key=old_key)

                # update DB with new key
                file_obj.s3_key = new_key

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to move file in S3: {str(e)}")

        else:
            # 6️⃣ Resubmission logic
            if annotation.review_state != 'rejected':
                raise HTTPException(status_code=400, detail="File is not rejected, cannot resubmit.")

            annotation.review_state = 'in_review'
            annotation.belief = True
            annotation.submitted_at = datetime.now(IST)
            annotation.review_cycle += 1
           


           

            # Reset last review decision
            review_record = (
                db.query(database_models.AnnotationReviews)
                .filter(database_models.AnnotationReviews.annotation_id == annotation.id)
                .order_by(database_models.AnnotationReviews.id.desc())
                .first()
            )
            if review_record:
                review_record.decision = None

        # 7️⃣ Ensure DB file status matches
        file_obj.status = 'review'

        db.commit()

        msg = (
            "File submitted for review (first submission)."
            if is_first_submission
            else f"File resubmitted for review (cycle {annotation.review_cycle})."
        )

        return {
            "message": msg,
            "file_id": file_obj.id,
            "review_cycle": annotation.review_cycle,
            "new_s3_key": file_obj.s3_key
        }

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error daaaaaaaaaaaa sarva: {str(e)}")

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")




@router.get("/rejected/{employee_id}/{project_id}")
def get_rejected_files(employee_id: str, project_id: str, db: Session = Depends(get_db)):
    """
    Get all rejected files for a specific employee in a given project.
    Now uses full S3 key stored in DB (no manual reconstruction).
    """

    project = (
        db.query(database_models.Project)
        .filter(database_models.Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fetch rejected files via annotation state
    rejected_files = (
        db.query(database_models.Files)
        .join(database_models.Annotations, database_models.Annotations.file_id == database_models.Files.id)
        .filter(
            database_models.Files.project_id == project_id,
            database_models.Annotations.user_id == employee_id,
            database_models.Annotations.review_state == "rejected"
        )
        .distinct(database_models.Files.id)
        .all()
    )

    if not rejected_files:
        raise HTTPException(status_code=404, detail="No rejected files found.")

    files_data = []
    for file in rejected_files:
        filename = file.s3_key.split("/")[-1]  # keep this, it's correct
        full_s3_key = file.s3_key             # use as-is

        # Correct object URL
        object_url = f"https://{BUCKET_NAME}.s3.eu-north-1.amazonaws.com/{full_s3_key}"

        files_data.append({
            "file_id": file.id,
            "filename": filename,
            "file_type": file.type,
            "status": file.status,
            "s3_key": full_s3_key,
            "object_url": object_url
        })

    return {
        "status": "rejected",
        "project_id": project_id,
        "employee_id": employee_id,
        "rejected_files_count": len(files_data),
        "files": files_data
    }


@router.get("/rejection/{file_id}")
def get_rejection_description(file_id: int, db: Session = Depends(get_db)):
    """
    Return the rejection_description JSON array for a given file_id.
    """

    annotation = (
        db.query(database_models.Annotations)
        .filter(database_models.Annotations.file_id == file_id)
        .first()
    )

    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found for this file.")
    # if annotation.rejection_description==None:
    #     return{

    #     }


    return {
        "file_id": file_id,
        "rejection_description": annotation.rejection_description or []
    }


@router.get("/weekly-labels/{project_id}/{user_id}")
def get_weekly_labels(
    project_id: str,
    user_id: str,
    week_offset: int = 0,
    db: Session = Depends(get_db),
):

    # -----------------------------------------
    # 1. Compute Monday → Sunday for the target week
    # -----------------------------------------
    today = datetime.now().date()

    # Monday of current week
    current_week_start = today - timedelta(days=today.weekday())

    # Adjust based on week_offset
    target_week_start = current_week_start + timedelta(days=week_offset * 7)
    target_week_end = target_week_start + timedelta(days=7)

    # -----------------------------------------
    # 2. Query: sum(label_count) grouped by day
    # -----------------------------------------
    raw_results = (
        db.query(
            cast(database_models.Annotations.submitted_at, Date).label("day"),
            func.sum(database_models.Annotations.label_count).label("total_labels")
        )
        .join(database_models.Files, database_models.Files.id == database_models.Annotations.file_id)
        .filter(database_models.Files.project_id == project_id)
        .filter(database_models.Annotations.user_id == user_id)
        .filter(database_models.Annotations.submitted_at >= target_week_start)
        .filter(database_models.Annotations.submitted_at < target_week_end)
        .group_by(cast(database_models.Annotations.submitted_at, Date))
        .all()
    )

    # Convert DB result → dictionary for quick lookup
    result_map = {str(row.day): row.total_labels for row in raw_results}

    # -----------------------------------------
    # 3. Build FULL week output (Mon-Sun), filling missing days with 0
    # -----------------------------------------
    weekly_data = {}
    day_ptr = target_week_start

    for _ in range(7):   # always 7 days
        day_str = str(day_ptr)
        weekly_data[day_str] = result_map.get(day_str, 0)
        day_ptr += timedelta(days=1)

    # -----------------------------------------
    # 4. Return result
    # -----------------------------------------
    return {
        "week_start": str(target_week_start),
        "week_end": str(target_week_end),
        "days": weekly_data
    }




@router.get("/weekly-records/{project_id}/{user_id}")
def get_weekly_records(
    project_id: str,
    user_id: str,
    week_offset: int = 0,
    db: Session = Depends(get_db),
):

    # -----------------------------------------
    # 1. Compute Monday → Sunday for the target week
    # -----------------------------------------
    today = datetime.now().date()

    # Monday of current week
    current_week_start = today - timedelta(days=today.weekday())

    # Apply week offset
    target_week_start = current_week_start + timedelta(days=week_offset * 7)
    target_week_end = target_week_start + timedelta(days=7)

    # -----------------------------------------
    # 2. Query: COUNT(*) grouped by date(submitted_at)
    # -----------------------------------------
    raw_results = (
        db.query(
            cast(database_models.Annotations.submitted_at, Date).label("day"),
            func.count(database_models.Annotations.id).label("record_count")
        )
        .join(database_models.Files, database_models.Files.id == database_models.Annotations.file_id)
        .filter(database_models.Files.project_id == project_id)
        .filter(database_models.Annotations.user_id == user_id)
        .filter(database_models.Annotations.submitted_at >= target_week_start)
        .filter(database_models.Annotations.submitted_at < target_week_end)
        .group_by(cast(database_models.Annotations.submitted_at, Date))
        .all()
    )

    # Convert to dictionary for quick lookup
    result_map = {str(r.day): r.record_count for r in raw_results}

    # -----------------------------------------
    # 3. Build output for ALL 7 days (fill zeros)
    # -----------------------------------------
    weekly_data = {}
    day_ptr = target_week_start

    for _ in range(7):
        day_str = str(day_ptr)
        weekly_data[day_str] = result_map.get(day_str, 0)
        day_ptr += timedelta(days=1)

    # -----------------------------------------
    # 4. Return final formatted result
    # -----------------------------------------
    return {
        "week_start": str(target_week_start),
        "week_end": str(target_week_end),
        "days": weekly_data
    }