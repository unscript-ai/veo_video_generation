"""Video generation service."""
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

from veo_video_generator import VeoVideoGenerator
from config import Config
from services.storage_service import StorageService
from utils.azure_utils import download_and_upload_video
from utils.file_utils import get_base_filename

logger = logging.getLogger(__name__)


class VideoService:
    """Service for video generation operations."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize video service.
        
        Args:
            api_key: Veo API key (defaults to Config.VEO_API_KEY)
        """
        self.api_key = api_key or Config.VEO_API_KEY
        if not self.api_key:
            raise ValueError("VEO_API_KEY is required")
        self._generator: Optional[VeoVideoGenerator] = None
    
    @property
    def generator(self) -> VeoVideoGenerator:
        """Get or create Veo generator instance (singleton pattern)."""
        if self._generator is None:
            self._generator = VeoVideoGenerator(self.api_key)
        return self._generator
    
    def generate_video(
        self,
        prompt: str,
        image_url: str,
        image_filename: str = "",
        aspect_ratio: str = Config.DEFAULT_ASPECT_RATIO,
        model: str = Config.DEFAULT_MODEL,
        seeds: Optional[int] = None,
        generation_type: str = Config.DEFAULT_GENERATION_TYPE,
    ) -> Dict[str, Any]:
        """
        Generate a video using Veo API.
        
        Args:
            prompt: Text prompt describing the video
            image_url: URL of the reference image
            image_filename: Original image filename
            aspect_ratio: Video aspect ratio
            model: Model to use
            seeds: Random seed for reproducibility
            generation_type: Type of generation
            
        Returns:
            Dictionary with task_id and metadata
            
        Raises:
            Exception: If generation fails
        """
        try:
            result = self.generator.generate_video(
                prompt=prompt,
                image_urls=[image_url],
                model=model,
                aspect_ratio=aspect_ratio,
                seeds=seeds,
                enable_translation=True,
                generation_type=generation_type
            )
            
            task_id = result.get('taskId')
            if not task_id:
                raise Exception("Failed to create video generation task")
            
            logger.info(f"Video generation task created: {task_id}")
            return {
                'task_id': task_id,
                'result': result
            }
        except Exception as e:
            logger.error(f"Error generating video: {e}", exc_info=True)
            raise
    
    def get_video_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get video generation status.
        
        Args:
            task_id: Task ID to check
            
        Returns:
            Dictionary with status information
        """
        try:
            details = self.generator.get_video_details(task_id)
            success_flag = details.get('successFlag')
            response_data = details.get('response', {})
            
            if success_flag == 1:
                return {
                    'status': 'completed',
                    'response_data': response_data,
                    'details': details
                }
            elif success_flag == 0:
                return {
                    'status': 'processing',
                    'details': details
                }
            else:
                error_code = details.get('errorCode')
                error_message = details.get('errorMessage', 'Unknown error')
                return {
                    'status': 'failed',
                    'error_code': error_code,
                    'error_message': error_message,
                    'details': details
                }
        except Exception as e:
            logger.error(f"Error getting video status for {task_id}: {e}", exc_info=True)
            raise
    
    def process_completed_video(
        self,
        task_id: str,
        video_urls: List[str],
        task_metadata: Dict[str, Any],
        upload_folder: str
    ) -> Dict[str, Any]:
        """
        Process a completed video: download and upload to Azure.
        
        Args:
            task_id: Task ID
            video_urls: List of video URLs from Veo API
            task_metadata: Metadata associated with the task
            upload_folder: Local folder for temporary storage
            
        Returns:
            Dictionary with processed video information
        """
        if not video_urls:
            logger.warning(f"No video URLs for task {task_id}")
            return {'azure_video_urls': []}
        
        # Get base filename from input image
        image_filename = task_metadata.get('image_filename', '')
        deck_id = task_metadata.get('deck_id')
        card_id = task_metadata.get('card_id')
        
        if image_filename:
            base_filename = get_base_filename(image_filename)
            
            # If part of a deck, determine video number
            if deck_id and card_id:
                deck = StorageService.get_deck_by_id(deck_id)
                if deck:
                    card = next((c for c in deck.get('cards', []) if c.get('id') == card_id), None)
                    if card:
                        existing_count = len(card.get('video_urls', []))
                        video_number = existing_count + 1
                        base_filename = f"{base_filename}_{video_number}"
        else:
            base_filename = task_id
        
        logger.info(f"Processing video {task_id} with base filename: {base_filename}")
        
        # Download and upload the first video URL to Azure
        azure_video_url = download_and_upload_video(
            video_urls[0],
            base_filename,
            upload_folder
        )
        
        if azure_video_url:
            return {
                'azure_video_urls': [azure_video_url],
                'veo_urls': video_urls,
                'base_filename': base_filename
            }
        else:
            logger.warning(f"Failed to upload video to Azure, using Veo URL as fallback")
            return {
                'azure_video_urls': [],
                'veo_urls': video_urls,
                'base_filename': base_filename
            }
    
    def generate_deck_videos(
        self,
        deck_id: str,
        cards: List[Dict[str, Any]],
        aspect_ratio: str
    ) -> Dict[str, Any]:
        """
        Generate videos for all cards in a deck (batch generation with rate limiting).
        
        Args:
            deck_id: Deck ID
            cards: List of card dictionaries
            aspect_ratio: Aspect ratio for all videos
            
        Returns:
            Dictionary with generation results
        """
        all_task_ids = []
        total_requests = len(cards) * Config.VIDEOS_PER_CARD
        requests_sent = 0
        batch_size = Config.RATE_LIMIT_BATCH_SIZE
        delay_between_batches = Config.RATE_LIMIT_DELAY_SECONDS
        
        logger.info(
            f"Generating {total_requests} videos with rate limiting "
            f"(max {batch_size} requests per {delay_between_batches}s)..."
        )
        
        for card in cards:
            for i in range(Config.VIDEOS_PER_CARD):
                # Rate limiting: wait if we've sent a full batch
                if requests_sent > 0 and requests_sent % batch_size == 0:
                    logger.info(
                        f"Rate limit: Waiting {delay_between_batches}s before next batch... "
                        f"({requests_sent}/{total_requests} requests sent)"
                    )
                    time.sleep(delay_between_batches)
                
                try:
                    result = self.generator.generate_video(
                        prompt=card['prompt'],
                        image_urls=[card['image_url']],
                        model=Config.DEFAULT_MODEL,
                        aspect_ratio=aspect_ratio,
                        enable_translation=True,
                        generation_type=Config.DEFAULT_GENERATION_TYPE
                    )
                    
                    task_id = result.get('taskId')
                    if task_id:
                        if 'task_ids' not in card:
                            card['task_ids'] = []
                        card['task_ids'].append(task_id)
                        all_task_ids.append({
                            'task_id': task_id,
                            'card_id': card['id'],
                            'deck_id': deck_id,
                            'image_filename': card.get('image_filename', ''),
                            'prompt': card['prompt'],
                            'aspect_ratio': aspect_ratio
                        })
                        requests_sent += 1
                        logger.info(f"Request {requests_sent}/{total_requests} sent (Task ID: {task_id})")
                    else:
                        logger.error(f"Failed to get task ID for card {card['id']}, video {i+1}")
                        
                except Exception as e:
                    error_str = str(e).lower()
                    if '429' in error_str or 'rate limit' in error_str or 'too many requests' in error_str:
                        logger.warning("Rate limit hit! Waiting 10 seconds before retrying...")
                        time.sleep(10)
                        # Retry once
                        try:
                            result = self.generator.generate_video(
                                prompt=card['prompt'],
                                image_urls=[card['image_url']],
                                model=Config.DEFAULT_MODEL,
                                aspect_ratio=aspect_ratio,
                                enable_translation=True,
                                generation_type=Config.DEFAULT_GENERATION_TYPE
                            )
                            task_id = result.get('taskId')
                            if task_id:
                                if 'task_ids' not in card:
                                    card['task_ids'] = []
                                card['task_ids'].append(task_id)
                                all_task_ids.append({
                                    'task_id': task_id,
                                    'card_id': card['id'],
                                    'deck_id': deck_id,
                                    'image_filename': card.get('image_filename', ''),
                                    'prompt': card['prompt'],
                                    'aspect_ratio': aspect_ratio
                                })
                                requests_sent += 1
                                logger.info(f"Retry successful: Request {requests_sent}/{total_requests} sent")
                        except Exception as retry_error:
                            logger.error(f"Retry failed: {retry_error}")
                    else:
                        logger.error(f"Error generating video for card {card['id']}, video {i+1}: {e}")
        
        return {
            'task_ids': all_task_ids,
            'cards': cards,
            'total_requests': requests_sent
        }

