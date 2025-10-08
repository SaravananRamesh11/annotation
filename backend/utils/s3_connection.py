from dotenv import load_dotenv
import os
import boto3
from botocore.exceptions import NoCredentialsError


load_dotenv()

AWS_ACCESS_KEY =os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION =   os.getenv("ap-south-1")
BUCKET_NAME =  os.getenv("BUCKET_NAME")


def get_s3_connection():

    s3_client = boto3.client(
        "s3",
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION,
    )
    return s3_client

