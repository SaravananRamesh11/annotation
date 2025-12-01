from sqlalchemy.sql.elements import Null
import traceback     
from fastapi import APIRouter, Request, Depends, HTTPException, status,File, UploadFile, Form,Query
from sqlalchemy import and_, func, select, update,delete,exists,not_,cast
from sqlalchemy.orm import Session,aliased
from database import get_db
from sqlalchemy.dialects.postgresql import JSONB
from dotenv import load_dotenv
import  uuid,os,io
from sqlalchemy.exc import SQLAlchemyError
from utils import s3_connection
from botocore.exceptions import NoCredentialsError,ClientError
from models import modelsp,database_models
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import bcrypt
from fastapi.responses import JSONResponse
import pandas as pd
from helper_functions import admin_helper
import json
import random

load_dotenv()

AWS_ACCESS_KEY =os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION =   os.getenv("AWS_REGION")
BUCKET_NAME =  os.getenv("BUCKET_NAME")

router = APIRouter(prefix="/api/reviewer", tags=["auth"])

# @router.put("/accept-annotation")
# def accept_annotation(file_id: int, db: Session = Depends(get_db), s3=Depends(s3_connection.get_s3_connection)):

#     print("hello")

#     # Step 1️⃣: Find annotation by file_id
#     annotation = db.query(database_models.Annotations).filter(
#         database_models.Annotations.file_id == file_id
#     ).first()

#     if not annotation:
#         raise HTTPException(status_code=404, detail="Annotation not found for the given file_id")

#     # Step 2️⃣: Approve annotation
#     annotation.review_state = 'approved'
#     db.commit()
#     db.refresh(annotation)

#     # Step 3️⃣: Get file record
#     file_record = db.query(database_models.Files).filter(
#         database_models.Files.id == file_id
#     ).first()

#     if not file_record:
#         raise HTTPException(status_code=404, detail="File not found")

#     # Step 4️⃣: Get project
#     project = db.query(database_models.Project).filter(
#         database_models.Project.id == file_record.project_id
#     ).first()

#     if not project:
#         raise HTTPException(status_code=404, detail="Project not found for this file")

#     project_name = project.name
#     print("s3 key", file_record.s3_key)

#     # Step 5️⃣: Move file in S3
#     old_key = f"annotation/{project_name}/working_directory/review/{file_record.s3_key}"
#     new_key = f"annotation/{project_name}/finished_directory/completed/{file_record.s3_key}"

#     print("old", old_key, "new", new_key)

#     try:
#         s3.copy_object(
#             Bucket=BUCKET_NAME,
#             CopySource={"Bucket": BUCKET_NAME, "Key": old_key},
#             Key=new_key
#         )
#         s3.delete_object(Bucket=BUCKET_NAME, Key=old_key)
#     except ClientError as e:
#         raise HTTPException(status_code=500, detail=f"S3 operation failed: {str(e)}")

#     print("after the movement")

#     # Step 6️⃣: Update file status → completed
#     file_record.status = 'completed'
#     db.commit()

#     # Step 7️⃣: Update review record
#     review_record = db.query(database_models.AnnotationReviews).filter(
#         database_models.AnnotationReviews.annotation_id == annotation.id
#     ).first()

#     if not review_record:
#         raise HTTPException(status_code=404, detail="Review record not found for this annotation")

#     review_record.decision = 'approved'
#     review_record.reviewed_at = datetime.now()
#     db.commit()

#     # Step 8️⃣: Build label JSON (corrected completely)
#     annotation_rows = db.query(database_models.Annotations).filter(
#         database_models.Annotations.file_id == file_id
#     ).all()

#     if not annotation_rows:
#         raise HTTPException(status_code=404, detail="No annotations found for this file")

#     # Flatten JSON
#     annotation_list = []

#     for row in annotation_rows:
#         if not row.data:
#             continue

#         for item in row.data:        # item is a dict
#             annotation_list.append({
#                 "id": item.get("id"),
#                 "x": item.get("x"),
#                 "y": item.get("y"),
#                 "width": item.get("width"),
#                 "height": item.get("height"),
#                 "class_name": item.get("classes", {}).get("className"),
#                 "attribute": item.get("classes", {}).get("attribute"),
#             })

#    # Convert to JSON string (you can uncomment this if needed)
#     json_content = json.dumps(annotation_list, indent=4)

