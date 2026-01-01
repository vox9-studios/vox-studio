import boto3
from fastapi import UploadFile
import os

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME", "vox-storage")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

async def upload_to_s3(file: UploadFile, s3_key: str) -> str:
    """Upload file to S3 and return public URL"""
    file_content = await file.read()
    
    s3_client.put_object(
        Bucket=AWS_BUCKET_NAME,
        Key=s3_key,
        Body=file_content,
        ContentType=file.content_type or 'application/octet-stream',
        ACL='public-read'
    )
    
    url = f"https://{AWS_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
    return url

def test_s3_connection() -> bool:
    """Test S3 connection"""
    try:
        s3_client.list_buckets()
        return True
    except Exception as e:
        print(f"S3 connection failed: {e}")
        return False
