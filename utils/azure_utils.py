"""Azure Blob Storage utility functions."""
import os
import logging
import requests
from typing import Optional
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import AzureError

from config import Config

logger = logging.getLogger(__name__)


def get_azure_blob_service_client() -> BlobServiceClient:
    """
    Create and return Azure Blob Service Client.
    
    Returns:
        BlobServiceClient instance
        
    Raises:
        ValueError: If Azure credentials are not configured
    """
    if not Config.AZURE_STORAGE_ACCOUNT_NAME or not Config.AZURE_STORAGE_ACCOUNT_KEY:
        raise ValueError("Azure Storage credentials not configured")
    
    connection_string = Config.get_azure_connection_string()
    return BlobServiceClient.from_connection_string(connection_string)


def upload_to_azure_blob(local_file_path: str, blob_name: str) -> str:
    """
    Upload a file to Azure Blob Storage.
    
    Note: This function preserves the original file quality - no compression,
    resizing, or image processing is applied.
    
    Args:
        local_file_path: Path to local file
        blob_name: Name for the blob in Azure
        
    Returns:
        Public URL of the uploaded blob
        
    Raises:
        Exception: If upload fails
    """
    try:
        blob_service_client = get_azure_blob_service_client()
        blob_client = blob_service_client.get_blob_client(
            container=Config.AZURE_CONTAINER_NAME,
            blob=blob_name
        )
        
        # Upload the file in binary mode - preserves original quality
        with open(local_file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        
        # Construct the public URL
        blob_url = (
            f"https://{Config.AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/"
            f"{Config.AZURE_CONTAINER_NAME}/{blob_name}"
        )
        logger.info(f"Successfully uploaded {blob_name} to Azure")
        return blob_url
    
    except AzureError as e:
        logger.error(f"Azure error uploading {blob_name}: {e}")
        raise Exception(f"Failed to upload to Azure: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error uploading {blob_name}: {e}")
        raise Exception(f"Failed to upload to Azure: {str(e)}")


def download_video(video_url: str, local_path: str, timeout: int = 300) -> bool:
    """
    Download a video from a URL to a local file.
    
    Args:
        video_url: URL of the video to download
        local_path: Local path to save the video
        timeout: Request timeout in seconds
        
    Returns:
        True if successful, False otherwise
    """
    try:
        response = requests.get(video_url, stream=True, timeout=timeout)
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(local_path) if os.path.dirname(local_path) else '.', exist_ok=True)
        
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        logger.info(f"Successfully downloaded video to {local_path}")
        return True
    except Exception as e:
        logger.error(f"Error downloading video from {video_url}: {e}")
        return False


def download_and_upload_video(
    video_url: str,
    base_filename: str,
    upload_folder: str
) -> Optional[str]:
    """
    Download video from Veo API and upload to Azure Storage.
    
    Args:
        video_url: URL of the video from Veo API
        base_filename: Base filename (without extension) to use for the video
        upload_folder: Local folder for temporary storage
        
    Returns:
        Azure blob URL of the uploaded video, or None if failed
    """
    try:
        # Generate video filename
        video_filename = f"{base_filename}.mp4"
        
        # Ensure uploads directory exists
        os.makedirs(upload_folder, exist_ok=True)
        
        # Download video temporarily
        temp_video_path = os.path.join(upload_folder, video_filename)
        
        logger.info(f"Downloading video from {video_url} to {temp_video_path}...")
        if not download_video(video_url, temp_video_path):
            logger.warning(f"Failed to download video from Veo API: {video_url}")
            return None
        
        # Check if file was downloaded successfully
        if not os.path.exists(temp_video_path) or os.path.getsize(temp_video_path) == 0:
            logger.warning(f"Downloaded video file is empty or doesn't exist: {temp_video_path}")
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            return None
        
        file_size = os.path.getsize(temp_video_path)
        logger.info(f"Video downloaded successfully ({file_size / 1024 / 1024:.2f} MB)")
        
        # Upload to Azure
        blob_name = f"{Config.AZURE_BLOB_PATH_OUTPUT}{video_filename}"
        logger.info(f"Uploading to Azure: {blob_name}")
        blob_url = upload_to_azure_blob(temp_video_path, blob_name)
        
        # Clean up local file
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
            logger.info(f"Cleaned up temporary file: {temp_video_path}")
        
        logger.info(f"Video successfully uploaded to Azure: {blob_url}")
        return blob_url
    
    except Exception as e:
        logger.error(f"Error in download_and_upload_video: {e}", exc_info=True)
        # Clean up any partial files
        temp_video_path = os.path.join(upload_folder, f"{base_filename}.mp4")
        if os.path.exists(temp_video_path):
            try:
                os.remove(temp_video_path)
            except Exception:
                pass
        return None

