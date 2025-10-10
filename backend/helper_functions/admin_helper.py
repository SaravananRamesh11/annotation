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



load_dotenv()



AWS_ACCESS_KEY =os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION =   os.getenv("AWS_REGION")
BUCKET_NAME =  os.getenv("BUCKET_NAME")



def get_presigned_url(s3_client, key: str, expire_seconds: int = 3600):
    """Generate a signed URL for an S3 object."""
    try:
        return s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": key},
            ExpiresIn=expire_seconds
        )
    except ClientError as e:
        print(f"⚠️ Could not sign {key}: {e}")
        return None


def list_files_in_s3(s3_client, prefix: str):
    """List all file keys in a given S3 prefix."""
    try:
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)
        if "Contents" not in response:
            return []
        return [obj["Key"] for obj in response["Contents"] if not obj["Key"].endswith("/")]
    except ClientError as e:
        print(f" S3 list error for {prefix}: {e}")
        return []