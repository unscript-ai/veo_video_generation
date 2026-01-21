"""Status checking service for deck video generation."""
import logging
from typing import Dict, Any, List, Optional

from services.storage_service import StorageService
from services.video_service import VideoService
from utils.azure_utils import download_and_upload_video
from utils.file_utils import get_base_filename
from config import Config

logger = logging.getLogger(__name__)


class StatusService:
    """Service for checking and updating video generation status."""
    
    def __init__(self, video_service: Optional[VideoService] = None):
        """
        Initialize status service.
        
        Args:
            video_service: Video service instance
        """
        self.video_service = video_service or VideoService()
    
    def check_deck_status(
        self,
        deck_id: str,
        pending_tasks: Dict[str, Dict[str, Any]],
        upload_folder: str
    ) -> Dict[str, Any]:
        """
        Check and update status of all pending videos in a deck.
        
        Args:
            deck_id: Deck ID
            pending_tasks: Dictionary of pending task metadata
            upload_folder: Folder for temporary file storage
            
        Returns:
            Dictionary with update results
        """
        deck = StorageService.get_deck_by_id(deck_id)
        if not deck:
            raise ValueError("Deck not found")
        
        updated_count = 0
        
        # Check status of all task IDs in all cards
        for card in deck.get('cards', []):
            task_ids = card.get('task_ids', [])
            existing_video_count = len(card.get('video_urls', []))
            expected_video_count = len(task_ids)
            
            # Track which task_ids have already been processed to avoid duplicates
            # Get mapping from task_id to video_url if it exists
            task_to_video_map = card.get('task_video_map', {})  # task_id -> video_url mapping
            processed_task_ids = set(task_to_video_map.keys())
            
            # Check all tasks, but only process ones that haven't been completed yet
            for task_id in task_ids:
                # Skip if this task_id already has a video assigned
                if task_id in processed_task_ids:
                    # Still check status to update if needed, but don't process again
                    try:
                        status_result = self.video_service.get_video_status(task_id)
                        # If status changed to failed, update it
                        if status_result['status'] == 'failed':
                            self._track_failed_video(
                                task_id,
                                status_result,
                                card
                            )
                    except Exception as e:
                        error_msg = str(e)
                        if "record is null" not in error_msg.lower() and "not found" not in error_msg.lower():
                            logger.debug(f"Error checking already-processed task {task_id[:8]}...: {e}")
                    continue
                
                try:
                    status_result = self.video_service.get_video_status(task_id)
                    
                    if status_result['status'] == 'completed':
                        # Process if this specific task hasn't been processed yet
                        # (even if we have enough videos, we should map the task)
                        if task_id not in processed_task_ids:
                            self._process_completed_video(
                                task_id,
                                status_result,
                                card,
                                deck_id,
                                pending_tasks,
                                upload_folder
                            )
                            updated_count += 1
                        else:
                            logger.debug(
                                f"Task {task_id[:8]}... already processed, skipping"
                            )
                            
                    elif status_result['status'] == 'failed':
                        self._track_failed_video(
                            task_id,
                            status_result,
                            card
                        )
                    
                    # Remove from pending
                    pending_tasks.pop(task_id, None)
                    
                except Exception as e:
                    error_msg = str(e)
                    # Skip "record is null" errors (task still processing)
                    if "record is null" not in error_msg.lower() and "not found" not in error_msg.lower():
                        logger.error(f"Error checking task {task_id}: {e}")
        
        # Update card and deck statuses
        self._update_card_statuses(deck)
        self._update_deck_status(deck)
        
        # Save the updated deck - need to update the entire deck in the list
        decks = StorageService.load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d.get('id') == deck_id), None)
        if deck_index is not None:
            decks[deck_index] = deck
            StorageService.save_decks(decks)
        
        return {
            'updated_videos': updated_count,
            'deck': deck
        }
    
    def _process_completed_video(
        self,
        task_id: str,
        status_result: Dict[str, Any],
        card: Dict[str, Any],
        deck_id: str,
        pending_tasks: Dict[str, Dict[str, Any]],
        upload_folder: str
    ) -> None:
        """Process a completed video."""
        response_data = status_result.get('response_data', {})
        video_urls = response_data.get('resultUrls', [])
        
        if not video_urls:
            return
        
        # Get task metadata
        task_metadata = pending_tasks.get(task_id, {})
        if not task_metadata:
            deck = StorageService.get_deck_by_id(deck_id)
            task_metadata = {
                'image_filename': card.get('image_filename', ''),
                'deck_id': deck_id,
                'card_id': card['id'],
                'prompt': card.get('prompt', ''),
                'image_url': card.get('image_url', ''),
                'aspect_ratio': deck.get('aspect_ratio', Config.DEFAULT_ASPECT_RATIO) if deck else Config.DEFAULT_ASPECT_RATIO,
            }
        
        # Check if this task_id has already been processed
        task_video_map = card.get('task_video_map', {})
        if task_id in task_video_map:
            logger.debug(f"Task {task_id[:8]}... already processed, skipping")
            return  # This task has already been processed
        
        # Check if we need to process this video
        current_video_count = len(card.get('video_urls', []))
        expected_video_count = len(card.get('task_ids', []))
        
        # Check if all expected videos are from unique tasks
        processed_tasks = set(task_video_map.keys())
        if len(processed_tasks) >= expected_video_count:
            return  # All tasks have been processed
        
        # Determine filename
        image_filename = task_metadata.get('image_filename', '')
        if image_filename:
            base_filename = get_base_filename(image_filename)
            video_number = current_video_count + 1
            base_filename = f"{base_filename}_{video_number}"
        else:
            base_filename = task_id
        
        logger.info(
            f"Processing task {task_id[:8]}... for card {card['id'][:8]}...: "
            f"video {video_number}/{expected_video_count}"
        )
        
        # Download and upload to Azure
        azure_video_url = download_and_upload_video(
            video_urls[0],
            base_filename,
            upload_folder
        )
        
        if azure_video_url:
            if 'video_urls' not in card:
                card['video_urls'] = []
            
            # Initialize task_video_map if it doesn't exist
            if 'task_video_map' not in card:
                card['task_video_map'] = {}
            
            # Check if this task_id has already been processed
            if task_id in card['task_video_map']:
                logger.info(
                    f"Task {task_id[:8]}... already processed with video "
                    f"{card['task_video_map'][task_id]}, skipping duplicate"
                )
                return
            
            # Check if URL already exists (different task producing same video)
            if azure_video_url not in card['video_urls']:
                card['video_urls'].append(azure_video_url)
                # Map this task_id to this video URL
                card['task_video_map'][task_id] = azure_video_url
                logger.info(
                    f"Added video to card {card['id'][:8]}... for task {task_id[:8]}... "
                    f"Total: {len(card['video_urls'])}/{expected_video_count}"
                )
            else:
                # Video URL exists but from a different task - still map this task
                existing_task_id = next(
                    (tid for tid, url in card.get('task_video_map', {}).items() if url == azure_video_url),
                    None
                )
                if existing_task_id:
                    logger.warning(
                        f"Video URL already exists for task {existing_task_id[:8]}..., "
                        f"but task {task_id[:8]}... also produced same video. "
                        f"Mapping task {task_id[:8]}... to existing video."
                    )
                card['task_video_map'][task_id] = azure_video_url
        else:
            # Track as failed
            error_msg = "Failed to download or upload video to Azure"
            self._add_failed_task(card, task_id, error_msg, video_number)
            logger.warning(
                f"Failed to process video for task {task_id[:8]}... ({error_msg})"
            )
    
    def _track_failed_video(
        self,
        task_id: str,
        status_result: Dict[str, Any],
        card: Dict[str, Any]
    ) -> None:
        """Track a failed video generation."""
        error_code = status_result.get('error_code', '')
        error_message = status_result.get('error_message', '')
        
        # Build error message
        if error_message:
            error_msg = error_message
            if error_code:
                error_msg = f"{error_message} (Error Code: {error_code})"
        elif error_code:
            error_msg = f"Video generation failed (Error Code: {error_code})"
        else:
            error_msg = "Video generation failed on KIE API"
        
        current_video_count = len(card.get('video_urls', []))
        video_number = current_video_count + 1
        
        logger.warning(f"Task {task_id[:8]}... failed on KIE API side: {error_msg}")
        self._add_failed_task(card, task_id, error_msg, video_number)
    
    def _add_failed_task(
        self,
        card: Dict[str, Any],
        task_id: str,
        error_msg: str,
        video_number: int
    ) -> None:
        """Add a failed task to card tracking."""
        if 'failed_tasks' not in card:
            card['failed_tasks'] = []
        if 'failed_tasks_details' not in card:
            card['failed_tasks_details'] = []
        
        # Check if already tracked
        task_exists = any(
            ft.get('task_id') == task_id
            for ft in card.get('failed_tasks_details', [])
        )
        
        if not task_exists:
            card['failed_tasks'].append(task_id)
            card['failed_tasks_details'].append({
                'task_id': task_id,
                'error': error_msg,
                'video_number': video_number
            })
    
    def _update_card_statuses(self, deck: Dict[str, Any]) -> None:
        """Update status for all cards in a deck."""
        for card in deck['cards']:
            expected_videos = len(card.get('task_ids', []))
            actual_videos = len(card.get('video_urls', []))
            failed_count = len(card.get('failed_tasks', []))
            
            if expected_videos > 0:
                if actual_videos >= expected_videos:
                    card['status'] = 'completed'
                elif actual_videos > 0:
                    if actual_videos + failed_count >= expected_videos:
                        card['status'] = 'partially_completed'
                    else:
                        card['status'] = 'generating'
                elif failed_count > 0 and actual_videos == 0:
                    card['status'] = 'failed'
                else:
                    card['status'] = 'generating'
    
    def _update_deck_status(self, deck: Dict[str, Any]) -> None:
        """Update deck status based on card statuses."""
        cards_with_tasks = [
            c for c in deck['cards']
            if len(c.get('task_ids', [])) > 0
        ]
        
        if not cards_with_tasks:
            return
        
        all_completed = all(
            c.get('status') in ['completed', 'partially_completed', 'failed']
            for c in cards_with_tasks
        )
        
        if all_completed:
            has_any_videos = any(
                len(c.get('video_urls', [])) > 0
                for c in cards_with_tasks
            )
            deck['status'] = 'completed' if has_any_videos else 'failed'
        else:
            deck['status'] = 'generating'

