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
        Get a deck by ID with enriched card data (virtual first_frame/last_frame fields).
        
        Args:
            deck_id: Deck ID
            
        Returns:
            Deck dictionary with enriched cards or None
        """
        deck = StorageService.get_deck_by_id(deck_id)
        if deck:
            # Enrich cards with virtual first_frame/last_frame fields for API compatibility
            deck = self._enrich_deck_cards(deck)
        return deck
    
    @staticmethod
    def _enrich_deck_cards(deck: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich deck cards with virtual first_frame/last_frame fields based on stored data.
        This adds virtual fields without changing the JSON structure.
        
        Args:
            deck: Deck dictionary
            
        Returns:
            Deck with enriched cards (virtual fields added in-memory only)
        """
        if 'cards' not in deck:
            return deck
        
        enriched_deck = deck.copy()
        enriched_deck['cards'] = []
        
        for card in deck.get('cards', []):
            enriched_card = card.copy()
            
            # Add virtual first_frame fields (from image_url - old structure)
            enriched_card['first_frame_url'] = card.get('image_url', '')
            enriched_card['first_frame_filename'] = card.get('image_filename', '')
            
            # Add virtual last_frame fields (from metadata if present)
            metadata = card.get('metadata', {})
            if metadata and isinstance(metadata, dict) and 'last_frame_url' in metadata:
                enriched_card['last_frame_url'] = metadata.get('last_frame_url')
                enriched_card['last_frame_filename'] = metadata.get('last_frame_filename')
            else:
                enriched_card['last_frame_url'] = None
                enriched_card['last_frame_filename'] = None
            
            enriched_deck['cards'].append(enriched_card)
        
        return enriched_deck
    
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
        first_frame_url: str,
        prompt: str,
        first_frame_filename: str = "",
        last_frame_url: Optional[str] = None,
        last_frame_filename: Optional[str] = None,
        # Backward compatibility
        image_url: Optional[str] = None,
        image_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Add a card to a deck.
        
        Args:
            deck_id: Deck ID
            first_frame_url: First frame image URL (required)
            prompt: Video prompt
            first_frame_filename: First frame filename
            last_frame_url: Last frame image URL (optional)
            last_frame_filename: Last frame filename
            image_url: Backward compatibility - if provided, used as first_frame_url
            image_filename: Backward compatibility - if provided, used as first_frame_filename
            
        Returns:
            Created card dictionary
            
        Raises:
            ValueError: If validation fails or deck is full
        """
        # Backward compatibility: if image_url is provided, use it as first_frame_url
        if image_url and not first_frame_url:
            first_frame_url = image_url
        if image_filename and not first_frame_filename:
            first_frame_filename = image_filename
        
        # Validate inputs
        if not first_frame_url or not first_frame_url.strip():
            raise ValueError("First frame image URL is required")
        
        is_valid, error = validate_prompt(prompt)
        if not is_valid:
            raise ValueError(error)
        
        deck = self.get_deck(deck_id)
        if not deck:
            logger.warning(f"Deck not found: {deck_id[:8]}... (trying to add card)")
            # Try to list all decks to help debug
            all_decks = StorageService.load_decks()
            logger.debug(f"Available decks: {[d.get('id', 'no-id')[:8] for d in all_decks]}")
            raise ValueError("Deck not found")
        
        # Check scene limit
        if Config.MAX_CARDS_PER_DECK is not None:
            current_card_count = len(deck.get('cards', []))
            if current_card_count >= Config.MAX_CARDS_PER_DECK:
                raise ValueError(
                    f"Maximum {Config.MAX_CARDS_PER_DECK} scenes allowed per video. "
                    f"Current: {current_card_count}"
                )
        
        # Create new card - keep JSON structure exactly same as old
        # Store first frame in image_url, last frame in metadata if present
        new_card = {
            'id': str(uuid.uuid4()),
            'image_url': first_frame_url,  # First frame stored here (old structure)
            'image_filename': first_frame_filename or '',
            'prompt': prompt,
            'status': 'pending',  # pending, generating, completed
            'task_ids': [],
            'video_urls': [],
            'created_at': datetime.now().isoformat()
        }
        
        # Store last frame info in metadata field (optional, won't break old structure)
        # Only add if last_frame_url is provided
        if last_frame_url:
            if 'metadata' not in new_card:
                new_card['metadata'] = {}
            new_card['metadata']['last_frame_url'] = last_frame_url
            if last_frame_filename:
                new_card['metadata']['last_frame_filename'] = last_frame_filename
        
        decks = StorageService.load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        
        if deck_index is not None:
            decks[deck_index]['cards'].append(new_card)
            decks[deck_index]['updated_at'] = datetime.now().isoformat()
            StorageService.save_decks(decks)
        
        logger.info(f"Added card {new_card['id']} to deck {deck_id}")
        # Return enriched card with virtual fields for API compatibility
        enriched_card = new_card.copy()
        enriched_card['first_frame_url'] = new_card['image_url']
        enriched_card['first_frame_filename'] = new_card['image_filename']
        metadata = new_card.get('metadata', {})
        if metadata and 'last_frame_url' in metadata:
            enriched_card['last_frame_url'] = metadata.get('last_frame_url')
            enriched_card['last_frame_filename'] = metadata.get('last_frame_filename')
        else:
            enriched_card['last_frame_url'] = None
            enriched_card['last_frame_filename'] = None
        return enriched_card
    
    def update_card(
        self,
        deck_id: str,
        card_id: str,
        prompt: Optional[str] = None,
        first_frame_url: Optional[str] = None,
        first_frame_filename: Optional[str] = None,
        last_frame_url: Optional[str] = None,
        last_frame_filename: Optional[str] = None,
        # Backward compatibility
        image_url: Optional[str] = None,
        image_filename: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update a card in a deck.
        
        Args:
            deck_id: Deck ID
            card_id: Card ID
            prompt: New prompt
            first_frame_url: New first frame URL
            first_frame_filename: New first frame filename
            last_frame_url: New last frame URL (None to remove)
            last_frame_filename: New last frame filename
            image_url: Backward compatibility - if provided, used as first_frame_url
            image_filename: Backward compatibility - if provided, used as first_frame_filename
            
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
        
        # Backward compatibility: if image_url is provided, use it as first_frame_url
        if image_url and not first_frame_url:
            first_frame_url = image_url
        if image_filename and not first_frame_filename:
            first_frame_filename = image_filename
        
        # Validate and update - keep JSON structure exactly same as old
        if first_frame_url is not None:
            if not isinstance(first_frame_url, str) or not first_frame_url.strip():
                raise ValueError("First frame URL is required and must be a non-empty string")
            # Store first frame in image_url (old structure)
            card['image_url'] = first_frame_url.strip()
        
        if first_frame_filename is not None:
            card['image_filename'] = first_frame_filename
        
        # Store last frame in metadata field (optional, won't break old structure)
        if last_frame_url is not None:  # Allow setting to None to remove last frame
            if isinstance(last_frame_url, str) and last_frame_url.strip():
                if 'metadata' not in card:
                    card['metadata'] = {}
                card['metadata']['last_frame_url'] = last_frame_url.strip()
                if last_frame_filename and isinstance(last_frame_filename, str) and last_frame_filename.strip():
                    card['metadata']['last_frame_filename'] = last_frame_filename.strip()
            else:
                # Remove last frame metadata if clearing it
                if 'metadata' in card:
                    card['metadata'].pop('last_frame_url', None)
                    card['metadata'].pop('last_frame_filename', None)
                    # Clean up empty metadata
                    if not card['metadata']:
                        card.pop('metadata', None)
        
        if last_frame_filename is not None and last_frame_url is None:
            # If only filename is provided without URL, update metadata if it exists
            if 'metadata' in card and 'last_frame_url' in card['metadata']:
                if isinstance(last_frame_filename, str) and last_frame_filename.strip():
                    card['metadata']['last_frame_filename'] = last_frame_filename.strip()
        
        if prompt is not None:
            is_valid, error = validate_prompt(prompt)
            if not is_valid:
                raise ValueError(error)
            card['prompt'] = prompt
        
        card['updated_at'] = datetime.now().isoformat()
        decks[deck_index]['updated_at'] = datetime.now().isoformat()
        StorageService.save_decks(decks)
        
        logger.info(f"Updated card {card_id} in deck {deck_id}")
        # Return enriched card with virtual fields for API compatibility
        enriched_card = card.copy()
        enriched_card['first_frame_url'] = card.get('image_url', '')
        enriched_card['first_frame_filename'] = card.get('image_filename', '')
        metadata = card.get('metadata', {})
        if metadata and isinstance(metadata, dict) and 'last_frame_url' in metadata:
            enriched_card['last_frame_url'] = metadata.get('last_frame_url')
            enriched_card['last_frame_filename'] = metadata.get('last_frame_filename')
        else:
            enriched_card['last_frame_url'] = None
            enriched_card['last_frame_filename'] = None
        return enriched_card
    
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

