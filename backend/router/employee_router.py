#hello 
from fastapi import APIRouter, Request, Depends, HTTPException, status,File, UploadFile, Form,Query
router = APIRouter(prefix="/api/employee", tags=["auth"])