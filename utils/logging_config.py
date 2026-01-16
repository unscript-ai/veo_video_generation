"""Logging configuration."""
import logging
import sys
import os
from datetime import datetime
from typing import Optional


def get_timestamped_log_filename(base_name: str = "app") -> str:
    """
    Generate a timestamped log filename.
    
    Args:
        base_name: Base name for the log file
        
    Returns:
        Timestamped log file path (e.g., logs/app_20260116_133925.log)
    """
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(logs_dir, f"{base_name}_{timestamp}.log")


def setup_logging(level: str = "INFO", log_file: Optional[str] = None, use_timestamp: bool = True) -> str:
    """
    Configure application logging.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path (if None and use_timestamp=True, generates timestamped filename)
        use_timestamp: If True and log_file is None, creates a timestamped log file
        
    Returns:
        Path to the log file being used
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    
    # File handler
    actual_log_file = log_file
    if actual_log_file is None and use_timestamp:
        # Generate timestamped log file
        actual_log_file = get_timestamped_log_filename()
    elif actual_log_file is None:
        # Default to logs/app.log if timestamp is disabled
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)
        actual_log_file = os.path.join(logs_dir, "app.log")
    
    if actual_log_file:
        # Ensure directory exists
        log_dir = os.path.dirname(actual_log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        file_handler = logging.FileHandler(actual_log_file, mode='w')  # 'w' mode overwrites, but we create new file each run
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Set specific loggers
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('azure').setLevel(logging.WARNING)
    
    return actual_log_file or ""