#     # Build JSON filename
#     base_name, _ = os.path.splitext(file_record.s3_key)
#     json_filename = f"{base_name}.json"

#     # S3 destination
#     json_key = f"annotation/{project_name}/labels/{json_filename}"

#     try:
#         s3.put_object(
#             Bucket=BUCKET_NAME,
#             Key=json_key,
#             Body=json_content,
#             ContentType="application/json"
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to upload JSON label file: {str(e)}")

#     return {
#         "message": f"Annotation approved and file moved to completed for project '{project_name}' successfully",
#         "annotation_id": annotation.id,
#         "file_id": file_id,
#         "old_s3_key": old_key,
#         "new_s3_key": new_key,
#         "new_status": file_record.status,
#         "label_count": len(annotation_list)
#     }




@router.put("/accept-annotation")
def accept_annotation(
    file_id: int,
    db: Session = Depends(get_db),
    s3=Depends(s3_connection.get_s3_connection)
):
    print("hello")

    # Step 1: Find annotation
    annotation = (
        db.query(database_models.Annotations)
        .filter(database_models.Annotations.file_id == file_id)
        .first()
    )
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found for the given file_id")

    # Step 2: Approve annotation
    annotation.review_state = 'approved'
    annotation.rejection_description=None
    db.commit()
    db.refresh(annotation)

    # Step 3: Get file record
    file_record = db.query(database_models.Files).filter(
        database_models.Files.id == file_id
    ).first()

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Step 4: Get project
    project = db.query(database_models.Project).filter(
        database_models.Project.id == file_record.project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found for this file")

    project_name = project.name

    # -------------------------------------------
    # FIX: Extract filename and current full key
    # -------------------------------------------

    old_key = file_record.s3_key                            # full existing key
    filename = os.path.basename(old_key)                   # only the file name

    # Build new key in completed folder
    new_key = f"annotation/{project_name}/finished_directory/completed/{filename}"

    print("old", old_key, "new", new_key)

    # Step 5: Move file in S3
    try:
        s3.copy_object(
            Bucket=BUCKET_NAME,
            CopySource={"Bucket": BUCKET_NAME, "Key": old_key},
            Key=new_key
        )
        s3.delete_object(Bucket=BUCKET_NAME, Key=old_key)
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 operation failed: {str(e)}")

    print("after the movement")

    # Update file record key
    file_record.s3_key = new_key
    file_record.status = 'completed'
    db.commit()

    # Step 7: Update review record
    review_record = db.query(database_models.AnnotationReviews).filter(
        database_models.AnnotationReviews.annotation_id == annotation.id
    ).first()

    if not review_record:
        raise HTTPException(status_code=404, detail="Review record not found for this annotation")

    review_record.decision = 'approved'
    review_record.reviewed_at = datetime.now()
    db.commit()

    # # Step 8: Build JSON labels
    # annotation_rows = db.query(database_models.Annotations).filter(
    #     database_models.Annotations.file_id == file_id
    # ).all()

    # if not annotation_rows:
    #     raise HTTPException(status_code=404, detail="No annotations found for this file")

    # annotation_list = []

    # for row in annotation_rows:
    #     if not row.data:
    #         continue

    #     for item in row.data:
    #         annotation_list.append({
    #             "id": item.get("id"),
    #             "x": item.get("x"),
    #             "y": item.get("y"),
    #             "width": item.get("width"),
    #             "height": item.get("height"),
    #             "class_name": item.get("classes", {}).get("className"),
    #             "attribute": item.get("classes", {}).get("attribute"),
    #         })

    # json_content = json.dumps(annotation_list, indent=4)






    annotation_rows = db.query(database_models.Annotations).filter(
        database_models.Annotations.file_id == file_id
    ).all()

    if not annotation_rows:
        raise HTTPException(status_code=404, detail="No annotations found for this file")

    # Combine all annotation.data arrays into one
    annotation_list = []

    for row in annotation_rows:
        if row.data:
            annotation_list.extend(row.data)   # ← DIRECTLY USE DB JSON

    json_content = json.dumps(annotation_list, indent=4)

    # Build JSON filename
    base_name = os.path.splitext(filename)[0]
    json_filename = f"{base_name}.json"

    json_key = f"annotation/{project_name}/labels/{json_filename}"

    try:
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=json_key,
            Body=json_content,
            ContentType="application/json"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload JSON label file: {str(e)}")

    return {
        "message": f"Annotation approved and file moved to completed successfully",
        "annotation_id": annotation.id,
        "file_id": file_id,
        "old_s3_key": old_key,
        "new_s3_key": new_key,
        "new_status": file_record.status,
        "label_count": len(annotation_list)
    }










# @router.get("/resubmitted-files/{project_id}/{reviewer_id}")
# def get_resubmitted_files(project_id: str, reviewer_id: str, db: Session = Depends(get_db)):
#     # Step 1: Verify reviewer is part of the project
#     reviewer_member = (
#         db.query(database_models.ProjectMember)
#         .filter_by(project_id=project_id, user_id=reviewer_id, project_role="reviewer")
#         .first()
#     )
#     if not reviewer_member:
#         raise HTTPException(
#             status_code=403,
#             detail="Reviewer is not part of this project"
#         )

#     # Step 2: Fetch resubmitted files (review_cycle > 1, belief=True)
#     # where the reviewer has reviewed previously and now the annotator has resubmitted
#     files = (
#         db.query(database_models.Files)
#         .join(database_models.Annotations, database_models.Annotations.file_id == database_models.Files.id)
#         .join(database_models.AnnotationReviews, database_models.AnnotationReviews.annotation_id == database_models.Annotations.id)
#         .filter(
#             database_models.Files.project_id == project_id,
#             database_models.AnnotationReviews.reviewer_id == reviewer_id,
#             database_models.Annotations.review_cycle > 1,
#             database_models.Annotations.belief == True
#         )
#         .distinct()
#         .all()
#     )

#     return files






# @router.put("/reject")
# def reject_file(request: modelsp.RejectFileFromReview, db: Session = Depends(get_db)):
#     """
#     Reject a file under review.
#     Marks review_state='rejected', sets belief=False,
#     updates AnnotationReviews.decision='rejected', and keeps file.status='review'.
#     """

#     annotation = (
#         db.query(database_models.Annotations)
#         .join(database_models.Files)
#         .filter(
#             database_models.Files.id == request.file_id,
#             database_models.Files.project_id == request.project_id,
#             database_models.Annotations.file_id == request.file_id,
#         )
#         .first()
#     )

#     if not annotation:
#         raise HTTPException(status_code=404, detail="Annotation not found for this file.")

#     if annotation.review_state != 'in_review':
#         raise HTTPException(status_code=400, detail="File not currently under review.")

#     # ❌ Remove increment here — do NOT increase review_cycle
#     annotation.belief = False
#     annotation.review_state = 'rejected'
#     annotation.submitted_at = datetime.utcnow()
#     annotation.rejection_description=request.rejection_description

#     file = db.query(database_models.Files).filter(database_models.Files.id == request.file_id).first()
#     if file:
#         file.status = 'review'

#     review_record = (
#         db.query(database_models.AnnotationReviews)
#         .filter(database_models.AnnotationReviews.annotation_id == annotation.id)
#         .first()
#     )
#     if review_record:
#         review_record.decision = 'rejected'
#         review_record.reviewed_at = datetime.utcnow()

#     db.commit()

#     return {
#         "message": "File rejected successfully.",
#         "file_id": request.file_id,
#         "review_cycle": annotation.review_cycle,
#         "belief": annotation.belief,
#         "review_state": annotation.review_state,
#     }

@router.put("/reject")
def reject_file(request: modelsp.RejectFileFromReview, db: Session = Depends(get_db)):
    """
    Reject a file under review.
    Appends a rejection entry into rejection_description (JSONB array),
    sets review_state='rejected', belief=False, and updates review record.
    """

    annotation = (
        db.query(database_models.Annotations)
        .join(database_models.Files)
        .filter(
            database_models.Files.id == request.file_id,
            database_models.Files.project_id == request.project_id,
            database_models.Annotations.file_id == request.file_id,
        )
        .first()
    )

    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found for this file.")

    if annotation.review_state != 'in_review':
        raise HTTPException(status_code=400, detail="File not currently under review.")

    # Convert Pydantic model → dict (THIS FIXES YOUR ERROR)
    new_rejection = request.rejection_description.model_dump()
    if isinstance(new_rejection["submitted_at"], datetime):
        new_rejection["submitted_at"] = new_rejection["submitted_at"].isoformat()

    # If rejection_description is empty, initialize it
    if annotation.rejection_description is None:
        annotation.rejection_description = [new_rejection]
    else:
        # Append using PostgreSQL JSONB concatenation
        from sqlalchemy import cast
        from sqlalchemy.dialects.postgresql import JSONB

        db.execute(
            database_models.Annotations.__table__.update()
            .where(database_models.Annotations.id == annotation.id)
            .values(
                rejection_description=
                    database_models.Annotations.rejection_description.op("||")(
                        cast([new_rejection], JSONB)
                    )
            )
        )

    # Update core annotation fields
    annotation.belief = False
    annotation.review_state = "rejected"
    annotation.submitted_at = datetime.utcnow()

    # Update file state
    file = db.query(database_models.Files).filter(
        database_models.Files.id == request.file_id
    ).first()
    if file:
        file.status = "review"

    # Update review record
    review_record = (
        db.query(database_models.AnnotationReviews)
        .filter(database_models.AnnotationReviews.annotation_id == annotation.id)
        .first()
    )
    if review_record:
        review_record.decision = "rejected"
        review_record.reviewed_at = datetime.utcnow()

    db.commit()

    return {
        "message": "File rejected successfully.",
        "file_id": request.file_id,
        "review_state": annotation.review_state,
        "rejection_appended": new_rejection,
    }





# @router.get("/review-files/{project_id}/{user_id}")
# def get_assigned_review_files(
#     project_id: str,
#     user_id: str,
#     db: Session = Depends(get_db)
# ):
#     """
#     Returns all files assigned to a reviewer (reviewer = user_id)
#     where annotation.review_state = 'in_review'.
#     Includes full S3 object URL.
#     """

#     # 1️⃣ Validate project
#     project = (
#         db.query(database_models.Project)
#         .filter(database_models.Project.id == project_id)
#         .first()
#     )
#     if not project:
#         raise HTTPException(status_code=404, detail="Project not found")

#     # 2️⃣ Fetch assigned files
#     assigned_files = (
#         db.query(database_models.Files)
#         .join(database_models.Annotations, database_models.Annotations.file_id == database_models.Files.id)
#         .join(database_models.AnnotationReviews, database_models.AnnotationReviews.annotation_id == database_models.Annotations.id)
#         .filter(
#             database_models.Files.project_id == project_id,
#             database_models.AnnotationReviews.reviewer_id == user_id,
#             database_models.Annotations.review_state == 'in_review'
#         )
#         .all()
#     )

#     if not assigned_files:
#         raise HTTPException(status_code=404, detail="No assigned review files found.")

#     files_output = []

#     for file in assigned_files:
#         s3_key = file.s3_key  # already full path, don’t reconstruct

#         object_url = f"https://{BUCKET_NAME}.s3.eu-north-1.amazonaws.com/{s3_key}"

#         files_output.append({
#             "file_id": file.id,
#             "filename": os.path.basename(s3_key),
#             "file_type": file.type,
#             "status": file.status,
#             "s3_key": s3_key,
#             "object_url": object_url
#         })

#     return {
#         "status": "assigned_for_review",
#         "project_id": project_id,
#         "reviewer_id": user_id,
#         "assigned_files_count": len(files_output),
#         "files": files_output
#     }





    
# @router.get("/review-files/{project_id}/{user_id}")
# def get_assigned_review_files(
#     project_id: str,
#     user_id: str,
#     db: Session = Depends(get_db)
# ):
#     """
#     Returns all files assigned to a reviewer (reviewer = user_id)
#     where annotation.review_state = 'in_review'.
#     Includes full S3 object URL and review cycle (to differentiate resubmissions).
#     """

#     # 1️⃣ Validate project
#     project = (
#         db.query(database_models.Project)
#         .filter(database_models.Project.id == project_id)
#         .first()
#     )
#     if not project:
#         raise HTTPException(status_code=404, detail="Project not found")

#     # 2️⃣ Fetch all files assigned to reviewer for review
#     assigned_files = (
#         db.query(database_models.Files, database_models.Annotations)
#         .join(database_models.Annotations, database_models.Annotations.file_id == database_models.Files.id)
#         .join(database_models.AnnotationReviews, database_models.AnnotationReviews.annotation_id == database_models.Annotations.id)
#         .filter(
#             database_models.Files.project_id == project_id,
#             database_models.AnnotationReviews.reviewer_id == user_id,
#             database_models.Annotations.review_state == 'in_review'
#         )
#         .all()
#     )

#     if not assigned_files:
#         return []

#     files_output = []

#     for file_obj, annotation in assigned_files:
#         s3_key = file_obj.s3_key  # already full path

#         object_url = f"https://{BUCKET_NAME}.s3.eu-north-1.amazonaws.com/{s3_key}"

#         files_output.append({
#             "file_id": file_obj.id,
#             "assigned_by_annotation":annotation.assigned_by,
#             "filename": os.path.basename(s3_key),
#             "file_type": file_obj.type,
#             "status": file_obj.status,
#             "s3_key": s3_key,
#             "object_url": object_url,
#             "review_cycle": annotation.review_cycle,  # include cycle
#             "annotation_id": annotation.id
#         })

#         print("hi from sarva",files_output)

#     return {
#         "status": "assigned_for_review",
#         "project_id": project_id,
#         "reviewer_id": user_id,
#         "assigned_files_count": len(files_output),
#         "files": files_output
#     }




@router.get("/review-files/{project_id}/{user_id}")
def get_assigned_review_files(
    project_id: str,
    user_id: str,
    db: Session = Depends(get_db)
):
    # Validate project
    project = (
        db.query(database_models.Project)
        .filter(database_models.Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fetch files + annotation + annotation_review
    assigned_files = (
        db.query(
            database_models.Files,
            database_models.Annotations,
            database_models.AnnotationReviews
        )
        .join(
            database_models.Annotations,
            database_models.Annotations.file_id == database_models.Files.id
        )
        .join(
            database_models.AnnotationReviews,
            database_models.AnnotationReviews.annotation_id == database_models.Annotations.id
        )
        .filter(
            database_models.Files.project_id == project_id,
            database_models.AnnotationReviews.reviewer_id == user_id,
            database_models.Annotations.review_state == "in_review"
        )
        .all()
    )

    if not assigned_files:
        return {
            "status": "assigned_for_review",
            "project_id": project_id,
            "reviewer_id": user_id,
            "assigned_files_count": 0,
            "files": []
        }

    files_output = []

    for file_obj, annotation, annotation_review in assigned_files:
        s3_key = file_obj.s3_key

        object_url = (
            f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
        )

        files_output.append({
            "file_id": file_obj.id,
            "assigned_by_annotation": annotation.assigned_by,     # old
            "assigned_by_review": annotation_review.assigned_by,  # NEW
            "filename": os.path.basename(s3_key),
            "file_type": file_obj.type,
            "status": file_obj.status,
            "s3_key": s3_key,
            "object_url": object_url,
            "review_cycle": annotation.review_cycle,
            "annotation_id": annotation.id
        })

    return {
        "status": "assigned_for_review",
        "project_id": project_id,
        "reviewer_id": user_id,
        "assigned_files_count": len(files_output),
        "files": files_output
    }









# @router.get("/review/assign-random/{project_id}/{reviewer_id}")
# def assign_random_review_file(
#     project_id: str,
#     reviewer_id: str,
#     db: Session = Depends(get_db)
# ):
#     # 1. Validate reviewer
#     reviewer = db.query(Users).filter(Users.id == reviewer_id).first()
#     if not reviewer:
#         print("no reviewer")
#         raise HTTPException(status_code=404, detail="Reviewer not found.")

#     # 2. Find all unassigned random review files for this project
#     candidates = (
#         db.query(Annotations)
#         .join(Files, Files.id == Annotations.file_id)
#         .filter(
#             Files.project_id == project_id,
#             Annotations.assigned_by == "random",
#             Annotations.review_cycle == 0,
#             Annotations.review_state == "not_reviewed"
#         )
#         .all()
#     )

#     if not candidates:
#         print("no candidatess")
#         raise HTTPException(
#             status_code=404,
#             detail="No unassigned random review files available."
#         )

#     # 3. Select a random candidate
#     chosen = random.choice(candidates)
#     file_obj = chosen.file

#     # 4. Create a record in AnnotationReviews (assignment)
#     review_entry = AnnotationReviews(
#         annotation_id=chosen.id,
#         reviewer_id=reviewer_id,
#         decision=None,
#         comments=None
#     )

#     db.add(review_entry)

#     # 5. Update the annotation to mark it as "in review"
#     chosen.review_cycle = 1
#     chosen.review_state = "in_review"

#     try:
#         db.commit()
#     except Exception as e:
#         db.rollback()
#         print("DB ERROR:", e)
#         raise HTTPException(status_code=500, detail=str(e))

    

#     db.refresh(chosen)
#     db.refresh(review_entry)

#     # 6. Build S3 object URL
#     bucket = "intern-vista-work-space"
#     region = "eu-north-1"
#     object_url = f"https://{bucket}.s3.{region}.amazonaws.com/{file_obj.s3_key}"

#     # 7. Return response
#     return {
#         "status": "assigned_for_review",
#         "project_id": project_id,
#         "reviewer_id": reviewer_id,
#         "file": {
#             "file_id": file_obj.id,
#             "annotation_id": chosen.id,
#             "review_cycle": chosen.review_cycle,
#             "review_state": chosen.review_state,
#             "s3_key": file_obj.s3_key,
#             "file_url": object_url,
#         }
#     }





@router.get("/review/assign-random/{project_id}/{reviewer_id}")
def assign_random_review_file(
    project_id: str,
    reviewer_id: str,
    db: Session = Depends(get_db)
):
    # 1. Validate reviewer
    reviewer = db.query(database_models.Users).filter(database_models.Users.id == reviewer_id).first()
    if not reviewer:
        print("Reviewer not found")
        raise HTTPException(status_code=404, detail="Reviewer not found.")

    # 2. Find candidates
    candidates = (
        db.query(database_models.Annotations)
        .join(database_models.Files, database_models.Files.id == database_models.Annotations.file_id)
        .filter(
            database_models.Files.project_id == project_id,
            #database_models.Annotations.assigned_by == "random",
            database_models.Annotations.review_cycle == 1,
            database_models.Annotations.review_state == "not_reviewed"
        )
        .all()
    )

    if not candidates:
        print("No candidate random review files")
        raise HTTPException(status_code=404, detail="No unassigned random review files available.")

    # 3. Random selection
    chosen = random.choice(candidates)
    file_obj = chosen.file

    if not file_obj:
        print("Annotation has no file mapped:", chosen.id)
        raise HTTPException(status_code=500, detail="Broken annotation → file not found")

    # 4. Create review entry
    review_entry = database_models.AnnotationReviews(
        annotation_id=chosen.id,
        reviewer_id=reviewer_id,
        decision=None,
        comments=None,
        assigned_by="random"
    )

    db.add(review_entry)

    # 5. Update annotation
    chosen.review_cycle = 1
    chosen.review_state = "in_review"

    # 6. Commit safely
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        print("DB ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))

    db.refresh(chosen)
    db.refresh(review_entry)

    # Build S3 URL
    bucket = "intern-vista-work-space"
    region = "eu-north-1"
    object_url = f"https://{bucket}.s3.{region}.amazonaws.com/{file_obj.s3_key}"

    # 7. Return
    return {
        "status": "assigned_for_review",
        "project_id": project_id,
        "reviewer_id": reviewer_id,
        "file": {
            "file_id": file_obj.id,
            "annotation_id": chosen.id,
            "review_cycle": chosen.review_cycle,
            "review_state": chosen.review_state,
            "s3_key": file_obj.s3_key,
            "object_url": object_url,
        }
    }


@router.get("/review/unassigned/{project_id}")
def get_unassigned_random_review_files(
    project_id: str,
    db: Session = Depends(get_db)
):
    # 1. Query all unassigned review files for this project
    unassigned = (
        db.query(database_models.Annotations)
        .join(database_models.Files, database_models.Files.id == database_models.Annotations.file_id)
        .filter(
            database_models.Files.project_id == project_id,
            database_models.Annotations.assigned_by == "random",
            database_models.Annotations.review_cycle == 1,
            database_models.Annotations.review_state == "not_reviewed"
        )
        .all()
    )

    # 2. If none found
    if not unassigned:
        return {
            "project_id": project_id,
            "count": 0,
            "files": []
        }

    # 3. Build S3 URL for each file
    bucket = "intern-vista-work-space"
    region = "eu-north-1"

    result_files = []
    for annotation in unassigned:
        file_obj = annotation.file
        object_url = f"https://{bucket}.s3.{region}.amazonaws.com/{file_obj.s3_key}"

        result_files.append({
            "file_id": file_obj.id,
            "annotation_id": annotation.id,
            "s3_key": file_obj.s3_key,
            "object_url": object_url,
            "review_cycle": annotation.review_cycle,
            "review_state": annotation.review_state,
        })

    # 4. Return list
    return {
        "project_id": project_id,
        "count": len(result_files),
        "files": result_files
    }
