"""File utility functions."""
import os
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename
from typing import Optional


def generate_unique_filename(original_filename: str) -> str:
    """
    Generate a unique filename with timestamp and UUID.
    
    Format: YYYYMMDD_HHMMSS_<uuid>_<original_filename>
    
    Args:
        original_filename: Original filename
        
    Returns:
        Unique filename string
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    _, ext = os.path.splitext(original_filename)
    base_name = secure_filename(os.path.splitext(original_filename)[0])
    
    # Limit base name length
    if len(base_name) > 50:
        base_name = base_name[:50]
    
    return f"{timestamp}_{unique_id}_{base_name}{ext}"


def ensure_directory_exists(directory_path: str) -> None:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        directory_path: Path to the directory
    """
    os.makedirs(directory_path, exist_ok=True)


def get_file_extension(filename: str) -> str:
    """
    Get file extension from filename.
    
    Args:
        filename: Filename
        
    Returns:
        File extension (with dot)
    """
    _, ext = os.path.splitext(filename)
    return ext.lower()


def get_base_filename(filename: str) -> str:
    """
    Get base filename without extension.
    
    Args:
        filename: Full filename
        
    Returns:
        Base filename without extension
    """
    return os.path.splitext(filename)[0]

