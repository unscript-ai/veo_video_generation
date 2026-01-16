# Log Types Reference

This document explains what types of logs are generated and what they mean.

## Log Format

Each log entry follows this format:
```
TIMESTAMP - LOGGER_NAME - LEVEL - MESSAGE
```

## Log Types

### 1. **Page Navigation Logs** `[PAGE]`
Logged when users visit different pages:
- `[PAGE] Rendering index.html - Main Video Generator`
- `[PAGE] Rendering history.html - Video History`
- `[PAGE] Rendering decks.html - Deck Management`
- `[PAGE] Rendering deck_detail.html - Deck ID: abc123...`
- `[PAGE] Rendering deck_results.html - Deck ID: abc123...`

**What it shows:** Which pages users are viewing and when.

### 2. **HTTP Request Logs** `[REQUEST]`
Logged for every HTTP request to the server:
- `[REQUEST] GET / | IP: 127.0.0.1 | User-Agent: ...`
- `[REQUEST] POST /api/generate-video | IP: 127.0.0.1 | User-Agent: ...`

**What it shows:** 
- All page visits and API calls
- Client IP addresses
- Request methods (GET, POST, etc.)
- Request paths

### 3. **HTTP Response Logs** `[RESPONSE]`
Logged after each request is processed:
- `[RESPONSE] GET / | Status: 200 | Duration: 0.023s`
- `[RESPONSE] POST /api/upload-image | Status: 200 | Duration: 2.145s`

**What it shows:**
- HTTP status codes (200 = success, 404 = not found, 500 = error)
- Request duration (how long each request took)
- Performance metrics

### 4. **API Operation Logs** `[API]`
Logged for specific API operations:
- `[API] Image upload requested`
- `[API] Video generation requested`
- `[API] Creating new deck`
- `[API] Fetching all decks`
- `[API] Starting video generation for deck: abc123...`

**What it shows:** When specific API endpoints are called and what actions are taken.

### 5. **Status Logs** `[STATUS]`
Logged for status changes and updates:
- `[STATUS] Task abc123... status: processing`
- `[STATUS] Task abc123... status: completed`
- `[STATUS] Video generation completed - Task ID: abc123...`
- `[STATUS] Deck status updated - Deck: abc123... | New Videos: 2`

**What it shows:** 
- Video generation progress
- Task completion status
- Deck status changes

### 6. **Query Parameter Logs** `[QUERY]`
Logged when requests include query parameters:
- `[QUERY] {'page': '1', 'limit': '10'}`

**What it shows:** URL query parameters passed with requests.

### 7. **POST Data Logs** `[POST DATA]`
Logged for POST requests with JSON data:
- `[POST DATA] {'name': 'My Deck', 'aspect_ratio': '16:9'}`

**Note:** Prompts are truncated to 100 characters to keep logs readable.

### 8. **Error Logs** `[ERROR]`
Logged when errors occur:
- `[ERROR] GET /api/decks/123 | Error: Deck not found`

**What it shows:** 
- Errors that occur during request processing
- Full stack traces for debugging

## Example Log Flow

Here's what a typical user interaction looks like in the logs:

```
[REQUEST] GET /decks | IP: 127.0.0.1 | User-Agent: Mozilla/5.0...
[PAGE] Rendering decks.html - Deck Management
[RESPONSE] GET /decks | Status: 200 | Duration: 0.045s

[REQUEST] GET /api/decks | IP: 127.0.0.1 | User-Agent: Mozilla/5.0...
[API] Fetching all decks
[API] Retrieved 3 deck(s)
[RESPONSE] GET /api/decks | Status: 200 | Duration: 0.012s

[REQUEST] POST /api/decks | IP: 127.0.0.1 | User-Agent: Mozilla/5.0...
[API] Creating new deck
[API] Deck created - ID: abc12345..., Name: My Video, Aspect: 16:9
[RESPONSE] POST /api/decks | Status: 200 | Duration: 0.089s
```

## Filtering Logs

### Find all page visits:
```bash
grep "\[PAGE\]" logs/app_*.log
```

### Find all API calls:
```bash
grep "\[API\]" logs/app_*.log
```

### Find all errors:
```bash
grep "\[ERROR\]" logs/app_*.log
```

### Find slow requests (over 1 second):
```bash
grep "\[RESPONSE\]" logs/app_*.log | grep -E "Duration: [1-9][0-9]*\."
```

### Find all video generation activities:
```bash
grep -E "\[API\].*video|\[STATUS\].*video" logs/app_*.log -i
```

### Find all deck-related activities:
```bash
grep -E "\[API\].*deck|\[PAGE\].*deck" logs/app_*.log -i
```

### See complete user session (filter by IP):
```bash
grep "127.0.0.1" logs/app_*.log
```

## Log Levels

- **DEBUG**: Detailed information (status checks, query params, POST data)
- **INFO**: General information (page loads, API calls, status updates)
- **WARNING**: Warning messages (non-critical issues)
- **ERROR**: Error messages (exceptions, failures)
- **CRITICAL**: Critical errors (system failures)

Set log level with: `export LOG_LEVEL=DEBUG` for more verbose logging.

