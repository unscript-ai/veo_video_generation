"""
Flask web application for Veo Video Generation with Azure Storage integration.

This is a refactored version with improved structure, logging, and best practices.
"""
import os
import logging
import time
from flask import Flask, render_template, request, jsonify, g
from werkzeug.utils import secure_filename

from config import Config
from utils.logging_config import setup_logging
from utils.file_utils import generate_unique_filename, ensure_directory_exists
from utils.validation import validate_image_file, validate_deck_name
from utils.azure_utils import upload_to_azure_blob, download_and_upload_video
from services.storage_service import StorageService
from services.video_service import VideoService
from services.deck_service import DeckService
from services.status_service import StatusService

# Initialize logging
log_level = os.getenv('LOG_LEVEL', 'INFO')
# Use timestamped log files by default (each app run gets its own file)
# Set LOG_FILE to disable timestamping, or set USE_TIMESTAMPED_LOGS=false
use_timestamp = os.getenv('USE_TIMESTAMPED_LOGS', 'true').lower() == 'true'
log_file = os.getenv('LOG_FILE')  # If set, use this file (disables timestamping)
actual_log_file = setup_logging(
    level=log_level,
    log_file=log_file if not use_timestamp else None,
    use_timestamp=use_timestamp
)
logger = logging.getLogger(__name__)
logger.info(f"Logging to: {actual_log_file}")

# Validate configuration
try:
    Config.validate()
except ValueError as e:
    logger.error(f"Configuration error: {e}")
    raise

# Initialize Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = Config.MAX_CONTENT_LENGTH
app.config['SECRET_KEY'] = Config.SECRET_KEY

# Ensure directories exist
ensure_directory_exists(Config.UPLOAD_FOLDER)
ensure_directory_exists('logs')  # For log files

# Initialize services
video_service = VideoService()
deck_service = DeckService(video_service)
status_service = StatusService(video_service)

# In-memory storage for pending tasks (in production, consider Redis or database)
pending_tasks: dict[str, dict] = {}

# Flag to prevent multiple simultaneous failed task updates
_failed_task_update_in_progress = False


# ============================================================================
# Request Logging Middleware
# ============================================================================

@app.before_request
def log_request_info():
    """Log all incoming requests with details."""
    g.start_time = time.time()
    
    # Log request details
    logger.info(
        f"[REQUEST] {request.method} {request.path} | "
        f"IP: {request.remote_addr} | "
        f"User-Agent: {request.headers.get('User-Agent', 'Unknown')[:50]}"
    )
    
    # Log query parameters if present
    if request.args:
        logger.debug(f"[QUERY] {dict(request.args)}")
    
    # Log form data for POST requests (excluding file uploads)
    if request.method == 'POST' and request.is_json:
        try:
            data = request.get_json(silent=True)
            if data:
                # Don't log full prompts/images to keep logs clean
                sanitized_data = {}
                for key, value in data.items():
                    if key == 'prompt' and isinstance(value, str):
                        sanitized_data[key] = value[:100] + '...' if len(value) > 100 else value
                    elif key == 'image_url':
                        sanitized_data[key] = value.split('/')[-1] if '/' in value else value
                    else:
                        sanitized_data[key] = value
                logger.debug(f"[POST DATA] {sanitized_data}")
        except Exception:
            pass


@app.after_request
def log_response_info(response):
    """Log response details and request duration."""
    # Calculate request duration
    duration = time.time() - g.start_time if hasattr(g, 'start_time') else 0
    
    # Log response
    logger.info(
        f"[RESPONSE] {request.method} {request.path} | "
        f"Status: {response.status_code} | "
        f"Duration: {duration:.3f}s"
    )
    
    return response


@app.errorhandler(Exception)
def log_exceptions(error):
    """Log all exceptions."""
    logger.error(
        f"[ERROR] {request.method} {request.path} | "
        f"Error: {str(error)}",
        exc_info=True
    )
    raise error


# ============================================================================
# Frontend Routes
# ============================================================================

@app.route('/')
def index():
    """Render the main page."""
    logger.info("[PAGE] Rendering index.html - Main Video Generator")
    return render_template('index.html')


@app.route('/history')
def history():
    """Render the video history page."""
    logger.info("[PAGE] Rendering history.html - Video History")
    return render_template('history.html')


