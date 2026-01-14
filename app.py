"""
Flask web application for Veo Video Generation with Azure Storage integration.
"""

import os
import uuid
import json
import time
import requests
from datetime import datetime
from typing import Optional
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from veo_video_generator import VeoVideoGenerator

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['HISTORY_FILE'] = 'video_history.json'
app.config['DECKS_FILE'] = 'decks.json'
app.config['MAX_CARDS_PER_DECK'] = 50  # Maximum scenes per video (set to None for unlimited)

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Azure Blob Storage client
AZURE_STORAGE_ACCOUNT_NAME = os.getenv('AZURE_STORAGE_ACCOUNT_NAME')
AZURE_STORAGE_ACCOUNT_KEY = os.getenv('AZURE_STORAGE_ACCOUNT_KEY')
AZURE_CONTAINER_NAME = 'unai-public'
AZURE_BLOB_PATH_INPUT = 'veo_video_generation/input_images/'
AZURE_BLOB_PATH_OUTPUT = 'veo_video_generation/output_video/'

# Initialize Veo Video Generator (will be initialized after env load)
VEO_API_KEY = os.getenv('VEO_API_KEY', 'd9b6abd85b76487369acdf2cbab1fd8e')
veo_generator = None

def get_veo_generator():
    """Get or create Veo generator instance."""
    global veo_generator
    if veo_generator is None:
        api_key = os.getenv('VEO_API_KEY', 'd9b6abd85b76487369acdf2cbab1fd8e')
        veo_generator = VeoVideoGenerator(api_key)
    return veo_generator


def get_azure_blob_service_client():
    """Create and return Azure Blob Service Client."""
    connection_string = (
        f"DefaultEndpointsProtocol=https;"
        f"AccountName={AZURE_STORAGE_ACCOUNT_NAME};"
        f"AccountKey={AZURE_STORAGE_ACCOUNT_KEY};"
        f"EndpointSuffix=core.windows.net"
    )
    return BlobServiceClient.from_connection_string(connection_string)


