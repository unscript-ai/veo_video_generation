"""
Veo 3.1 Video Generation Client
Handles video generation requests and polling for completion status.
"""

import requests
import time
import json
from typing import Optional, Dict, List


class VeoVideoGenerator:
    """Client for Veo 3.1 API video generation."""
    
    BASE_URL = "https://api.kie.ai/api/v1/veo"
    GENERATE_ENDPOINT = f"{BASE_URL}/generate"
    RECORD_INFO_ENDPOINT = f"{BASE_URL}/record-info"
    
    def __init__(self, api_key: str):
        """
        Initialize the Veo Video Generator client.
        
        Args:
            api_key: Your Veo API key (Bearer token)
        """
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    @staticmethod
    def normalize_prompt(prompt: str) -> str:
        """
        Normalize prompt string to handle both literal newlines and \\n escape sequences.
        
        Args:
            prompt: Prompt string that may contain literal newlines or \\n sequences
            
        Returns:
            Normalized prompt string with proper newlines
        """
        # Replace literal \n sequences with actual newlines if they exist
        # This handles cases where prompts are pasted with \n as text
        if "\\n" in prompt:
            prompt = prompt.replace("\\n", "\n")
        return prompt.strip()
    
    def generate_video(
        self,
        prompt: str,
        image_urls: Optional[List[str]] = None,
        model: str = "veo3_fast",
        aspect_ratio: str = "16:9",
        seeds: Optional[int] = None,
        enable_translation: bool = True,
        generation_type: str = "TEXT_2_VIDEO",
        watermark: Optional[str] = None,
        callback_url: Optional[str] = None
    ) -> Dict:
        """
        Generate a video using the Veo 3.1 API.
        
        Args:
            prompt: Text prompt describing the desired video content (supports multi-line)
            image_urls: List of image URLs (1-3 images depending on generation_type)
            model: Model type - "veo3" or "veo3_fast" (default: "veo3_fast")
            aspect_ratio: Video aspect ratio - "16:9", "9:16", or "Auto" (default: "16:9")
            seeds: Random seed (10000-99999) for reproducible results
            enable_translation: Enable prompt translation to English (default: True)
            generation_type: Generation mode - "TEXT_2_VIDEO", "FIRST_AND_LAST_FRAMES_2_VIDEO", 
                           or "REFERENCE_2_VIDEO" (default: "TEXT_2_VIDEO")
            watermark: Optional watermark text
            callback_url: Optional callback URL for completion notifications
            
        Returns:
            Dict containing the response with taskId
            
        Raises:
            requests.exceptions.RequestException: If the API request fails
        """
        # Normalize prompt to handle newlines properly
        normalized_prompt = self.normalize_prompt(prompt)
        
        payload = {
            "prompt": normalized_prompt,
            "model": model,
            "aspectRatio": aspect_ratio,
            "enableTranslation": enable_translation,
            "generationType": generation_type
        }
        
        if image_urls:
            payload["imageUrls"] = image_urls
        
        if seeds is not None:
            if not (10000 <= seeds <= 99999):
                raise ValueError("Seeds must be between 10000 and 99999")
            payload["seeds"] = seeds
        
        if watermark:
            payload["watermark"] = watermark
        
        if callback_url:
            payload["callBackUrl"] = callback_url
        
        response = requests.post(
            self.GENERATE_ENDPOINT,
            headers=self.headers,
            json=payload
        )
        
        response.raise_for_status()
        result = response.json()
        
        if result.get("code") != 200:
            raise Exception(f"API Error {result.get('code')}: {result.get('msg', 'Unknown error')}")
        
        return result.get("data", {})
    
    def get_video_details(self, task_id: str) -> Dict:
        """
        Get video generation task details and status.
        
        Args:
            task_id: The task ID returned from generate_video()
            
        Returns:
            Dict containing task details including status and video URLs
            
        Raises:
            requests.exceptions.RequestException: If the API request fails
        """
        params = {"taskId": task_id}
        
        response = requests.get(
            self.RECORD_INFO_ENDPOINT,
            headers=self.headers,
            params=params
        )
        
        response.raise_for_status()
        result = response.json()
        
        if result.get("code") != 200:
            raise Exception(f"API Error {result.get('code')}: {result.get('msg', 'Unknown error')}")
        
        return result.get("data", {})
    
    def wait_for_completion(
        self,
        task_id: str,
        poll_interval: int = 10,
        max_wait_time: int = 600,
        verbose: bool = True
    ) -> Dict:
        """
        Poll the API until video generation is complete.
        
        Args:
            task_id: The task ID to poll
            poll_interval: Seconds between polling attempts (default: 10)
            max_wait_time: Maximum time to wait in seconds (default: 600 = 10 minutes)
            verbose: Print status updates (default: True)
            
        Returns:
            Dict containing completed task details with video URLs
            
        Raises:
            TimeoutError: If max_wait_time is exceeded
            Exception: If generation fails
        """
        start_time = time.time()
        
        if verbose:
            print(f"Polling task {task_id} for completion...")
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > max_wait_time:
                raise TimeoutError(f"Video generation timed out after {max_wait_time} seconds")
            
            try:
                details = self.get_video_details(task_id)
                
                success_flag = details.get("successFlag")
                
                if success_flag == 1:
                    if verbose:
                        print(f"✓ Video generation completed in {elapsed:.1f} seconds")
                    return details
                elif success_flag == 0:
                    # Still processing
                    if verbose:
                        print(f"⏳ Still processing... (elapsed: {elapsed:.1f}s)")
                else:
                    # Failed
                    error_code = details.get("errorCode")
                    error_message = details.get("errorMessage", "Unknown error")
                    raise Exception(f"Video generation failed: {error_code} - {error_message}")
                
            except Exception as e:
                if "record is null" in str(e) or "not success" in str(e).lower():
                    # Task might still be processing
                    if verbose:
                        print(f"⏳ Task not ready yet... (elapsed: {elapsed:.1f}s)")
                else:
                    raise
            
            time.sleep(poll_interval)
    
    def generate_and_wait(
        self,
        prompt: str,
        image_urls: Optional[List[str]] = None,
        model: str = "veo3_fast",
        aspect_ratio: str = "16:9",
        seeds: Optional[int] = None,
        enable_translation: bool = True,
        generation_type: str = "TEXT_2_VIDEO",
        watermark: Optional[str] = None,
        poll_interval: int = 10,
        max_wait_time: int = 600,
        verbose: bool = True
    ) -> Dict:
        """
        Generate a video and wait for completion in one call.
        
        Args:
            prompt: Text prompt describing the desired video content
            image_urls: List of image URLs (1-3 images depending on generation_type)
            model: Model type - "veo3" or "veo3_fast" (default: "veo3_fast")
            aspect_ratio: Video aspect ratio - "16:9", "9:16", or "Auto" (default: "16:9")
            seeds: Random seed (10000-99999) for reproducible results
            enable_translation: Enable prompt translation to English (default: True)
            generation_type: Generation mode (default: "TEXT_2_VIDEO")
            watermark: Optional watermark text
            poll_interval: Seconds between polling attempts (default: 10)
            max_wait_time: Maximum time to wait in seconds (default: 600)
            verbose: Print status updates (default: True)
            
        Returns:
            Dict containing completed task details with video URLs
        """
        if verbose:
            print("🚀 Starting video generation...")
        
        # Generate video
        result = self.generate_video(
            prompt=prompt,
            image_urls=image_urls,
            model=model,
            aspect_ratio=aspect_ratio,
            seeds=seeds,
            enable_translation=enable_translation,
            generation_type=generation_type,
            watermark=watermark
        )
        
        task_id = result.get("taskId")
        if not task_id:
            raise Exception("No taskId returned from API")
        
        if verbose:
            print(f"✓ Task created: {task_id}")
        
        # Wait for completion
        return self.wait_for_completion(
            task_id=task_id,
            poll_interval=poll_interval,
            max_wait_time=max_wait_time,
            verbose=verbose
        )


