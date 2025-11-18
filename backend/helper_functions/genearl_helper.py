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



def project_name(projectId):
    project_name = (
    db.query(Project.name)
      .filter(Project.id == project_id)
      .scalar()
            )
    return project_name
