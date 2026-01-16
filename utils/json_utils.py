"""JSON file utility functions."""
import os
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def load_json_file(file_path: str, default: Any = None) -> Any:
    """
    Load data from a JSON file.
    
    Args:
        file_path: Path to the JSON file
        default: Default value to return if file doesn't exist or is invalid
        
    Returns:
        Loaded data or default value
    """
    if not os.path.exists(file_path):
        logger.debug(f"JSON file not found: {file_path}, returning default")
        return default if default is not None else []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.debug(f"Successfully loaded JSON file: {file_path}")
            return data
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in file {file_path}: {e}")
        return default if default is not None else []
    except IOError as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return default if default is not None else []


def save_json_file(file_path: str, data: Any, indent: int = 2) -> bool:
    """
    Save data to a JSON file.
    
    Args:
        file_path: Path to the JSON file
        data: Data to save
        indent: JSON indentation level
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure directory exists
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        logger.debug(f"Successfully saved JSON file: {file_path}")
        return True
    except IOError as e:
        logger.error(f"Error saving file {file_path}: {e}")
        return False


def append_to_json_list(file_path: str, item: Dict[str, Any], max_items: Optional[int] = None) -> bool:
    """
    Append an item to a JSON list file.
    
    Args:
        file_path: Path to the JSON file
        item: Item to append
        max_items: Maximum number of items to keep (keeps most recent)
        
    Returns:
        True if successful, False otherwise
    """
    data = load_json_file(file_path, default=[])
    if not isinstance(data, list):
        logger.warning(f"File {file_path} does not contain a list, converting...")
        data = []
    
    # Add to beginning of list (most recent first)
    data.insert(0, item)
    
    # Limit list size if specified
    if max_items is not None and len(data) > max_items:
        data = data[:max_items]
    
    return save_json_file(file_path, data)

