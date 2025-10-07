from sqlalchemy import Column, Integer, String, Float, DateTime, Date
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Users(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email=Column(String, nullable=False)
    role=Column(String, nullable=False)
    password=Column(String, nullable=False)
    otp=Column(String, nullable=True)
    otpExpiry=Column(DateTime, nullable=True)

    