"""
Configuration management for Veo Video Generation application.
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Application configuration class."""
    
    # Flask Configuration
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = 'uploads'
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24).hex())
    
    # File Paths
    HISTORY_FILE = 'video_history.json'
    DECKS_FILE = 'decks.json'
    
    # Business Logic Configuration
    MAX_CARDS_PER_DECK = int(os.getenv('MAX_CARDS_PER_DECK', 50))
    MAX_HISTORY_ENTRIES = int(os.getenv('MAX_HISTORY_ENTRIES', 100))
    
    # Azure Storage Configuration
    AZURE_STORAGE_ACCOUNT_NAME = os.getenv('AZURE_STORAGE_ACCOUNT_NAME')
    AZURE_STORAGE_ACCOUNT_KEY = os.getenv('AZURE_STORAGE_ACCOUNT_KEY')
    AZURE_CONTAINER_NAME = os.getenv('AZURE_CONTAINER_NAME', 'unai-public')
    AZURE_BLOB_PATH_INPUT = 'veo_video_generation/input_images/'
    AZURE_BLOB_PATH_OUTPUT = 'veo_video_generation/output_video/'
    
    # Veo API Configuration
    VEO_API_KEY = os.getenv('VEO_API_KEY')
    VEO_API_BASE_URL = os.getenv('VEO_API_BASE_URL', 'https://api.kie.ai/api/v1/veo')
    
    # Rate Limiting Configuration
    RATE_LIMIT_BATCH_SIZE = int(os.getenv('RATE_LIMIT_BATCH_SIZE', 18))
    RATE_LIMIT_DELAY_SECONDS = float(os.getenv('RATE_LIMIT_DELAY_SECONDS', 10.5))
    
    # Polling Configuration
    STATUS_POLL_INTERVAL = int(os.getenv('STATUS_POLL_INTERVAL', 3))  # seconds
    DECK_STATUS_POLL_INTERVAL = int(os.getenv('DECK_STATUS_POLL_INTERVAL', 30))  # seconds
    
    # Video Generation Defaults
    DEFAULT_MODEL = os.getenv('DEFAULT_MODEL', 'veo3_fast')
    DEFAULT_ASPECT_RATIO = os.getenv('DEFAULT_ASPECT_RATIO', '9:16')
    DEFAULT_GENERATION_TYPE = os.getenv('DEFAULT_GENERATION_TYPE', 'FIRST_AND_LAST_FRAMES_2_VIDEO')
    VIDEOS_PER_CARD = int(os.getenv('VIDEOS_PER_CARD', 2))
    
    # Allowed File Extensions
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration values."""
        required_vars = [
            ('VEO_API_KEY', cls.VEO_API_KEY),
            ('AZURE_STORAGE_ACCOUNT_NAME', cls.AZURE_STORAGE_ACCOUNT_NAME),
            ('AZURE_STORAGE_ACCOUNT_KEY', cls.AZURE_STORAGE_ACCOUNT_KEY),
        ]
        
        missing = [name for name, value in required_vars if not value]
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
    
    @classmethod
    def get_azure_connection_string(cls) -> str:
        """Get Azure Storage connection string."""
        return (
            f"DefaultEndpointsProtocol=https;"
            f"AccountName={cls.AZURE_STORAGE_ACCOUNT_NAME};"
            f"AccountKey={cls.AZURE_STORAGE_ACCOUNT_KEY};"
            f"EndpointSuffix=core.windows.net"
        )

