from fastapi import FastAPI, Depends, HTTPException,Request 
from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models.database_models 
from models import modelsp
import bcrypt
from fastapi.responses import JSONResponse
from router import router_login,admin_router,annotator_router,reviewer_router
from fastapi.middleware.cors import CORSMiddleware



models.database_models.Base.metadata.create_all(bind=engine)


app = FastAPI()

origins = [
    "http://localhost:3000",  # React frontend
    "http://localhost:5173"   # Vite frontend (if you use it)
]

# 2. Add the CORSMiddleware to your app
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allows the specified origins
    allow_credentials=True, # Allows cookies to be sent
    allow_methods=["*"],    # Allows all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],    # Allows all headers
)


def hash_password(password: str) -> str:
    """Hashes a password using bcrypt and returns the hash as a string."""
    # Convert string password to bytes
    password_bytes = password.encode('utf-8')
    
    # Generate a salt and hash the password
    # gensalt() generates a random salt
    hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    
    # Decode the hash bytes back to a string for storage in the DB
    return hashed_bytes.decode('utf-8')

SARVA_HASH = hash_password("sarva")
HEMANTH_HASH = hash_password("hemanth")
MOHANA_HASH = hash_password("mohana")
DARSHINI_HASH = hash_password("darshini")

# Define your user objects using the hashed passwords
users = [
    modelsp.Users(id="VISTA0001", name="sarva", email="saravananramesh102002@gmail.com", role="admin", password=SARVA_HASH, otp=None, otpExpiry=None),
    modelsp.Users(id="VISTA0002", name="hemanth", email="hamanthmoorthi77@gmail.com", role="employee", password=HEMANTH_HASH, otp=None, otpExpiry=None),
    modelsp.Users(id="VISTA0003", name="mohana", email="mohanapriya7114@gmail.com", role="employee", password=MOHANA_HASH, otp=None, otpExpiry=None),
    modelsp.Users(id="VISTA0004", name="darshini", email="dharshiniramu78@gmail.com", role="employee", password=DARSHINI_HASH, otp=None, otpExpiry=None),
]




def init_db():
    db = SessionLocal()

    existing_count = db.query(models.database_models.Users).count()

    if existing_count == 0:
        for product in users:
            db.add(models.database_models.Users(**product.model_dump()))
        db.commit()
        print("Database initialized with sample products.")
        
    db.close()

init_db()






app.include_router(router_login.router)
app.include_router(admin_router.router)
app.include_router(annotator_router.router)
app.include_router(reviewer_router.router)
