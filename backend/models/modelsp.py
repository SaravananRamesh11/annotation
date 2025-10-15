from pydantic import BaseModel
from datetime import datetime
from typing import Optional,List, Any, Dict
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
    classes: List[Dict[str, Any]]



  




class ProjectMemberData(BaseModel):
    user_id: str                   
    project_role: str              

class AddProjectMembers(BaseModel):
    project_name: str
    members: List[ProjectMemberData] # list of members with user_id & role


class ProjectMemberResponse(BaseModel):
    id: int
    project_id: int
    user_id: str
    project_role: str
    joined_at: datetime

   

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str

class ProjectMemberOut(BaseModel):
    user_id: str
    project_id: int
    project_role: str
    joined_at: datetime

    class Config:
        orm_mode = True


class AnnotatorOut(BaseModel):
    user_id: str
    project_role: str
    joined_at: datetime

    class Config:
        from_attributes = True

   

class PromoteRequest(BaseModel):
    user_ids: List[str]
