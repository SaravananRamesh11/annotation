from fastapi import APIRouter, Request, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import database_models  
import bcrypt
import jwt
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os


router = APIRouter(prefix="/api/general", tags=["auth"])


load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")  # default to HS256 if not set
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))



def create_access_token(data: dict, expires_delta: int = ACCESS_TOKEN_EXPIRE_MINUTES):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


@router.post("/login")
async def login_user(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON format")

    user_id = body.get("id")
    password = body.get("password")

    if not user_id or not password:
        raise HTTPException(status_code=400, detail="ID and password are required")

    # 1️⃣ Fetch user from DB
    user = db.query(database_models.Users).filter(database_models.Users.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ID or password")

    # 2️⃣ Check password
    if not bcrypt.checkpw(password.encode("utf-8"), user.password.encode("utf-8")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ID or password")

    # 3️⃣ Create JWT token with payload (id, role)
    token_data = {"id": user.id, "role": user.role}
    token = create_access_token(token_data)

    # 4️⃣ Return token
    return {"access_token": token, "token_type": "bearer"}


