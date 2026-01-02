"""
S3 client for uploading files to AWS S3
"""
import os
import boto3
from botocore.exceptions import ClientError

# Initialize S3 client
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION', 'eu-west-2')
)

BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'vox-platform-storage')


def upload_to_s3(file_bytes: bytes, s3_key: str, content_type: str = 'application/octet-stream') -> str:
    """
    Upload bytes to S3 and return public URL
    
    Args:
        file_bytes: The file content as bytes
        s3_key: S3 object key (path in bucket)
        content_type: MIME type of the file
    
    Returns:
        Public URL of the uploaded file
    """
    try:
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=file_bytes,
            ContentType=content_type,
            ACL='public-read'  # Make file publicly accessible
        )
        
        # Return public URL
        url = f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION', 'eu-west-2')}.amazonaws.com/{s3_key}"
        return url
        
    except ClientError as e:
        print(f"Error uploading to S3: {e}")
        raise Exception(f"Failed to upload to S3: {str(e)}")


def delete_from_s3(s3_key: str) -> bool:
    """
    Delete a file from S3
    
    Args:
        s3_key: S3 object key to delete
    
    Returns:
        True if successful, False otherwise
    """
    try:
        s3_client.delete_object(
            Bucket=BUCKET_NAME,
            Key=s3_key
        )
        return True
    except ClientError as e:
        print(f"Error deleting from S3: {e}")
        return False


def get_s3_url(s3_key: str) -> str:
    """
    Get public URL for an S3 object
    
    Args:
        s3_key: S3 object key
    
    Returns:
        Public URL
    """
    return f"https://{BUCKET_NAME}.s3.{os.getenv('AWS_REGION', 'eu-west-2')}.amazonaws.com/{s3_key}"
