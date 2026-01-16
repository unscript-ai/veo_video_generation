"""Storage service for managing video history and decks."""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from config import Config
from utils.json_utils import load_json_file, save_json_file, append_to_json_list

logger = logging.getLogger(__name__)


class StorageService:
    """Service for managing persistent storage."""
    
    @staticmethod
    def load_video_history() -> List[Dict[str, Any]]:
        """
        Load video generation history from JSON file.
        
        Returns:
            List of video history entries
        """
        return load_json_file(Config.HISTORY_FILE, default=[])
    
    @staticmethod
    def save_video_history(history: List[Dict[str, Any]]) -> bool:
        """
        Save video generation history to JSON file.
        
        Args:
            history: List of video history entries
            
        Returns:
            True if successful
        """
        return save_json_file(Config.HISTORY_FILE, history)
    
    @staticmethod
    def add_to_history(video_data: Dict[str, Any]) -> bool:
        """
        Add a completed video to history.
        
        Args:
            video_data: Video data dictionary
            
        Returns:
            True if successful
        """
        # Add timestamp if not present
        if 'created_at' not in video_data:
            video_data['created_at'] = datetime.now().isoformat()
        
        history = StorageService.load_video_history()
        history.insert(0, video_data)  # Add to beginning (most recent first)
        
        # Keep only last N entries
        history = history[:Config.MAX_HISTORY_ENTRIES]
        
        return StorageService.save_video_history(history)
    
    @staticmethod
    def load_decks() -> List[Dict[str, Any]]:
        """
        Load decks from JSON file.
        
        Returns:
            List of deck dictionaries
        """
        return load_json_file(Config.DECKS_FILE, default=[])
    
    @staticmethod
    def save_decks(decks: List[Dict[str, Any]]) -> bool:
        """
        Save decks to JSON file.
        
        Args:
            decks: List of deck dictionaries
            
        Returns:
            True if successful
        """
        return save_json_file(Config.DECKS_FILE, decks)
    
    @staticmethod
    def get_deck_by_id(deck_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a deck by its ID.
        
        Args:
            deck_id: Deck ID
            
        Returns:
            Deck dictionary or None if not found
        """
        decks = StorageService.load_decks()
        return next((d for d in decks if d.get('id') == deck_id), None)
    
    @staticmethod
    def update_deck(deck_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update a deck with new data.
        
        Args:
            deck_id: Deck ID
            updates: Dictionary of fields to update
            
        Returns:
            Updated deck dictionary or None if not found
        """
        decks = StorageService.load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d.get('id') == deck_id), None)
        
        if deck_index is None:
            return None
        
        # Apply updates
        for key, value in updates.items():
            decks[deck_index][key] = value
        
        decks[deck_index]['updated_at'] = datetime.now().isoformat()
        
        if StorageService.save_decks(decks):
            return decks[deck_index]
        return None
    
    @staticmethod
    def delete_deck(deck_id: str) -> bool:
        """
        Delete a deck.
        
        Args:
            deck_id: Deck ID
            
        Returns:
            True if successful
        """
        decks = StorageService.load_decks()
        original_count = len(decks)
        decks = [d for d in decks if d.get('id') != deck_id]
        
        if len(decks) < original_count:
            return StorageService.save_decks(decks)
        return False

