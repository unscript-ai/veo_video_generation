"""Deck management service."""
import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime

from config import Config
from services.storage_service import StorageService
from services.video_service import VideoService
from utils.validation import validate_deck_name, validate_prompt

logger = logging.getLogger(__name__)


class DeckService:
    """Service for deck operations."""
    
    def __init__(self, video_service: Optional[VideoService] = None):
        """
        Initialize deck service.
        
        Args:
            video_service: Video service instance (creates new one if not provided)
        """
        self.video_service = video_service or VideoService()
    
    def create_deck(self, name: str, aspect_ratio: str = Config.DEFAULT_ASPECT_RATIO) -> Dict[str, Any]:
        """
        Create a new deck.
        
        Args:
            name: Deck name
            aspect_ratio: Aspect ratio for videos
            
        Returns:
            Created deck dictionary
            
        Raises:
            ValueError: If validation fails
        """
        is_valid, error = validate_deck_name(name)
        if not is_valid:
            raise ValueError(error)
        
        decks = StorageService.load_decks()
        
        new_deck = {
            'id': str(uuid.uuid4()),
            'name': name,
            'aspect_ratio': aspect_ratio,
            'cards': [],
            'status': 'draft',  # draft, generating, completed
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        decks.append(new_deck)
        StorageService.save_decks(decks)
        
        logger.info(f"Created deck: {new_deck['id']} - {name}")
        return new_deck
    
    def get_deck(self, deck_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a deck by ID.
        
        Args:
            deck_id: Deck ID
            
        Returns:
            Deck dictionary or None
        """
        return StorageService.get_deck_by_id(deck_id)
    
    def update_deck(
        self,
        deck_id: str,
        name: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        status: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update deck properties.
        
        Args:
            deck_id: Deck ID
            name: New deck name
            aspect_ratio: New aspect ratio
            status: New status
            
        Returns:
            Updated deck dictionary or None
        """
        updates = {}
        if name is not None:
            is_valid, error = validate_deck_name(name)
            if not is_valid:
                raise ValueError(error)
            updates['name'] = name
        if aspect_ratio is not None:
            updates['aspect_ratio'] = aspect_ratio
        if status is not None:
            updates['status'] = status
        
        return StorageService.update_deck(deck_id, updates)
    
    def delete_deck(self, deck_id: str) -> bool:
        """
        Delete a deck.
        
        Args:
            deck_id: Deck ID
            
        Returns:
            True if successful
        """
        return StorageService.delete_deck(deck_id)
    
    def add_card_to_deck(
        self,
        deck_id: str,
        image_url: str,
        prompt: str,
        image_filename: str = ""
    ) -> Dict[str, Any]:
        """
        Add a card to a deck.
        
        Args:
            deck_id: Deck ID
            image_url: Image URL
            prompt: Video prompt
            image_filename: Original image filename
            
        Returns:
            Created card dictionary
            
        Raises:
            ValueError: If validation fails or deck is full
        """
        # Validate inputs
        if not image_url.strip():
            raise ValueError("Image URL is required")
        
        is_valid, error = validate_prompt(prompt)
        if not is_valid:
            raise ValueError(error)
        
        deck = self.get_deck(deck_id)
        if not deck:
            raise ValueError("Deck not found")
        
        # Check scene limit
        if Config.MAX_CARDS_PER_DECK is not None:
            current_card_count = len(deck.get('cards', []))
            if current_card_count >= Config.MAX_CARDS_PER_DECK:
                raise ValueError(
                    f"Maximum {Config.MAX_CARDS_PER_DECK} scenes allowed per video. "
                    f"Current: {current_card_count}"
                )
        
        # Create new card
        new_card = {
            'id': str(uuid.uuid4()),
            'image_url': image_url,
            'image_filename': image_filename,
            'prompt': prompt,
            'status': 'pending',  # pending, generating, completed
            'task_ids': [],
            'video_urls': [],
            'created_at': datetime.now().isoformat()
        }
        
        decks = StorageService.load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        
        if deck_index is not None:
            decks[deck_index]['cards'].append(new_card)
            decks[deck_index]['updated_at'] = datetime.now().isoformat()
            StorageService.save_decks(decks)
        
        logger.info(f"Added card {new_card['id']} to deck {deck_id}")
        return new_card
    
    def update_card(
        self,
        deck_id: str,
        card_id: str,
        image_url: Optional[str] = None,
        prompt: Optional[str] = None,
        image_filename: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update a card in a deck.
        
        Args:
            deck_id: Deck ID
            card_id: Card ID
            image_url: New image URL
            prompt: New prompt
            image_filename: New image filename
            
        Returns:
            Updated card dictionary or None
        """
        decks = StorageService.load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        
        if deck_index is None:
            return None
        
        deck = decks[deck_index]
        card = next((c for c in deck['cards'] if c['id'] == card_id), None)
        
        if not card:
            return None
        
        # Validate and update
        if image_url is not None:
            if not image_url.strip():
                raise ValueError("Image URL is required")
            card['image_url'] = image_url
        
        if prompt is not None:
            is_valid, error = validate_prompt(prompt)
            if not is_valid:
                raise ValueError(error)
            card['prompt'] = prompt
        
        if image_filename is not None:
            card['image_filename'] = image_filename
        
        card['updated_at'] = datetime.now().isoformat()
        decks[deck_index]['updated_at'] = datetime.now().isoformat()
        StorageService.save_decks(decks)
        
        logger.info(f"Updated card {card_id} in deck {deck_id}")
        return card
    
    def delete_card(self, deck_id: str, card_id: str) -> bool:
        """
        Delete a card from a deck.
        
        Args:
            deck_id: Deck ID
            card_id: Card ID
            
        Returns:
            True if successful
        """
        decks = StorageService.load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        
        if deck_index is None:
            return False
        
        deck = decks[deck_index]
        original_count = len(deck['cards'])
        deck['cards'] = [c for c in deck['cards'] if c['id'] != card_id]
        
        if len(deck['cards']) < original_count:
            deck['updated_at'] = datetime.now().isoformat()
            StorageService.save_decks(decks)
            logger.info(f"Deleted card {card_id} from deck {deck_id}")
            return True
        
        return False
    
    def generate_deck_videos(self, deck_id: str) -> Dict[str, Any]:
        """
        Generate videos for all cards in a deck.
        
        Args:
            deck_id: Deck ID
            
        Returns:
            Generation result dictionary
        """
        deck = self.get_deck(deck_id)
        if not deck:
            raise ValueError("Deck not found")
        
        if not deck.get('cards'):
            raise ValueError("No scenes in video")
        
        # Check if already generating
        total_videos = sum(len(card.get('video_urls', [])) for card in deck['cards'])
        if deck['status'] == 'generating' and total_videos > 0:
            raise ValueError("Deck is already generating. Please wait for completion.")
        
        # Update deck status
        StorageService.update_deck(deck_id, {'status': 'generating'})
        
        # Reset card statuses and clear previous videos
        decks = StorageService.load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        
        if deck_index is not None:
            for card in decks[deck_index]['cards']:
                card['status'] = 'generating'
                card['video_urls'] = []
                card['task_ids'] = []
            StorageService.save_decks(decks)
        
        # Generate videos
        result = self.video_service.generate_deck_videos(
            deck_id,
            deck['cards'],
            deck['aspect_ratio']
        )
        
        # Store task metadata
        pending_tasks = {}
        for task_info in result['task_ids']:
            card = next(
                (c for c in deck['cards'] if c['id'] == task_info['card_id']),
                None
            )
            if card:
                pending_tasks[task_info['task_id']] = {
                    'deck_id': task_info['deck_id'],
                    'card_id': task_info['card_id'],
                    'prompt': task_info['prompt'],
                    'image_url': card['image_url'],
                    'image_filename': task_info['image_filename'],
                    'aspect_ratio': task_info['aspect_ratio'],
                    'model': Config.DEFAULT_MODEL,
                    'generation_type': Config.DEFAULT_GENERATION_TYPE,
                    'created_at': datetime.now().isoformat()
                }
        
        # Update cards with task_ids
        decks = StorageService.load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        
        if deck_index is not None:
            decks[deck_index]['cards'] = result['cards']
            StorageService.save_decks(decks)
        
        logger.info(
            f"Started generation for deck {deck_id}: "
            f"{result['total_requests']} videos"
        )
        
        return {
            'task_count': result['total_requests'],
            'pending_tasks': pending_tasks
        }

