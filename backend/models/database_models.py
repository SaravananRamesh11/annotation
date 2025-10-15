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
    # Removed annotations relationship here


class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_role = Column(String, nullable=False)  # "annotator" or "reviewer"
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project = relationship("Project", back_populates="members")
    user = relationship("Users", back_populates="project_links")
    annotations = relationship("Annotations", back_populates="project_member")  # correct FK



class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(String(300), nullable=True)
    classes = Column(JSONB, nullable=False)  # e.g. ["car", "bus", "bike"]
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)

    members = relationship("ProjectMember", back_populates="project")
    files = relationship("Files", back_populates="project")  # link to project files





class Files(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    s3_key = Column(String(255), unique=True, nullable=False, index=True)  # unique S3 key
    type = Column(Enum('image', 'video', name="file_type"), nullable=False)
    status = Column(Enum('pending', 'assigned','review', 'completed', name="file_status"), nullable=False, default='pending')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    project = relationship("Project", back_populates="files")
    annotations = relationship("Annotations", back_populates="file")


# class Annotations(Base):
#     __tablename__ = "annotations"

#     id = Column(Integer, primary_key=True, autoincrement=True)
#     file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
#     project_member_id = Column(Integer, ForeignKey("project_members.id", ondelete="CASCADE"), nullable=False)
#     data = Column(JSON, nullable=True)
#     started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
#     last_saved_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
#     submitted_at = Column(DateTime(timezone=True), nullable=True)

#     file = relationship("Files", back_populates="annotations")
#     project_member = relationship("ProjectMember", back_populates="annotations")



class Annotations(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    project_member_id = Column(Integer, ForeignKey("project_members.id", ondelete="CASCADE"), nullable=False)
    data = Column(JSON, nullable=True)
    assigned_by = Column(Enum('admin', 'random', name="assign1ed_type"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_saved_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)

    file = relationship("Files", back_populates="annotations")
    project_member = relationship("ProjectMember", back_populates="annotations")
















