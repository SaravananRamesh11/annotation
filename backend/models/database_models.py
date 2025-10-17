from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Enum, ForeignKey,JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

Base = declarative_base()


class Users(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    role = Column(String, nullable=False)  # "admin" or "employee"
    password = Column(String, nullable=False)
    otp = Column(String, nullable=True)
    otpExpiry = Column(DateTime, nullable=True)

    project_links = relationship("ProjectMember", back_populates="user")
    annotations = relationship("Annotations", back_populates="user")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(String(300), nullable=True)
    classes = Column(JSONB, nullable=False)  # e.g. ["car", "bus", "bike"]
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)

    # Cascading deletes: deleting project deletes members and files
    members = relationship(
        "ProjectMember",
        back_populates="project",
        cascade="all, delete-orphan"
    )
    files = relationship(
        "Files",
        back_populates="project",
        cascade="all, delete-orphan"
    )


class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_role = Column(String, nullable=False)  # "annotator" or "reviewer"
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project = relationship("Project", back_populates="members")
    user = relationship("Users", back_populates="project_links")


class Files(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    s3_key = Column(String(255), unique=True, nullable=False, index=True)  # unique S3 key
    type = Column(Enum('image', 'video', name="file_type"), nullable=False)
    status = Column(Enum('pending', 'assigned', 'review', 'completed', name="file_status"), nullable=False, default='pending')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    project = relationship("Project", back_populates="files")
    # Cascading deletes: deleting a file deletes all its annotations
    annotations = relationship(
        "Annotations",
        back_populates="file",
        cascade="all, delete-orphan"
    )

class Annotations(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    data = Column(JSON, nullable=True)
    assigned_by = Column(Enum('admin', 'random', name="assigned_type"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_saved_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)

    file = relationship("Files", back_populates="annotations")
    user = relationship("Users", back_populates="annotations")











