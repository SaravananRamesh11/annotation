import traceback
from fastapi import APIRouter, Request, Depends, HTTPException, status,File, UploadFile, Form,Query
from sqlalchemy import and_, func, select, update,delete,exists,not_
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

load_dotenv()

AWS_ACCESS_KEY =os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION =   os.getenv("AWS_REGION")
BUCKET_NAME =  os.getenv("BUCKET_NAME")

router = APIRouter(prefix="/api/reviewer", tags=["auth"])

@router.put("/accept-annotation")
def accept_annotation(file_id: int, db: Session = Depends(get_db), s3=Depends(s3_connection.get_s3_connection)):
    # Step 1️⃣: Find annotation by file_id
    annotation = db.query(database_models.Annotations).filter(
        database_models.Annotations.file_id == file_id
    ).first()

    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found for the given file_id")

    # Step 2️⃣: Update annotation review_state → 'approved'
    annotation.review_state = 'approved'
    db.commit()
    db.refresh(annotation)

    # Step 3️⃣: Fetch the file record
    file_record = db.query(database_models.Files).filter(
        database_models.Files.id == file_id
    ).first()

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Step 4️⃣: Fetch associated project
    project = db.query(database_models.Project).filter(
        database_models.Project.id == file_record.project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found for this file")

    project_name = project.name
    print("s3 key",file_record.s3_key)

    # Step 5️⃣: Move file in S3 (from review → completed)
    old_key = f"annotation/{project_name}/working_directory/review/{file_record.s3_key}"
    new_key = f"annotation/{project_name}/finished_directory/completed/{file_record.s3_key}"
    print("old",old_key,"new",new_key)
    try:
        # Copy file to new path
        s3.copy_object(
            Bucket=BUCKET_NAME,
            CopySource={"Bucket": BUCKET_NAME, "Key": old_key},
            Key=new_key
        )

        # Delete the file from old location
        s3.delete_object(Bucket=BUCKET_NAME, Key=old_key)
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 operation failed: {str(e)}")

    # Step 6️⃣: Update file status → 'completed'
    file_record.status = 'completed'
    db.commit()

    # Step 7️⃣: Update annotation_reviews decision → 'approved'
    review_record = db.query(database_models.AnnotationReviews).filter(
        database_models.AnnotationReviews.annotation_id == annotation.id
    ).first()

    if not review_record:
        raise HTTPException(status_code=404, detail="Review record not found for this annotation")

    review_record.decision = 'approved'
    review_record.reviewed_at = datetime.now()
    db.commit()

    return {
        "message": f"Annotation approved and file moved to completed for project '{project_name}' successfully",
        "annotation_id": annotation.id,
        "file_id": file_id,
        "old_s3_key": old_key,
        "new_s3_key": new_key,
        "new_status": file_record.status
    }


@router.get("/resubmitted-files/{project_id}/{reviewer_id}")
def get_resubmitted_files(project_id: str, reviewer_id: str, db: Session = Depends(get_db)):
    # Step 1: Verify reviewer is part of the project
    reviewer_member = (
        db.query(database_models.ProjectMember)
        .filter_by(project_id=project_id, user_id=reviewer_id, project_role="reviewer")
        .first()
    )
    if not reviewer_member:
        raise HTTPException(
            status_code=403,
            detail="Reviewer is not part of this project"
        )

    # Step 2: Fetch resubmitted files (review_cycle > 1, belief=True)
    # where the reviewer has reviewed previously and now the annotator has resubmitted
    files = (
        db.query(database_models.Files)
        .join(database_models.Annotations, database_models.Annotations.file_id == database_models.Files.id)
        .join(database_models.AnnotationReviews, database_models.AnnotationReviews.annotation_id == database_models.Annotations.id)
        .filter(
            database_models.Files.project_id == project_id,
            database_models.AnnotationReviews.reviewer_id == reviewer_id,
            database_models.Annotations.review_cycle > 1,
            database_models.Annotations.belief == True
        )
        .distinct()
        .all()
    )

    return files






@router.put("/reject")
def reject_file(request: modelsp.RejectFileFromReview, db: Session = Depends(get_db)):
    """
    Reject a file under review.
    Marks review_state='rejected', sets belief=False,
    updates AnnotationReviews.decision='rejected', and keeps file.status='review'.
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

    # ❌ Remove increment here — do NOT increase review_cycle
    annotation.belief = False
    annotation.review_state = 'rejected'
    annotation.submitted_at = datetime.utcnow()

    file = db.query(database_models.Files).filter(database_models.Files.id == request.file_id).first()
    if file:
        file.status = 'review'

    review_record = (
        db.query(database_models.AnnotationReviews)
        .filter(database_models.AnnotationReviews.annotation_id == annotation.id)
        .first()
    )
    if review_record:
        review_record.decision = 'rejected'
        review_record.reviewed_at = datetime.utcnow()

    db.commit()

    return {
        "message": "File rejected successfully.",
        "file_id": request.file_id,
        "review_cycle": annotation.review_cycle,
        "belief": annotation.belief,
        "review_state": annotation.review_state,
    }
