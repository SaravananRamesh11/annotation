from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class Users(BaseModel):
    id:str 
    name:str 
    email:str
    role:str
    password:str
    otp:Optional[str]
    otpExpiry: Optional[datetime]