def main():
    """Example usage of the Veo Video Generator."""
    # Initialize client with your API key
    API_KEY = "d9b6abd85b76487369acdf2cbab1fd8e"
    generator = VeoVideoGenerator(API_KEY)
    
    # Example: Multi-line prompt (use triple quotes for multi-line strings)
    # You can paste your prompt directly between the triple quotes
    prompt = """SCENE_DESCRIPTION:

Neha drops onto a sofa inside a busy mall lounge, visibly exhausted. Her arms rest limply by her sides amid a pile of shopping bags from Zara, H&M, and Sephora. She leans slightly forward, looking dazed. Riya stands nearby, relaxed, arms loosely crossed, looking down at Neha with a half-smile.

Motion begins as Neha exhales deeply and slumps into the seat, then raises her head to speak in a tired tone. Riya shifts her weight casually, smirking slightly, and gives a casual reply with a short head tilt. The mall remains softly blurred in the background, filled with warm retail lighting.

Camera is locked in a slightly wide portrait shot, showing both characters fully with shopping bags in foreground. No camera motion.

REFERENCE_IMAGE:

reference_image_2.jpeg (first frame of Scene 2)

CHARACTER_DNA:

Neha

Appearance: South Asian, 26, slim build, shoulder-length dark hair, same pink outfit as Scene 1

Voice: Mid-pitched, slightly tired, showing money-related stress

Camera Settings: Frontal mid-wide, portrait 9:16, seated with downward-leaning posture

Riya

Appearance: South Asian, 27, medium build, short dark hair, same teal-blue kurta and dupatta as Scene 1

Voice: Practical, warm, upbeat

Camera Settings: Standing, right side of Neha, arms at ease, confident posture

AUDIO_IDENTITY:

Neha

Voice Type: Female, South Asian accent, age 26, natural tone

Pitch: Medium-high

Tone: Tired, stressed, subdued

Delivery Style: Slower than Scene 1, voice drops slightly at the end

Emotional Markers: Audible sigh before speaking, "stress" pronounced heavier

Speech Rhythm: Sluggish start, quickens on "saare kharchon"

Lip Sync Reference Line: "Woh to hai… par ek saath itne saare kharchon ka soch ke hi stress ho raha hai."

Riya

Voice Type: Female, South Asian accent, age 27, confident and grounded

Pitch: Medium

Tone: Casual, slightly playful

Delivery Style: Friendly, mildly teasing

Emotional Markers: Quick beat before "try kar na", suggesting spontaneity

Speech Rhythm: Light and conversational

Lip Sync Reference Line: "Toh Insta EMI Card try kar na."

DIALOGUE:

Neha (fatigued, slightly slouched): "Woh to hai… par ek saath itne saare kharchon ka soch ke hi stress ho raha hai."
Riya (casual, smiling): "Toh Insta EMI Card try kar na."

Lip-Sync Specifications:

Phoneme-accurate mouth animation ("map each syllable to jaw and lip contours, sync within ±50 ms")

Expression Timing: "brief micro-expressions on key words, maintain neutral rest between sentences"

AUDIO_CUES:

Sound Effects: faint mall ambiance, bag rustle as Neha sits

Background Music: None

Ambient Noise: distant foot traffic, indistinct murmurs from shops

TECHNICAL_SPECIFICATIONS:

Resolution: 1080p

Frame Rate: 24fps

Aspect Ratio: 9:16 portrait

Duration: 6 seconds

Lighting: Mall interior lighting, warm and diffused

Color Grading: Soft warm retail tones with slight contrast lift on midtones

NEGATIVE_PROMPT_ELEMENTS:

blurry, distortion, low quality, watermark, mis-synced lips, jerky animation, floating shopping bags, flickering lights, cartoonish skin, incorrect bag labels, shadow inconsistency"""
    
    image_urls = [
        "https://unaiorgdata.blob.core.windows.net/unai-public/prajwal/veo_3_testing/_positive_prompt_202601091312.jpeg"
    ]
    
    try:
        result = generator.generate_and_wait(
            prompt=prompt,
            image_urls=image_urls,
            model="veo3_fast",
            aspect_ratio="9:16",
            seeds=12345,
            enable_translation=True,
            generation_type="FIRST_AND_LAST_FRAMES_2_VIDEO",
            verbose=True
        )
        
        # Extract video URLs
        response_data = result.get("response", {})
        video_urls = response_data.get("resultUrls", [])
        origin_urls = response_data.get("originUrls", [])
        
        print("\n" + "="*50)
        print("VIDEO GENERATION SUCCESSFUL!")
        print("="*50)
        print(f"Task ID: {result.get('taskId')}")
        print(f"Resolution: {response_data.get('resolution', 'N/A')}")
        print(f"\nVideo URLs:")
        for i, url in enumerate(video_urls, 1):
            print(f"  {i}. {url}")
        if origin_urls:
            print(f"\nOriginal URLs:")
            for i, url in enumerate(origin_urls, 1):
                print(f"  {i}. {url}")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()

