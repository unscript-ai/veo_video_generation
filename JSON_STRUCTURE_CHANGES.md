# JSON Structure Changes Summary

## Overview
Both `decks.json` and `video_history.json` are gitignored files (not in version control), so there are no direct comparisons with origin/main. 

**IMPORTANT:** The JSON file structure remains **EXACTLY THE SAME** as the original structure. The first/last frame handling is done entirely in code using virtual fields and optional metadata.

---

## decks.json Structure

### Card Object Structure (UNCHANGED)

```json
{
  "id": "uuid",
  "image_url": "https://...",           // First frame URL (stored here)
  "image_filename": "filename.jpeg",    // First frame filename
  "prompt": "video prompt text",
  "status": "pending|generating|completed",
  "task_ids": ["task_id_1", "task_id_2"],
  "video_urls": ["url1", "url2"],
  "created_at": "ISO timestamp",
  "approved_videos": ["url1"],          // Optional: Array of approved video URLs
  "metadata": {                         // Optional: Only present if last_frame_url exists
    "last_frame_url": "https://...",
    "last_frame_filename": "frame2.jpeg"
  }
}
```

### Implementation Details

- ✅ **JSON Structure Preserved:**
  - `image_url` stores the first frame URL (original structure)
  - `image_filename` stores the first frame filename (original structure)
  - `metadata` field (optional) stores last frame info only if provided
  - No new top-level fields added to card structure

- ✅ **Code-Level Handling:**
  - When reading cards: Virtual `first_frame_url`, `last_frame_url`, `first_frame_filename`, `last_frame_filename` fields are added in-memory
  - When writing cards: Only `image_url`, `image_filename`, and optional `metadata` are saved to JSON
  - Code automatically enriches cards with virtual fields using `_enrich_deck_cards()` method

- ✅ **Backward Compatibility:**
  - Existing cards without `metadata` field work perfectly
  - Old code reading JSON directly will see the same structure
  - Only code using `deck_service.get_deck()` gets enriched virtual fields

### Deck Object Structure (Unchanged)
```json
{
  "id": "uuid",
  "name": "deck name",
  "aspect_ratio": "9:16|16:9|1:1",
  "status": "draft|generating|completed",
  "cards": [/* card objects */],
  "created_at": "ISO timestamp",
  "updated_at": "ISO timestamp"
}
```

---

## video_history.json Structure

### No Changes - Structure Remains the Same

```json
[
  {
    "task_id": "task_id_string",
    "video_urls": ["url1", "url2"],
    "origin_urls": ["origin_url1"],
    "veo_urls": ["veo_url1"],
    "resolution": "1080x1920",
    "prompt": "video prompt",
    "image_url": "https://...",        // Single image URL (legacy)
    "aspect_ratio": "9:16",
    "model": "veo3_fast",
    "generation_type": "FIRST_AND_LAST_FRAMES_2_VIDEO",
    "created_at": "ISO timestamp"
  }
]
```

**Note:** The video history structure has NOT been changed. It still uses the single `image_url` field. If you want to track first/last frames in history, that would require a separate enhancement.

---

## Migration Notes

### For Existing Data
- **No migration required** - existing cards will continue to work
- Code automatically handles both old and new formats
- New cards created will have all fields (new + legacy for compatibility)

### For New Cards
- Always include `first_frame_url` and `first_frame_filename`
- Optionally include `last_frame_url` and `last_frame_filename`
- Legacy `image_url` and `image_filename` fields are automatically populated for backward compatibility

---

## Code Compatibility

### Reading Cards (Enrichment)
```python
# Cards are automatically enriched when retrieved via deck_service.get_deck()
deck = deck_service.get_deck(deck_id)
# Cards now have virtual fields: first_frame_url, last_frame_url, etc.
first_frame_url = card.get('first_frame_url')  # Virtual field (from image_url)
last_frame_url = card.get('last_frame_url')    # Virtual field (from metadata)
```

### Writing Cards (Storage)
```python
# Only original structure is saved to JSON
card = {
    'image_url': first_frame_url,          # First frame stored here
    'image_filename': first_frame_filename,
    'metadata': {                          # Only if last_frame exists
        'last_frame_url': last_frame_url,
        'last_frame_filename': last_frame_filename
    },
    # ... other fields
}
```

---

## Testing Recommendations

1. ✅ **Backward Compatibility**: Test reading existing cards with only `image_url`
2. ✅ **New Cards**: Verify new cards have all fields (new + legacy)
3. ✅ **Video Generation**: Ensure both formats work for video generation
4. ✅ **Edit/Update**: Verify card updates work with both formats

