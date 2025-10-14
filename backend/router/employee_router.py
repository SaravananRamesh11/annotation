import os
import random
from fastapi import APIRouter, Request, Depends, HTTPException, status,File, UploadFile, Form,Query
from sqlalchemy.orm import Session
from models import modelsp,database_models
from database import get_db
from utils import s3_connection
from models import database_models,modelsp

router = APIRouter(prefix="/api/employee", tags=["auth"])

AWS_ACCESS_KEY =os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION =   os.getenv("AWS_REGION")
BUCKET_NAME =  os.getenv("BUCKET_NAME")

# Get all projects assigned to a user
@router.get("user_projects/{user_id}")
def get_user_projects(user_id: str, db: Session = Depends(get_db)):
    from models.database_models import Project, ProjectMember

    results = (
        db.query(Project.name)
        .select_from(ProjectMember)
        .join(Project, Project.id == ProjectMember.project_id)
        .filter(ProjectMember.user_id == user_id)
        .all()
    )

    if not results:
        raise HTTPException(status_code=404, detail="No projects found for this user")

    return [r.name for r in results]

@router.get("/{project_id}/assign-file/{employee_id}")
def assign_random_file(project_id: int, employee_id: str, db: Session = Depends(get_db), s3=Depends(s3_connection.get_s3_connection)):

    # Step 1: Validate project
    project = db.query(database_models.Project).filter(database_models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Step 2: Validate user
    user = db.query(database_models.Users).filter(database_models.Users.id == employee_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Step 3: Ensure user is part of the project
    print(f"Checking membership for project {project_id} and user {employee_id}")
    project_member = (
        db.query(database_models.ProjectMember)
        .filter(
            database_models.ProjectMember.project_id == project_id,
            database_models.ProjectMember.user_id == employee_id
        )
        .first()
    )
    print("Found project_member:", project_member)

    if not project_member:
        raise HTTPException(status_code=400, detail="User is not part of this project")

    
    # project_prefix = f"{project.name}/working/raw/"
    # print("the selected project is", project_prefix)

    # response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=project_prefix)
    # contents = response.get("Contents")
    # if not contents:
    #     raise HTTPException(status_code=404, detail="No files available in raw folder")


    # Step 4: List available raw files in S3
    project_prefix = f"annotation/{project.name}/working_directory/raw/"
    print("the selected project is", project_prefix)

    response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=project_prefix)
    contents = response.get("Contents")
    if not contents:
        raise HTTPException(status_code=404, detail="No files available in raw folder")

    # Step 5: Pick a random file
    selected_file = random.choice(contents)
    print("selected_file is",selected_file)
    file_key = selected_file["Key"] #actualy the path to the file from annotation
    print("file_key is ",file_key)
    filename = os.path.basename(file_key) #actual file name in s3
    print("filename is",filename)
    assigned_key = f"annotation/{project.name}/working_directory/assigned/{filename}"
    print("assigned_key is",assigned_key) # same as file_key without annotation/ in the path

    # Step 6: Move file in S3
    try:
        s3.copy_object(
            Bucket=BUCKET_NAME,
            CopySource={"Bucket": BUCKET_NAME, "Key": file_key},
            Key=assigned_key
        )
        print("\n   file copy done!!")
        s3.delete_object(Bucket=BUCKET_NAME, Key=file_key)
        print("\n    file delete done !!!!")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to move file in S3: {str(e)}")

    # Step 7: Update the existing file record (not create new)
    print("the file's key is",file_key)
    file_record = (
        db.query(database_models.Files)
        .filter(database_models.Files.s3_key == filename)
        .first()
    )
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File record not found in database")

    file_record.s3_key = assigned_key
    file_record.status = "assigned"
    db.commit()
    db.refresh(file_record)

    # Step 8: Create new annotation record
    new_annotation = database_models.Annotations(
        file_id=file_record.id,
        project_member_id=project_member.id
    )
    db.add(new_annotation)
    db.commit()

    file_url = f"https://{BUCKET_NAME}.s3.eu-north-1.amazonaws.com/{assigned_key}"

    return {
        "message": "File assigned successfully",
        "employee_id": employee_id,
        "file_assigned": assigned_key,
        "file_url": file_url
    }


