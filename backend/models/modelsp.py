from pydantic import BaseModel
from datetime import datetime
from typing import Optional,List, Any
from sqlalchemy.dialects.postgresql import JSONB

class Users(BaseModel):
    id:str 
    name:str 
    email:str
    role:str
    password:str
    otp:Optional[str]
    otpExpiry: Optional[datetime]



class ProjectCreate(BaseModel): #http://localhost:8000/api/admin/create_project   "for request" of the post request
    project_name: str
    description: str | None = None
    classes: List[str]




   

