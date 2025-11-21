from sqlalchemy import Boolean, Column, Integer, String, Float, DateTime, Date, Enum, ForeignKey,JSON,Sequence,text, event, DDL
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid

Base = declarative_base()

project_sequence_name = "project_id_seq"

# Create the sequence explicitly (guaranteed to run before tables)
event.listen(
    Base.metadata,
    "before_create",
    DDL(f"CREATE SEQUENCE IF NOT EXISTS {project_sequence_name} START 1 INCREMENT 1")
)

# Drop sequence if dropping tables (optional but clean)
event.listen(
    Base.metadata,
    "after_drop",
    DDL(f"DROP SEQUENCE IF EXISTS {project_sequence_name}")
)


class Project(Base):
    __tablename__ = "projects"

    id = Column(
        String(10),
        primary_key=True,
        server_default=func.concat(
            "VS",
            func.lpad(
                func.nextval(text(f"'{project_sequence_name}'")).cast(String),
                6,
                "0"
            )
        ),
        nullable=False,
        unique=True
    )

    name = Column(String(100), nullable=False)
    description = Column(String(300), nullable=True)
    classes = Column(JSONB, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

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
    reviews = relationship("AnnotationReviews", back_populates="reviewer")


class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # FIXED: was Integer → now UUID
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False
    )

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_role = Column(String, nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project = relationship("Project", back_populates="members")
    user = relationship("Users", back_populates="project_links")







class Files(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # FIXED: was Integer → now UUID
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False
    )

    s3_key = Column(String(255), unique=True, nullable=False, index=True)
    type = Column(Enum('image', 'video', name="file_type"), nullable=False)
    status = Column(Enum('pending', 'assigned', 'review', 'completed', name="file_status"), nullable=False, default='pending')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    project = relationship("Project", back_populates="files")
    annotations = relationship("Annotations", back_populates="file", cascade="all, delete-orphan")


class Annotations(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    data = Column(JSON, nullable=True)
    assigned_by = Column(Enum('admin', 'random', name="assigned_type"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())

    last_saved_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)

    review_state = Column(
        Enum('not_reviewed', 'in_review', 'approved', 'rejected', name="review_state"),
        default='not_reviewed',
        nullable=False
    )
    review_cycle = Column(Integer, default=0, nullable=False)
    belief = Column(Boolean, default=True, nullable=False)


    file = relationship("Files", back_populates="annotations")
    user = relationship("Users", back_populates="annotations")
    reviews = relationship(
        "AnnotationReviews",
        back_populates="annotation",
        cascade="all, delete-orphan"
    )


class AnnotationReviews(Base):
    __tablename__ = "annotation_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Link to the annotation being reviewed
    annotation_id = Column(Integer, ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False)

    # Who reviewed this annotation
    reviewer_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Review decision
    decision = Column(
        Enum('approved', 'rejected', name="review_decision"),
        nullable=True
    )

    # Optional feedback/comments
    comments = Column(String(255), nullable=True)

    # Timestamps
    reviewed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    annotation = relationship("Annotations", back_populates="reviews")
    reviewer = relationship("Users", back_populates="reviews")


