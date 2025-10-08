from fastapi import APIRouter, Request, Depends, HTTPException, status,File, UploadFile, Form
from sqlalchemy.orm import Session
from database import get_db
from models import database_models
from dotenv import load_dotenv
import  uuid,os
from utils import s3_connection
from botocore.exceptions import NoCredentialsError
from typing import List



load_dotenv()


AWS_ACCESS_KEY =os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION =   os.getenv("AWS_REGION")
BUCKET_NAME =  os.getenv("BUCKET_NAME")


FOLDER_PATH_TO_UPLOAD_FILES = "annotation/working_directory/"

router = APIRouter(prefix="/api/admin", tags=["auth"])



@router.post("/upload-to-s3")
async def upload_files_to_s3(
    id: str = Form(...),
    resolution: str = Form(...),
    proofImages: List[UploadFile] = File(...),
    s3_client=Depends(s3_connection.get_s3_connection),
):
    uploaded_files = []
    print("Received files:", proofImages)
    for f in proofImages:
        print("filename:", f.filename, "file object:", f.file)

    try:
        for file in proofImages:
            if file.filename is None or file.file is None:
                print("Skipping invalid file:", file)
                continue

            print("Uploading:", file.filename)
            file_extension = os.path.splitext(file.filename)[1]
            unique_name = f"{uuid.uuid4().hex}{file_extension}"
            s3_key = f"{FOLDER_PATH_TO_UPLOAD_FILES}{unique_name}"

            file.file.seek(0)  # Make sure stream is at the beginning
            s3_client.upload_fileobj(file.file, BUCKET_NAME, s3_key)

            file_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
            uploaded_files.append(file_url)


        return {
            "message": "Files uploaded successfully!",
            "ticket_id": id,
            "resolution": resolution,
            "file_urls": uploaded_files,
        }

    except NoCredentialsError:
        raise HTTPException(status_code=403, detail="AWS credentials not found")
    except Exception as e:
        print("Error uploading to S3:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
