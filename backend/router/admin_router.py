from fastapi import APIRouter, Request, Depends, HTTPException, status,File, UploadFile, Form
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from database import get_db
from models import database_models
from dotenv import load_dotenv
import  uuid,os
from utils import s3_connection
from botocore.exceptions import NoCredentialsError
from typing import List, Optional
from datetime import datetime, timedelta
import bcrypt




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


#Add User end point

# Pydantic model for input validation
class UserCreate(BaseModel):
    user_id: str
    name: str
    email: EmailStr
    role: str
    password: str
    otp: Optional[str] = None
    otpExpiry: Optional[str] = None

@router.post("/add-user")
async def add_user(user: UserCreate, db: Session = Depends(get_db)):
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