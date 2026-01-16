"""Validation utility functions."""
from werkzeug.datastructures import FileStorage
from typing import Optional
from config import Config


def validate_image_file(file: Optional[FileStorage]) -> tuple[bool, Optional[str]]:
    """
    Validate that an uploaded file is an image.
    
    Args:
        file: FileStorage object from Flask request
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if file is None:
        return False, "No file provided"
    
    if not file.filename:
        return False, "No file selected"
    
    # Check file extension
    if '.' not in file.filename:
        return False, "Invalid file type. File must have an extension."
    
    extension = file.filename.rsplit('.', 1)[1].lower()
    if extension not in Config.ALLOWED_IMAGE_EXTENSIONS:
        return False, (
            f"Invalid file type. Allowed extensions: "
            f"{', '.join(Config.ALLOWED_IMAGE_EXTENSIONS)}"
        )
    
    return True, None


def validate_deck_name(name: str) -> tuple[bool, Optional[str]]:
    """
    Validate deck name.
    
    Args:
        name: Deck name to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    name = name.strip() if name else ""
    
    if not name:
        return False, "Deck name is required"
    
    if len(name) > 200:
        return False, "Deck name must be 200 characters or less"
    
    return True, None


def validate_prompt(prompt: str) -> tuple[bool, Optional[str]]:
    """
    Validate video generation prompt.
    
    Args:
        prompt: Prompt text to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    prompt = prompt.strip() if prompt else ""
    
    if not prompt:
        return False, "Prompt is required"
    
    if len(prompt) > 10000:
        return False, "Prompt must be 10,000 characters or less"
    
    return True, None


def validate_aspect_ratio(aspect_ratio: str) -> tuple[bool, Optional[str]]:
    """
    Validate aspect ratio value.
    
    Args:
        aspect_ratio: Aspect ratio string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    valid_ratios = {'16:9', '9:16', '1:1', 'Auto'}
    
    if aspect_ratio not in valid_ratios:
        return False, f"Invalid aspect ratio. Allowed values: {', '.join(valid_ratios)}"
    
    return True, None