@app.route('/decks')
def decks():
    """Render the decks management page."""
    logger.info("[PAGE] Rendering decks.html - Deck Management")
    return render_template('decks.html')


@app.route('/deck/<deck_id>')
def deck_detail(deck_id):
    """Render the deck detail page."""
    logger.info(f"[PAGE] Rendering deck_detail.html - Deck ID: {deck_id}")
    return render_template('deck_detail.html', deck_id=deck_id)


@app.route('/deck/<deck_id>/results')
def deck_results(deck_id):
    """Render the deck results page."""
    logger.info(f"[PAGE] Rendering deck_results.html - Deck ID: {deck_id}")
    return render_template('deck_results.html', deck_id=deck_id)


# ============================================================================
# API Routes - Image Upload
# ============================================================================

@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    """Handle image upload and upload to Azure Storage."""
    logger.info("[API] Image upload requested")
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        file = request.files['image']
        is_valid, error_msg = validate_image_file(file)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
        
        # Generate unique filename and save temporarily
        unique_filename = generate_unique_filename(file.filename)
        local_path = os.path.join(Config.UPLOAD_FOLDER, unique_filename)
        file.save(local_path)
        
        try:
            # Upload to Azure
            blob_name = f"{Config.AZURE_BLOB_PATH_INPUT}{unique_filename}"
            blob_url = upload_to_azure_blob(local_path, blob_name)
            
            logger.info(f"[API] Image uploaded successfully: {unique_filename} -> {blob_url}")
            
            return jsonify({
                'success': True,
                'image_url': blob_url,
                'filename': unique_filename,
                'base_filename': unique_filename.rsplit('.', 1)[0]
            })
        finally:
            # Clean up local file
            if os.path.exists(local_path):
                os.remove(local_path)
    
    except Exception as e:
        logger.error(f"Error uploading image: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ============================================================================
# API Routes - Video Generation
# ============================================================================

@app.route('/api/generate-video', methods=['POST'])
def generate_video():
    """Generate video using Veo API."""
    logger.info("[API] Video generation requested")
    try:
        data = request.json
        
        # Validate required fields
        if not data or not data.get('image_url'):
            return jsonify({'error': 'Image URL is required'}), 400
        if not data.get('prompt'):
            return jsonify({'error': 'Prompt is required'}), 400
        
        # Extract parameters
        image_url = data['image_url']
        image_filename = data.get('image_filename', '')
        prompt = data['prompt']
        aspect_ratio = data.get('aspect_ratio', Config.DEFAULT_ASPECT_RATIO)
        model = data.get('model', Config.DEFAULT_MODEL)
        seeds = data.get('seeds')
        generation_type = data.get('generation_type', Config.DEFAULT_GENERATION_TYPE)
        
        # Generate video
        result = video_service.generate_video(
            prompt=prompt,
            image_url=image_url,
            image_filename=image_filename,
            aspect_ratio=aspect_ratio,
            model=model,
            seeds=seeds,
            generation_type=generation_type
        )
        
        task_id = result['task_id']
        
        # Store task metadata
        if not image_filename and '/' in image_url:
            image_filename = image_url.split('/')[-1]
        
        pending_tasks[task_id] = {
            'prompt': prompt,
            'image_url': image_url,
            'image_filename': image_filename,
            'aspect_ratio': aspect_ratio,
            'model': model,
            'generation_type': generation_type,
            'created_at': __import__('datetime').datetime.now().isoformat()
        }
        
        logger.info(f"[API] Video generation started - Task ID: {task_id}, Model: {model}, Aspect: {aspect_ratio}")
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': 'Video generation started'
        })
    
    except Exception as e:
        logger.error(f"Error generating video: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/video-status/<task_id>', methods=['GET'])
def get_video_status(task_id):
    """Get video generation status."""
    logger.debug(f"[API] Checking video status for task: {task_id[:8]}...")
    try:
        status_result = video_service.get_video_status(task_id)
        status = status_result['status']
        
        logger.debug(f"[STATUS] Task {task_id[:8]}... status: {status}")
        
        if status == 'completed':
            response_data = status_result.get('response_data', {})
            video_urls = response_data.get('resultUrls', [])
            origin_urls = response_data.get('originUrls', [])
            
            # Get stored metadata
            task_metadata = pending_tasks.pop(task_id, {})
            
            # Process completed video
            if video_urls:
                processed = video_service.process_completed_video(
                    task_id,
                    video_urls,
                    task_metadata,
                    Config.UPLOAD_FOLDER
                )
                final_video_urls = processed.get('azure_video_urls') or video_urls
            else:
                final_video_urls = []
            
            # Save to history
            video_data = {
                'task_id': task_id,
                'video_urls': final_video_urls,
                'origin_urls': origin_urls,
                'veo_urls': video_urls,
                'resolution': response_data.get('resolution', 'N/A'),
                'prompt': task_metadata.get('prompt', ''),
                'image_url': task_metadata.get('image_url', ''),
                'aspect_ratio': task_metadata.get('aspect_ratio', ''),
                'model': task_metadata.get('model', ''),
                'generation_type': task_metadata.get('generation_type', ''),
                'created_at': task_metadata.get('created_at', __import__('datetime').datetime.now().isoformat())
            }
            StorageService.add_to_history(video_data)
            
            logger.info(
                f"[STATUS] Video generation completed - Task ID: {task_id[:8]}... | "
                f"Resolution: {response_data.get('resolution', 'N/A')} | "
                f"Videos: {len(final_video_urls)}"
            )
            
            return jsonify({
                'status': 'completed',
                'task_id': task_id,
                'video_urls': final_video_urls,
                'origin_urls': origin_urls,
                'resolution': response_data.get('resolution', 'N/A')
            })
        
        elif status == 'processing':
            return jsonify({
                'status': 'processing',
                'task_id': task_id
            })
        
        else:  # failed
            return jsonify({
                'status': 'failed',
                'task_id': task_id,
                'error': status_result.get('error_message', 'Unknown error')
            }), 400
    
    except Exception as e:
        logger.error(f"Error getting video status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/video-history', methods=['GET'])
def get_video_history():
    """Get all video generation history."""
    try:
        history = StorageService.load_video_history()
        return jsonify({
            'success': True,
            'history': history,
            'count': len(history)
        })
    except Exception as e:
        logger.error(f"Error loading video history: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ============================================================================
# API Routes - Decks
# ============================================================================

@app.route('/api/decks', methods=['GET'])
def get_decks():
    """Get all decks."""
    logger.debug("[API] Fetching all decks")
    try:
        decks = StorageService.load_decks()
        logger.debug(f"[API] Retrieved {len(decks)} deck(s)")
        return jsonify({
            'success': True,
            'decks': decks,
            'count': len(decks)
        })
    except Exception as e:
        logger.error(f"Error loading decks: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks', methods=['POST'])
def create_deck():
    """Create a new deck."""
    logger.info("[API] Creating new deck")
    try:
        data = request.json or {}
        deck_name = data.get('name', '').strip()
        aspect_ratio = data.get('aspect_ratio', Config.DEFAULT_ASPECT_RATIO)
        
        new_deck = deck_service.create_deck(deck_name, aspect_ratio)
        
        logger.info(f"[API] Deck created - ID: {new_deck['id'][:8]}..., Name: {deck_name}, Aspect: {aspect_ratio}")
        
        return jsonify({
            'success': True,
            'deck': new_deck
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error creating deck: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>', methods=['GET'])
def get_deck(deck_id):
    """Get a specific deck."""
    try:
        deck = deck_service.get_deck(deck_id)
        if not deck:
            return jsonify({'error': 'Deck not found'}), 404
        
        return jsonify({
            'success': True,
            'deck': deck
        })
    except Exception as e:
        logger.error(f"Error getting deck: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>', methods=['PUT'])
def update_deck(deck_id):
    """Update a deck."""
    try:
        data = request.json or {}
        
        updated_deck = deck_service.update_deck(
            deck_id,
            name=data.get('name'),
            aspect_ratio=data.get('aspect_ratio'),
            status=data.get('status')
        )
        
        if not updated_deck:
            return jsonify({'error': 'Deck not found'}), 404
        
        return jsonify({
            'success': True,
            'deck': updated_deck
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error updating deck: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>', methods=['DELETE'])
def delete_deck(deck_id):
    """Delete a deck."""
    try:
        deck = deck_service.get_deck(deck_id)
        if not deck:
            return jsonify({'error': 'Deck not found'}), 404
        
        success = deck_service.delete_deck(deck_id)
        if success:
            return jsonify({
                'success': True,
                'message': f'Deck "{deck["name"]}" deleted successfully'
            })
        else:
            return jsonify({'error': 'Failed to delete deck'}), 500
    
    except Exception as e:
        logger.error(f"Error deleting deck: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/cards', methods=['POST'])
def add_card_to_deck(deck_id):
    """Add a card to a deck."""
    try:
        data = request.json or {}
        image_url = data.get('image_url', '').strip()
        prompt = data.get('prompt', '').strip()
        image_filename = data.get('image_filename', '')
        
        card = deck_service.add_card_to_deck(
            deck_id,
            image_url,
            prompt,
            image_filename
        )
        
        return jsonify({
            'success': True,
            'card': card
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error adding card: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/cards/<card_id>', methods=['PUT'])
def update_card(deck_id, card_id):
    """Update a card in a deck."""
    try:
        data = request.json or {}
        
        card = deck_service.update_card(
            deck_id,
            card_id,
            image_url=data.get('image_url'),
            prompt=data.get('prompt'),
            image_filename=data.get('image_filename')
        )
        
        if not card:
            return jsonify({'error': 'Card not found'}), 404
        
        return jsonify({
            'success': True,
            'card': card
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error updating card: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/cards/<card_id>', methods=['DELETE'])
def delete_card(deck_id, card_id):
    """Delete a card from a deck."""
    try:
        success = deck_service.delete_card(deck_id, card_id)
        if not success:
            return jsonify({'error': 'Card not found'}), 404
        
        return jsonify({
            'success': True
        })
    except Exception as e:
        logger.error(f"Error deleting card: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/generate', methods=['POST'])
def generate_deck_videos(deck_id):
    """Generate videos for all cards in a deck."""
    logger.info(f"[API] Starting video generation for deck: {deck_id[:8]}...")
    try:
        result = deck_service.generate_deck_videos(deck_id)
        
        # Store pending tasks
        pending_tasks.update(result['pending_tasks'])
        
        deck = deck_service.get_deck(deck_id)
        
        logger.info(
            f"[API] Deck video generation started - Deck: {deck_id[:8]}... | "
            f"Cards: {len(deck['cards'])} | "
            f"Total Tasks: {result['task_count']}"
        )
        
        return jsonify({
            'success': True,
            'message': f'Started generation for {len(deck["cards"])} scenes ({Config.VIDEOS_PER_CARD} videos each)',
            'task_count': result['task_count'],
            'deck': deck
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error generating deck videos: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/check-status', methods=['POST'])
def check_deck_status(deck_id):
    """Check and update status of all pending videos in a deck."""
    logger.debug(f"[API] Checking status for deck: {deck_id[:8]}...")
    try:
        result = status_service.check_deck_status(
            deck_id,
            pending_tasks,
            Config.UPLOAD_FOLDER
        )
        
        if result['updated_videos'] > 0:
            logger.info(
                f"[STATUS] Deck status updated - Deck: {deck_id[:8]}... | "
                f"New Videos: {result['updated_videos']} | "
                f"Status: {result['deck'].get('status', 'unknown')}"
            )
        
        return jsonify({
            'success': True,
            'updated_videos': result['updated_videos'],
            'deck': result['deck']
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        logger.error(f"Error checking deck status: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/videos', methods=['GET'])
def get_deck_videos(deck_id):
    """Get all videos for a specific deck."""
    try:
        deck = deck_service.get_deck(deck_id)
        if not deck:
            return jsonify({'error': 'Deck not found'}), 404
        
        # Collect all videos and failed tasks
        all_videos = []
        all_failed = []
        
        for card_index, card in enumerate(deck.get('cards', [])):
            # Add successful videos
            approved_videos = card.get('approved_videos', [])
            for video_url in card.get('video_urls', []):
                all_videos.append({
                    'card_id': card['id'],
                    'card_index': card_index,
                    'card_prompt': card['prompt'],
                    'card_image_url': card['image_url'],
                    'video_url': video_url,
                    'approved': video_url in approved_videos,
                    'created_at': card.get('created_at', ''),
                    'status': 'success'
                })
            
            # Add failed tasks
            failed_details = card.get('failed_tasks_details', [])
            for failed_detail in failed_details:
                all_failed.append({
                    'card_id': card['id'],
                    'card_index': card_index,
                    'card_prompt': card['prompt'],
                    'card_image_url': card['image_url'],
                    'error': failed_detail.get('error', 'Unknown error'),
                    'task_id': failed_detail.get('task_id', ''),
                    'video_number': failed_detail.get('video_number', 0),
                    'created_at': card.get('created_at', ''),
                    'status': 'failed'
                })
        
        return jsonify({
            'success': True,
            'videos': all_videos,
            'failed': all_failed,
            'count': len(all_videos),
            'failed_count': len(all_failed),
            'deck': {
                'id': deck['id'],
                'name': deck['name'],
                'status': deck['status']
            }
        })
    except Exception as e:
        logger.error(f"Error getting deck videos: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/approve-video', methods=['POST'])
def approve_video(deck_id):
    """Approve a video for a specific card in a deck."""
    logger.info(f"[API] Approving video for deck: {deck_id[:8]}...")
    try:
        data = request.json or {}
        video_url = data.get('video_url', '').strip()
        card_id = data.get('card_id', '').strip()
        
        if not video_url:
            return jsonify({'error': 'Video URL is required'}), 400
        if not card_id:
            return jsonify({'error': 'Card ID is required'}), 400
        
        deck = deck_service.get_deck(deck_id)
        if not deck:
            return jsonify({'error': 'Deck not found'}), 404
        
        # Find the card
        card = next((c for c in deck.get('cards', []) if c.get('id') == card_id), None)
        if not card:
            return jsonify({'error': 'Card not found'}), 404
        
        # Verify video URL exists in card
        if video_url not in card.get('video_urls', []):
            return jsonify({'error': 'Video not found in this card'}), 404
        
        # Initialize approved_videos if it doesn't exist
        if 'approved_videos' not in card:
            card['approved_videos'] = []
        
        # Add to approved list if not already approved
        if video_url not in card['approved_videos']:
            card['approved_videos'].append(video_url)
            
            # Update the deck
            decks = StorageService.load_decks()
            deck_index = next((i for i, d in enumerate(decks) if d.get('id') == deck_id), None)
            
            if deck_index is not None:
                card_index = next((i for i, c in enumerate(decks[deck_index]['cards']) if c.get('id') == card_id), None)
                if card_index is not None:
                    decks[deck_index]['cards'][card_index] = card
                    decks[deck_index]['updated_at'] = __import__('datetime').datetime.now().isoformat()
                    StorageService.save_decks(decks)
                    
                    logger.info(
                        f"[API] Video approved - Deck: {deck_id[:8]}... | "
                        f"Card: {card_id[:8]}... | "
                        f"Video: {video_url.split('/')[-1]}"
                    )
        
        return jsonify({
            'success': True,
            'message': 'Video approved successfully',
            'approved': True
        })
    
    except Exception as e:
        logger.error(f"Error approving video: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/unapprove-video', methods=['POST'])
def unapprove_video(deck_id):
    """Unapprove a video for a specific card in a deck."""
    logger.info(f"[API] Unapproving video for deck: {deck_id[:8]}...")
    try:
        data = request.json or {}
        video_url = data.get('video_url', '').strip()
        card_id = data.get('card_id', '').strip()
        
        if not video_url:
            return jsonify({'error': 'Video URL is required'}), 400
        if not card_id:
            return jsonify({'error': 'Card ID is required'}), 400
        
        deck = deck_service.get_deck(deck_id)
        if not deck:
            return jsonify({'error': 'Deck not found'}), 404
        
        # Find the card
        card = next((c for c in deck.get('cards', []) if c.get('id') == card_id), None)
        if not card:
            return jsonify({'error': 'Card not found'}), 404
        
        # Initialize approved_videos if it doesn't exist
        if 'approved_videos' not in card:
            card['approved_videos'] = []
        
        # Remove from approved list if it exists
        if video_url in card['approved_videos']:
            card['approved_videos'].remove(video_url)
            
            # Update the deck
            decks = StorageService.load_decks()
            deck_index = next((i for i, d in enumerate(decks) if d.get('id') == deck_id), None)
            
            if deck_index is not None:
                card_index = next((i for i, c in enumerate(decks[deck_index]['cards']) if c.get('id') == card_id), None)
                if card_index is not None:
                    decks[deck_index]['cards'][card_index] = card
                    decks[deck_index]['updated_at'] = __import__('datetime').datetime.now().isoformat()
                    StorageService.save_decks(decks)
                    
                    logger.info(
                        f"[API] Video unapproved - Deck: {deck_id[:8]}... | "
                        f"Card: {card_id[:8]}... | "
                        f"Video: {video_url.split('/')[-1]}"
                    )
        else:
            # Video wasn't approved, but return success anyway
            logger.debug(f"Video was not approved, nothing to unapprove: {video_url.split('/')[-1]}")
        
        return jsonify({
            'success': True,
            'message': 'Video unapproved successfully',
            'approved': False
        })
    
    except Exception as e:
        logger.error(f"Error unapproving video: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/update-failed-tasks', methods=['POST'])
def update_all_failed_tasks():
    """Retroactively check and update failed tasks for all existing decks."""
    global _failed_task_update_in_progress
    
    # Prevent multiple simultaneous updates
    if _failed_task_update_in_progress:
        logger.debug("Failed task update already in progress, skipping duplicate request")
        return jsonify({
            'success': True,
            'message': 'Update already in progress',
            'total_updated': 0,
            'decks_checked': 0
        })
    
    try:
        _failed_task_update_in_progress = True
        decks = StorageService.load_decks()
        total_updated = 0
        
        if decks:
            logger.debug(f"Starting retroactive failed task update for {len(decks)} decks...")
        
        for deck in decks:
            deck_updated = False
            for card in deck.get('cards', []):
                task_ids = card.get('task_ids', [])
                video_urls = card.get('video_urls', [])
                expected_count = len(task_ids)
                actual_count = len(video_urls) if video_urls else 0
                
                if expected_count > 0 and actual_count < expected_count:
                    if 'failed_tasks' not in card:
                        card['failed_tasks'] = []
                    if 'failed_tasks_details' not in card:
                        card['failed_tasks_details'] = []
                    
                    for task_id in task_ids:
                        already_tracked = any(
                            ft.get('task_id') == task_id
                            for ft in card.get('failed_tasks_details', [])
                        )
                        if already_tracked:
                            continue
                        
                        try:
                            status_result = video_service.get_video_status(task_id)
                            
                            if status_result['status'] == 'failed':
                                video_number = actual_count + len(card.get('failed_tasks_details', [])) + 1
                                error_msg = status_result.get('error_message', 'Unknown error')
                                
                                card['failed_tasks'].append(task_id)
                                card['failed_tasks_details'].append({
                                    'task_id': task_id,
                                    'error': error_msg,
                                    'video_number': video_number
                                })
                                deck_updated = True
                                total_updated += 1
                                logger.info(
                                    f"Tracked failed task {task_id[:8]}... for card {card['id'][:8]}... "
                                    f"in deck {deck['name']}: {error_msg}"
                                )
                        except Exception as e:
                            error_msg = str(e)
                            if "record is null" not in error_msg.lower() and "not found" not in error_msg.lower():
                                logger.warning(f"Could not check task {task_id[:8]}...: {e}")
            
            if deck_updated:
                StorageService.update_deck(deck['id'], {'updated_at': __import__('datetime').datetime.now().isoformat()})
        
        StorageService.save_decks(decks)
        
        if total_updated > 0:
            logger.info(f"Updated {total_updated} failed tasks across {len(decks)} decks")
        
        return jsonify({
            'success': True,
            'message': f'Updated {total_updated} failed tasks across {len(decks)} decks',
            'total_updated': total_updated,
            'decks_checked': len(decks)
        })
    except Exception as e:
        logger.error(f"Error updating failed tasks: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    finally:
        _failed_task_update_in_progress = False


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Resource not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}", exc_info=True)
    return jsonify({'error': 'Internal server error'}), 500


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Veo Video Generation application on port {port}")
    app.run(debug=debug, host='0.0.0.0', port=port)