def generate_unique_filename(original_filename: str) -> str:
    """
    Generate a unique filename with timestamp and UUID.
    
    Format: YYYYMMDD_HHMMSS_<uuid>_<original_filename>
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    # Get file extension
    _, ext = os.path.splitext(original_filename)
    # Create secure filename
    base_name = secure_filename(os.path.splitext(original_filename)[0])
    # Limit base name length
    if len(base_name) > 50:
        base_name = base_name[:50]
    
    return f"{timestamp}_{unique_id}_{base_name}{ext}"


def load_video_history():
    """Load video generation history from JSON file."""
    history_file = app.config['HISTORY_FILE']
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_video_history(history):
    """Save video generation history to JSON file."""
    history_file = app.config['HISTORY_FILE']
    try:
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"Error saving history: {e}")


def load_decks():
    """Load decks from JSON file."""
    decks_file = app.config['DECKS_FILE']
    if os.path.exists(decks_file):
        try:
            with open(decks_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_decks(decks):
    """Save decks to JSON file."""
    decks_file = app.config['DECKS_FILE']
    try:
        with open(decks_file, 'w', encoding='utf-8') as f:
            json.dump(decks, f, indent=2, ensure_ascii=False)
    except IOError as e:
        print(f"Error saving decks: {e}")


def add_to_history(video_data):
    """Add a completed video to history."""
    history = load_video_history()
    
    # Add timestamp if not present
    if 'created_at' not in video_data:
        video_data['created_at'] = datetime.now().isoformat()
    
    # Add to beginning of list (most recent first)
    history.insert(0, video_data)
    
    # Keep only last 100 entries to prevent file from growing too large
    history = history[:100]
    
    save_video_history(history)


def download_video(video_url: str, local_path: str) -> bool:
    """
    Download a video from a URL to a local file.
    
    Args:
        video_url: URL of the video to download
        local_path: Local path to save the video
        
    Returns:
        True if successful, False otherwise
    """
    try:
        response = requests.get(video_url, stream=True, timeout=300)
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(local_path) if os.path.dirname(local_path) else '.', exist_ok=True)
        
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        return True
    except Exception as e:
        print(f"Error downloading video: {e}")
        return False


def upload_video_to_azure(video_url: str, base_filename: str) -> Optional[str]:
    """
    Download video from Veo API and upload to Azure Storage.
    
    Args:
        video_url: URL of the video from Veo API
        base_filename: Base filename (without extension) to use for the video
        
    Returns:
        Azure blob URL of the uploaded video, or None if failed
    """
    try:
        # Generate video filename (same base name as input image, but with .mp4 extension)
        video_filename = f"{base_filename}.mp4"
        
        # Ensure uploads directory exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Download video temporarily
        temp_video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
        
        print(f"Downloading video from {video_url} to {temp_video_path}...")
        if not download_video(video_url, temp_video_path):
            print(f"⚠ Failed to download video from Veo API: {video_url}")
            return None
        
        # Check if file was downloaded successfully
        if not os.path.exists(temp_video_path) or os.path.getsize(temp_video_path) == 0:
            print(f"⚠ Downloaded video file is empty or doesn't exist: {temp_video_path}")
            # Clean up empty file
            if os.path.exists(temp_video_path):
                os.remove(temp_video_path)
            return None
        
        file_size = os.path.getsize(temp_video_path)
        print(f"Video downloaded successfully ({file_size / 1024 / 1024:.2f} MB)")
        
        # Upload to Azure
        blob_name = f"{AZURE_BLOB_PATH_OUTPUT}{video_filename}"
        print(f"Uploading to Azure: {blob_name}")
        blob_url = upload_to_azure_blob(temp_video_path, blob_name)
        
        # Clean up local file
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
            print(f"Cleaned up temporary file: {temp_video_path}")
        
        print(f"Video successfully uploaded to Azure: {blob_url}")
        return blob_url
    
    except Exception as e:
        print(f"⚠ Error in upload_video_to_azure: {e}")
        import traceback
        traceback.print_exc()
        # Clean up any partial files
        temp_video_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_filename}.mp4")
        if os.path.exists(temp_video_path):
            try:
                os.remove(temp_video_path)
            except:
                pass
        return None


def upload_to_azure_blob(local_file_path: str, blob_name: str) -> str:
    """
    Upload a file to Azure Blob Storage.
    
    Note: This function preserves the original file quality - no compression,
    resizing, or image processing is applied. The file is uploaded as-is in
    binary format, maintaining 100% of the original image quality.
    
    Args:
        local_file_path: Path to local file
        blob_name: Name for the blob in Azure
        
    Returns:
        Public URL of the uploaded blob
    """
    try:
        blob_service_client = get_azure_blob_service_client()
        blob_client = blob_service_client.get_blob_client(
            container=AZURE_CONTAINER_NAME,
            blob=blob_name
        )
        
        # Upload the file in binary mode - preserves original quality
        # No compression, resizing, or image processing is applied
        with open(local_file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        
        # Construct the public URL
        blob_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{AZURE_CONTAINER_NAME}/{blob_name}"
        return blob_url
    
    except Exception as e:
        raise Exception(f"Failed to upload to Azure: {str(e)}")


@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')


@app.route('/history')
def history():
    """Render the video history page."""
    return render_template('history.html')


@app.route('/decks')
def decks():
    """Render the decks management page."""
    return render_template('decks.html')


@app.route('/deck/<deck_id>')
def deck_detail(deck_id):
    """Render the deck detail page."""
    return render_template('deck_detail.html', deck_id=deck_id)


@app.route('/deck/<deck_id>/results')
def deck_results(deck_id):
    """Render the deck results page."""
    return render_template('deck_results.html', deck_id=deck_id)


@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    """Handle image upload and upload to Azure Storage."""
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check if file is an image
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        if not ('.' in file.filename and 
                file.filename.rsplit('.', 1)[1].lower() in allowed_extensions):
            return jsonify({'error': 'Invalid file type. Only images are allowed.'}), 400
        
        # Save file temporarily (preserves original quality - no processing)
        unique_filename = generate_unique_filename(file.filename)
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(local_path)
        
        # Upload to Azure (original image quality is preserved)
        blob_name = f"{AZURE_BLOB_PATH_INPUT}{unique_filename}"
        blob_url = upload_to_azure_blob(local_path, blob_name)
        
        # Clean up local file
        os.remove(local_path)
        
        return jsonify({
            'success': True,
            'image_url': blob_url,
            'filename': unique_filename,
            'base_filename': unique_filename.rsplit('.', 1)[0]  # Filename without extension
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Store pending tasks with metadata (will be saved to history when completed)
pending_tasks = {}

@app.route('/api/generate-video', methods=['POST'])
def generate_video():
    """Generate video using Veo API."""
    try:
        data = request.json
        
        # Validate required fields
        if not data.get('image_url'):
            return jsonify({'error': 'Image URL is required'}), 400
        if not data.get('prompt'):
            return jsonify({'error': 'Prompt is required'}), 400
        
        # Extract parameters
        image_url = data['image_url']
        image_filename = data.get('image_filename', '')  # Get filename from frontend
        prompt = data['prompt']
        aspect_ratio = data.get('aspect_ratio', '16:9')
        model = data.get('model', 'veo3_fast')
        seeds = data.get('seeds')
        generation_type = data.get('generation_type', 'FIRST_AND_LAST_FRAMES_2_VIDEO')
        
        # Generate video (async - return task ID immediately)
        generator = get_veo_generator()
        result = generator.generate_video(
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
            return jsonify({'error': 'Failed to create video generation task'}), 500
        
        # Store task metadata for later (will be added to history when completed)
        # Extract base filename from image URL to use for output video
        image_filename = data.get('image_filename', '')
        if not image_filename:
            # Try to extract from image_url
            if '/' in image_url:
                image_filename = image_url.split('/')[-1]
        
        pending_tasks[task_id] = {
            'prompt': prompt,
            'image_url': image_url,
            'image_filename': image_filename,
            'aspect_ratio': aspect_ratio,
            'model': model,
            'generation_type': generation_type,
            'created_at': datetime.now().isoformat()
        }
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': 'Video generation started'
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/video-status/<task_id>', methods=['GET'])
def get_video_status(task_id):
    """Get video generation status."""
    try:
        generator = get_veo_generator()
        details = generator.get_video_details(task_id)
        
        success_flag = details.get('successFlag')
        response_data = details.get('response', {})
        
        if success_flag == 1:
            # Completed
            video_urls = response_data.get('resultUrls', [])
            origin_urls = response_data.get('originUrls', [])
            
            # Get stored metadata for this task
            task_metadata = pending_tasks.pop(task_id, {})
            
            # Download and upload video to Azure
            azure_video_urls = []
            if video_urls:
                try:
                    # Get base filename from input image
                    image_filename = task_metadata.get('image_filename', '')
                    deck_id = task_metadata.get('deck_id')
                    card_id = task_metadata.get('card_id')
                    
                    if image_filename:
                        # Extract base name (without extension) - keep the full unique filename
                        # Format: YYYYMMDD_HHMMSS_<uuid>_<original_name>
                        base_filename = os.path.splitext(image_filename)[0]
                        
                        # If this is part of a deck, determine which video number this is (1 or 2)
                        if deck_id and card_id:
                            decks = load_decks()
                            deck = next((d for d in decks if d['id'] == deck_id), None)
                            if deck:
                                card = next((c for c in deck['cards'] if c['id'] == card_id), None)
                                if card:
                                    # Count existing videos for this card
                                    existing_count = len(card.get('video_urls', []))
                                    video_number = existing_count + 1
                                    base_filename = f"{base_filename}_{video_number}"
                    else:
                        # Fallback: use task_id as base filename
                        base_filename = task_id
                    
                    print(f"Downloading and uploading video to Azure with filename: {base_filename}.mp4")
                    # Download and upload the first video URL to Azure
                    azure_video_url = upload_video_to_azure(video_urls[0], base_filename)
                    if azure_video_url:
                        azure_video_urls = [azure_video_url]
                        print(f"Successfully uploaded video to Azure: {azure_video_url}")
                    else:
                        # Upload failed - use original Veo URL as fallback
                        print(f"⚠ Failed to upload video to Azure, using original Veo URL as fallback")
                        azure_video_urls = video_urls
                except Exception as e:
                    print(f"⚠ Error: Failed to upload video to Azure: {e}")
                    import traceback
                    traceback.print_exc()
                    # Fallback to original URLs if Azure upload fails
                    azure_video_urls = video_urls
                    print(f"Using original Veo URL as fallback: {video_urls[0]}")
            
            # Use Azure URLs if available, otherwise fallback to original URLs
            final_video_urls = azure_video_urls if azure_video_urls else video_urls
            
            # Get deck/card info (already extracted above)
            
            if deck_id and card_id:
                # Update deck card with video URL
                decks = load_decks()
                deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
                
                if deck_index is not None:
                    deck = decks[deck_index]
                    card = next((c for c in deck['cards'] if c['id'] == card_id), None)
                    
                    if card:
                        # Ensure video_urls array exists
                        if 'video_urls' not in card:
                            card['video_urls'] = []
                        
                        # Add video URL to card
                        if final_video_urls:
                            card['video_urls'].extend(final_video_urls)
                            print(f"Added {len(final_video_urls)} video(s) to card {card_id}. Total: {len(card['video_urls'])}")
                        
                        # Check if all videos for this card are complete
                        expected_videos = len(card.get('task_ids', []))
                        actual_videos = len(card['video_urls'])
                        
                        if actual_videos >= expected_videos:
                            card['status'] = 'completed'
                            print(f"Card {card_id} completed: {actual_videos}/{expected_videos} videos")
                        
                        # Check if all cards in deck are completed
                        all_completed = all(c.get('status') == 'completed' for c in deck['cards'])
                        if all_completed:
                            deck['status'] = 'completed'
                            print(f"Deck {deck_id} completed: all cards finished")
                        
                        deck['updated_at'] = datetime.now().isoformat()
                        save_decks(decks)
                        print(f"Deck saved. Card {card_id} now has {len(card['video_urls'])} videos")
            
            # Save to history with all metadata (using Azure URL)
            video_data = {
                'task_id': task_id,
                'video_urls': final_video_urls,
                'origin_urls': origin_urls,
                'veo_urls': video_urls,  # Keep original Veo URLs for reference
                'resolution': response_data.get('resolution', 'N/A'),
                'prompt': task_metadata.get('prompt', ''),
                'image_url': task_metadata.get('image_url', ''),
                'aspect_ratio': task_metadata.get('aspect_ratio', ''),
                'model': task_metadata.get('model', ''),
                'generation_type': task_metadata.get('generation_type', ''),
                'deck_id': deck_id,
                'card_id': card_id,
                'created_at': task_metadata.get('created_at', datetime.now().isoformat())
            }
            add_to_history(video_data)
            
            return jsonify({
                'status': 'completed',
                'task_id': task_id,
                'video_urls': final_video_urls,
                'origin_urls': origin_urls,
                'resolution': response_data.get('resolution', 'N/A')
            })
        elif success_flag == 0:
            # Processing
            return jsonify({
                'status': 'processing',
                'task_id': task_id
            })
        else:
            # Failed
            error_code = details.get('errorCode')
            error_message = details.get('errorMessage', 'Unknown error')
            return jsonify({
                'status': 'failed',
                'task_id': task_id,
                'error': f"{error_code}: {error_message}"
            }), 400
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/video-history', methods=['GET'])
def get_video_history():
    """Get all video generation history."""
    try:
        history = load_video_history()
        return jsonify({
            'success': True,
            'history': history,
            'count': len(history)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks', methods=['GET'])
def get_decks():
    """Get all decks."""
    try:
        decks = load_decks()
        return jsonify({
            'success': True,
            'decks': decks,
            'count': len(decks)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks', methods=['POST'])
def create_deck():
    """Create a new deck."""
    try:
        data = request.json
        deck_name = data.get('name', '').strip()
        aspect_ratio = data.get('aspect_ratio', '16:9')
        
        if not deck_name:
            return jsonify({'error': 'Deck name is required'}), 400
        
        decks = load_decks()
        
        # Create new deck
        new_deck = {
            'id': str(uuid.uuid4()),
            'name': deck_name,
            'aspect_ratio': aspect_ratio,
            'cards': [],
            'status': 'draft',  # draft, generating, completed
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        decks.append(new_deck)
        save_decks(decks)
        
        return jsonify({
            'success': True,
            'deck': new_deck
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>', methods=['GET'])
def get_deck(deck_id):
    """Get a specific deck."""
    try:
        decks = load_decks()
        deck = next((d for d in decks if d['id'] == deck_id), None)
        
        if not deck:
            return jsonify({'error': 'Deck not found'}), 404
        
        return jsonify({
            'success': True,
            'deck': deck
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>', methods=['PUT'])
def update_deck(deck_id):
    """Update a deck."""
    try:
        data = request.json
        decks = load_decks()
        
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        if deck_index is None:
            return jsonify({'error': 'Deck not found'}), 404
        
        # Update deck fields
        if 'name' in data:
            decks[deck_index]['name'] = data['name']
        if 'aspect_ratio' in data:
            decks[deck_index]['aspect_ratio'] = data['aspect_ratio']
        if 'status' in data:
            decks[deck_index]['status'] = data['status']
        
        decks[deck_index]['updated_at'] = datetime.now().isoformat()
        save_decks(decks)
        
        return jsonify({
            'success': True,
            'deck': decks[deck_index]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>', methods=['DELETE'])
def delete_deck(deck_id):
    """Delete a deck."""
    try:
        decks = load_decks()
        
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        if deck_index is None:
            return jsonify({'error': 'Deck not found'}), 404
        
        # Remove deck from list
        deleted_deck = decks.pop(deck_index)
        save_decks(decks)
        
        return jsonify({
            'success': True,
            'message': f'Deck "{deleted_deck["name"]}" deleted successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/cards', methods=['POST'])
def add_card_to_deck(deck_id):
    """Add a scene to a video."""
    try:
        data = request.json
        image_url = data.get('image_url', '').strip()
        prompt = data.get('prompt', '').strip()
        
        if not image_url:
            return jsonify({'error': 'Image URL is required'}), 400
        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400
        
        # Load decks and find the deck
        decks = load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        
        if deck_index is None:
            return jsonify({'error': 'Video not found'}), 404
        
        # Check scene limit
        max_cards = app.config.get('MAX_CARDS_PER_DECK')
        if max_cards is not None:
            current_card_count = len(decks[deck_index].get('cards', []))
            if current_card_count >= max_cards:
                return jsonify({
                    'error': f'Maximum {max_cards} scenes allowed per video. Current: {current_card_count}'
                }), 400
        
        # Create new scene
        new_card = {
            'id': str(uuid.uuid4()),
            'image_url': image_url,
            'image_filename': data.get('image_filename', ''),
            'prompt': prompt,
            'status': 'pending',  # pending, generating, completed
            'task_ids': [],
            'video_urls': [],
            'created_at': datetime.now().isoformat()
        }
        
        decks[deck_index]['cards'].append(new_card)
        decks[deck_index]['updated_at'] = datetime.now().isoformat()
        save_decks(decks)
        
        return jsonify({
            'success': True,
            'card': new_card,
            'deck': decks[deck_index]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/cards/<card_id>', methods=['PUT'])
def update_card(deck_id, card_id):
    """Update a scene in a video."""
    try:
        data = request.json
        image_url = data.get('image_url', '').strip()
        prompt = data.get('prompt', '').strip()
        
        if not image_url:
            return jsonify({'error': 'Image URL is required'}), 400
        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400
        
        decks = load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        
        if deck_index is None:
            return jsonify({'error': 'Video not found'}), 404
        
        deck = decks[deck_index]
        card_index = next((i for i, c in enumerate(deck['cards']) if c['id'] == card_id), None)
        
        if card_index is None:
            return jsonify({'error': 'Scene not found'}), 404
        
        # Update card
        card = deck['cards'][card_index]
        card['image_url'] = image_url
        card['image_filename'] = data.get('image_filename', '')
        card['prompt'] = prompt
        card['updated_at'] = datetime.now().isoformat()
        
        deck['updated_at'] = datetime.now().isoformat()
        save_decks(decks)
        
        return jsonify({
            'success': True,
            'card': card,
            'deck': deck
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/cards/<card_id>', methods=['DELETE'])
def delete_card(deck_id, card_id):
    """Delete a scene from a video."""
    try:
        decks = load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        
        if deck_index is None:
            return jsonify({'error': 'Video not found'}), 404
        
        # Remove card
        deck = decks[deck_index]
        deck['cards'] = [c for c in deck['cards'] if c['id'] != card_id]
        deck['updated_at'] = datetime.now().isoformat()
        save_decks(decks)
        
        return jsonify({
            'success': True,
            'deck': deck
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/generate', methods=['POST'])
def generate_deck_videos(deck_id):
    """Generate videos for all cards in a deck (2 videos per card)."""
    try:
        decks = load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        
        if deck_index is None:
            return jsonify({'error': 'Deck not found'}), 404
        
        deck = decks[deck_index]
        
        if not deck['cards']:
            return jsonify({'error': 'No scenes in video'}), 400
        
        # Allow regeneration if:
        # 1. Status is 'generating' but no videos exist (failed/interrupted generation), OR
        # 2. Status is 'draft' or 'completed'
        total_videos = sum(len(card.get('video_urls', [])) for card in deck['cards'])
        if deck['status'] == 'generating' and total_videos > 0:
            return jsonify({'error': 'Deck is already generating. Please wait for completion.'}), 400
        
        # Update deck status
        deck['status'] = 'generating'
        deck['updated_at'] = datetime.now().isoformat()
        
        # Reset card statuses and clear previous videos
        for card in deck['cards']:
            card['status'] = 'generating'
            card['video_urls'] = []
            card['task_ids'] = []
        
        save_decks(decks)
        
        # Generate 2 videos for each card
        # Rate limit: 20 requests per 10 seconds (KIE API limit)
        # We'll send requests in batches with delays to respect the limit
        generator = get_veo_generator()
        all_task_ids = []
        
        total_requests = len(deck['cards']) * 2
        requests_sent = 0
        batch_size = 18  # Max requests per 10-second window (slightly below 20 limit for safety)
        delay_between_batches = 10.5  # Slightly more than 10 seconds to be safe
        
        print(f"Generating {total_requests} videos with rate limiting (max {batch_size} requests per {delay_between_batches}s)...")
        
        for card in deck['cards']:
            for i in range(2):  # Generate 2 videos per card
                # Rate limiting: wait if we've sent a full batch
                if requests_sent > 0 and requests_sent % batch_size == 0:
                    print(f"Rate limit: Waiting {delay_between_batches}s before sending next batch... ({requests_sent}/{total_requests} requests sent)")
                    time.sleep(delay_between_batches)
                
                try:
                    result = generator.generate_video(
                        prompt=card['prompt'],
                        image_urls=[card['image_url']],
                        model='veo3_fast',
                        aspect_ratio=deck['aspect_ratio'],
                        enable_translation=True,
                        generation_type='FIRST_AND_LAST_FRAMES_2_VIDEO'
                    )
                    
                    task_id = result.get('taskId')
                    if task_id:
                        card['task_ids'].append(task_id)
                        all_task_ids.append({
                            'task_id': task_id,
                            'card_id': card['id'],
                            'deck_id': deck_id,
                            'image_filename': card.get('image_filename', ''),
                            'prompt': card['prompt'],
                            'aspect_ratio': deck['aspect_ratio']
                        })
                        requests_sent += 1
                        print(f"✓ Request {requests_sent}/{total_requests} sent (Task ID: {task_id})")
                    else:
                        print(f"✗ Failed to get task ID for card {card['id']}, video {i+1}")
                except Exception as e:
                    print(f"Error generating video for card {card['id']}, video {i+1}: {e}")
                    # Check if it's a rate limit error (429)
                    error_str = str(e).lower()
                    if '429' in error_str or 'rate limit' in error_str or 'too many requests' in error_str:
                        print("⚠ Rate limit hit! Waiting 10 seconds before retrying...")
                        time.sleep(10)
                        # Retry once
                        try:
                            result = generator.generate_video(
                                prompt=card['prompt'],
                                image_urls=[card['image_url']],
                                model='veo3_fast',
                                aspect_ratio=deck['aspect_ratio'],
                                enable_translation=True,
                                generation_type='FIRST_AND_LAST_FRAMES_2_VIDEO'
                            )
                            task_id = result.get('taskId')
                            if task_id:
                                card['task_ids'].append(task_id)
                                all_task_ids.append({
                                    'task_id': task_id,
                                    'card_id': card['id'],
                                    'deck_id': deck_id,
                                    'image_filename': card.get('image_filename', ''),
                                    'prompt': card['prompt'],
                                    'aspect_ratio': deck['aspect_ratio']
                                })
                                requests_sent += 1
                                print(f"✓ Retry successful: Request {requests_sent}/{total_requests} sent (Task ID: {task_id})")
                        except Exception as retry_error:
                            print(f"✗ Retry failed: {retry_error}")
        
        # Store task metadata for tracking
        for task_info in all_task_ids:
            pending_tasks[task_info['task_id']] = {
                'deck_id': task_info['deck_id'],
                'card_id': task_info['card_id'],
                'prompt': task_info['prompt'],
                'image_url': deck['cards'][next((i for i, c in enumerate(deck['cards']) if c['id'] == task_info['card_id']), 0)]['image_url'],
                'image_filename': task_info['image_filename'],
                'aspect_ratio': task_info['aspect_ratio'],
                'model': 'veo3_fast',
                'generation_type': 'FIRST_AND_LAST_FRAMES_2_VIDEO',
                'created_at': datetime.now().isoformat()
            }
        
        save_decks(decks)
        
        return jsonify({
            'success': True,
            'message': f'Started generation for {len(deck["cards"])} scenes (2 videos each)',
            'task_count': len(all_task_ids),
            'deck': deck
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/check-status', methods=['POST'])
def check_deck_status(deck_id):
    """Check and update status of all pending videos in a deck."""
    try:
        decks = load_decks()
        deck_index = next((i for i, d in enumerate(decks) if d['id'] == deck_id), None)
        
        if deck_index is None:
            return jsonify({'error': 'Deck not found'}), 404
        
        deck = decks[deck_index]
        generator = get_veo_generator()
        updated_count = 0
        
        # Check status of all task IDs in all cards
        for card in deck.get('cards', []):
            task_ids = card.get('task_ids', [])
            existing_video_count = len(card.get('video_urls', []))
            expected_video_count = len(task_ids)
            
            # Only check if we don't have all videos yet
            if existing_video_count < expected_video_count:
                for task_id in task_ids:
                    # Check if this task's video is already in the card's video_urls
                    # We can't easily match by task_id, so we'll check all tasks
                    try:
                        details = generator.get_video_details(task_id)
                        success_flag = details.get('successFlag')
                        
                        if success_flag == 1:
                            # Video completed - check if we already have it
                            response_data = details.get('response', {})
                            video_urls = response_data.get('resultUrls', [])
                            
                            if video_urls:
                                # Check if this video URL is already in the card
                                veo_url = video_urls[0]
                                # Try to match by checking if we have the same number of videos as completed tasks
                                # Or check if the URL pattern matches
                                
                                # Get task metadata (from pending_tasks or reconstruct from card)
                                task_metadata = pending_tasks.get(task_id, {})
                                if not task_metadata:
                                    # Reconstruct metadata from card
                                    task_metadata = {
                                        'image_filename': card.get('image_filename', ''),
                                        'deck_id': deck_id,
                                        'card_id': card['id'],
                                        'prompt': card.get('prompt', ''),
                                        'image_url': card.get('image_url', ''),
                                        'aspect_ratio': deck.get('aspect_ratio', ''),
                                        'model': 'veo3_fast',
                                        'generation_type': 'FIRST_AND_LAST_FRAMES_2_VIDEO'
                                    }
                                
                                # Check if we need to process this video
                                # We'll process it if we don't have enough videos yet
                                current_video_count = len(card.get('video_urls', []))
                                if current_video_count < expected_video_count:
                                    # Download and upload to Azure
                                    image_filename = task_metadata.get('image_filename', '')
                                    if image_filename:
                                        base_filename = os.path.splitext(image_filename)[0]
                                        video_number = current_video_count + 1
                                        base_filename = f"{base_filename}_{video_number}"
                                    else:
                                        base_filename = task_id
                                    
                                    print(f"Processing task {task_id[:8]}... for card {card['id'][:8]}...: video {video_number}/{expected_video_count}")
                                    
                                    # Try to upload to Azure (returns None on failure)
                                    azure_video_url = upload_video_to_azure(veo_url, base_filename)
                                    
                                    if azure_video_url:
                                        # Successfully uploaded to Azure
                                        if 'video_urls' not in card:
                                            card['video_urls'] = []
                                        
                                        # Check if URL already exists
                                        if azure_video_url not in card['video_urls']:
                                            card['video_urls'].append(azure_video_url)
                                            updated_count += 1
                                            print(f"✓ Added video to card {card['id'][:8]}... Total: {len(card['video_urls'])}/{expected_video_count}")
                                        else:
                                            print(f"Video already exists in card, skipping duplicate")
                                    else:
                                        # Failed to upload - log but continue
                                        error_msg = "Failed to download or upload video to Azure"
                                        print(f"✗ Failed to process video for task {task_id[:8]}... ({error_msg})")
                                        # Track failed task with error message
                                        if 'failed_tasks' not in card:
                                            card['failed_tasks'] = []
                                        if 'failed_tasks_details' not in card:
                                            card['failed_tasks_details'] = []
                                        
                                        # Check if we already have this task_id tracked
                                        task_exists = any(ft.get('task_id') == task_id for ft in card.get('failed_tasks_details', []))
                                        if not task_exists:
                                            card['failed_tasks'].append(task_id)
                                            card['failed_tasks_details'].append({
                                                'task_id': task_id,
                                                'error': error_msg,
                                                'video_number': video_number
                                            })
                                    
                                    # Remove from pending if it was there
                                    pending_tasks.pop(task_id, None)
                        elif success_flag == 0:
                            # Still processing - skip for now
                            pass
                        else:
                            # Failed on API side - extract actual error message
                            error_code = details.get('errorCode', '')
                            error_message = details.get('errorMessage', '')
                            
                            # Build error message with actual details
                            if error_message:
                                error_msg = error_message
                                if error_code:
                                    error_msg = f"{error_message} (Error Code: {error_code})"
                            elif error_code:
                                error_msg = f"Video generation failed (Error Code: {error_code})"
                            else:
                                error_msg = f"Video generation failed on KIE API (status flag: {success_flag})"
                            
                            print(f"✗ Task {task_id[:8]}... failed on KIE API side: {error_msg}")
                            
                            # Determine video number
                            current_video_count = len(card.get('video_urls', []))
                            video_number = current_video_count + 1
                            
                            # Track failed task with error message
                            if 'failed_tasks' not in card:
                                card['failed_tasks'] = []
                            if 'failed_tasks_details' not in card:
                                card['failed_tasks_details'] = []
                            
                            # Check if we already have this task_id tracked
                            task_exists = any(ft.get('task_id') == task_id for ft in card.get('failed_tasks_details', []))
                            if not task_exists:
                                card['failed_tasks'].append(task_id)
                                card['failed_tasks_details'].append({
                                    'task_id': task_id,
                                    'error': error_msg,
                                    'video_number': video_number
                                })
                            
                            # Remove from pending
                            pending_tasks.pop(task_id, None)
                    except Exception as e:
                        # Task might not exist or API error - continue checking others
                        error_msg = str(e)
                        if "record is null" not in error_msg.lower() and "not found" not in error_msg.lower():
                            print(f"Error checking task {task_id}: {e}")
        
        # Update card and deck statuses
        for card in deck['cards']:
            expected_videos = len(card.get('task_ids', []))
            actual_videos = len(card.get('video_urls', []))
            failed_count = len(card.get('failed_tasks', []))
            
            if expected_videos > 0:
                if actual_videos >= expected_videos:
                    # All videos succeeded
                    card['status'] = 'completed'
                elif actual_videos > 0:
                    # Some videos succeeded, some may have failed
                    if actual_videos + failed_count >= expected_videos:
                        # All tasks processed (some succeeded, some failed)
                        card['status'] = 'partially_completed'
                    else:
                        # Still processing
                        card['status'] = 'generating'
                elif failed_count > 0 and actual_videos == 0:
                    # All videos failed
                    card['status'] = 'failed'
                else:
                    # Still generating
                    card['status'] = 'generating'
        
        # Update deck status
        cards_with_tasks = [c for c in deck['cards'] if len(c.get('task_ids', [])) > 0]
        if cards_with_tasks:
            all_completed = all(c.get('status') in ['completed', 'partially_completed', 'failed'] for c in cards_with_tasks)
            if all_completed:
                # Check if any cards have videos
                has_any_videos = any(len(c.get('video_urls', [])) > 0 for c in cards_with_tasks)
                if has_any_videos:
                    deck['status'] = 'completed'
                else:
                    # All failed
                    deck['status'] = 'failed'
            else:
                deck['status'] = 'generating'
        
        deck['updated_at'] = datetime.now().isoformat()
        save_decks(decks)
        
        return jsonify({
            'success': True,
            'updated_videos': updated_count,
            'deck': deck
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/<deck_id>/videos', methods=['GET'])
def get_deck_videos(deck_id):
    """Get all videos for a specific deck."""
    try:
        decks = load_decks()
        deck = next((d for d in decks if d['id'] == deck_id), None)
        
        if not deck:
            return jsonify({'error': 'Deck not found'}), 404
        
        # Collect all videos and failed tasks from all cards in the deck
        all_videos = []
        all_failed = []
        
        for card_index, card in enumerate(deck['cards']):
            # Add successful videos
            for video_url in card.get('video_urls', []):
                all_videos.append({
                    'card_id': card['id'],
                    'card_index': card_index,
                    'card_prompt': card['prompt'],
                    'card_image_url': card['image_url'],
                    'video_url': video_url,
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
        return jsonify({'error': str(e)}), 500


@app.route('/api/decks/update-failed-tasks', methods=['POST'])
def update_all_failed_tasks():
    """Retroactively check and update failed tasks for all existing decks."""
    try:
        decks = load_decks()
        generator = get_veo_generator()
        total_updated = 0
        
        print("Starting retroactive failed task update for all decks...")
        
        for deck in decks:
            deck_updated = False
            for card in deck.get('cards', []):
                task_ids = card.get('task_ids', [])
                video_urls = card.get('video_urls', [])
                expected_count = len(task_ids)
                actual_count = len(video_urls) if video_urls else 0
                
                # If we have task_ids but fewer videos than expected, check for failures
                if expected_count > 0 and actual_count < expected_count:
                    # Initialize failed tracking if not exists
                    if 'failed_tasks' not in card:
                        card['failed_tasks'] = []
                    if 'failed_tasks_details' not in card:
                        card['failed_tasks_details'] = []
                    
                    # Check each task_id that doesn't have a corresponding video
                    for task_id in task_ids:
                        # Skip if already tracked as failed
                        already_tracked = any(ft.get('task_id') == task_id for ft in card.get('failed_tasks_details', []))
                        if already_tracked:
                            continue
                        
                        # Check if this task has a corresponding video (we can't perfectly match, so check status)
                        try:
                            details = generator.get_video_details(task_id)
                            success_flag = details.get('successFlag')
                            
                            if success_flag == 1:
                                # Task succeeded - check if we have the video
                                response_data = details.get('response', {})
                                video_urls_from_api = response_data.get('resultUrls', [])
                                if video_urls_from_api:
                                    # Task succeeded but we might not have processed it yet
                                    # This is okay, it will be picked up by normal status checking
                                    continue
                            elif success_flag == 0:
                                # Still processing - skip for now
                                continue
                            else:
                                # Failed on API side - extract actual error message
                                error_code = details.get('errorCode', '')
                                error_message = details.get('errorMessage', '')
                                
                                # Build error message with actual details
                                if error_message:
                                    error_msg = error_message
                                    if error_code:
                                        error_msg = f"{error_message} (Error Code: {error_code})"
                                elif error_code:
                                    error_msg = f"Video generation failed (Error Code: {error_code})"
                                else:
                                    error_msg = f"Video generation failed on KIE API (status flag: {success_flag})"
                                
                                video_number = actual_count + len(card.get('failed_tasks_details', [])) + 1
                                
                                card['failed_tasks'].append(task_id)
                                card['failed_tasks_details'].append({
                                    'task_id': task_id,
                                    'error': error_msg,
                                    'video_number': video_number
                                })
                                deck_updated = True
                                total_updated += 1
                                print(f"✓ Tracked failed task {task_id[:8]}... for card {card['id'][:8]}... in deck {deck['name']}: {error_msg}")
                        except Exception as e:
                            error_msg = str(e)
                            # If task doesn't exist or has an error, it might have failed
                            if "record is null" not in error_msg.lower() and "not found" not in error_msg.lower():
                                # Check if we've waited long enough (tasks older than 1 hour might be considered failed)
                                # For now, we'll only track explicit failures
                                print(f"⚠ Could not check task {task_id[:8]}...: {e}")
                                continue
            
            if deck_updated:
                deck['updated_at'] = datetime.now().isoformat()
                # Update deck status based on card statuses
                cards_with_tasks = [c for c in deck['cards'] if len(c.get('task_ids', [])) > 0]
                if cards_with_tasks:
                    all_completed = all(c.get('status') in ['completed', 'partially_completed', 'failed'] for c in cards_with_tasks)
                    if all_completed:
                        has_any_videos = any(len(c.get('video_urls', [])) > 0 for c in cards_with_tasks)
                        if has_any_videos:
                            deck['status'] = 'completed'
                        else:
                            deck['status'] = 'failed'
        
        save_decks(decks)
        
        return jsonify({
            'success': True,
            'message': f'Updated {total_updated} failed tasks across {len(decks)} decks',
            'total_updated': total_updated,
            'decks_checked': len(decks)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Use PORT environment variable if available (for deployment platforms)
    port = int(os.environ.get('PORT', 5000))
    # Set debug=False in production
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)

