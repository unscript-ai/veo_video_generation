# Logging Guide

## Where to Find Logs

### 1. **Console/Terminal Output**
When you run `python app.py`, logs are displayed in your terminal in real-time.

### 2. **Log Files** (Recommended)
All logs are saved to timestamped files:
- **Location**: `logs/app_YYYYMMDD_HHMMSS.log`
- **Format**: Same as console output
- **Behavior**: Each app run creates a NEW log file with a unique timestamp
- **Example**: `logs/app_20260116_133925.log`, `logs/app_20260116_140530.log`

**Each time you start `app.py`, it creates a new log file** - this keeps your logs organized and makes it easy to track different runs.

## Viewing Logs

### View log files:
```bash
# List all log files (sorted by date, newest first)
ls -lt logs/app_*.log | head -5

# View the most recent log file
cat logs/$(ls -t logs/app_*.log | head -1)

# View last 50 lines of the most recent log
tail -n 50 logs/$(ls -t logs/app_*.log | head -1)

# Follow the most recent log file in real-time
tail -f logs/$(ls -t logs/app_*.log | head -1)

# View a specific log file by timestamp
cat logs/app_20260116_133925.log
```

### View logs with filters:
```bash
# Only show errors from the most recent log
grep ERROR logs/$(ls -t logs/app_*.log | head -1)

# Only show video generation logs from all logs
grep "video" logs/app_*.log -i

# Search for errors across all log files
grep ERROR logs/app_*.log

# Show last 100 lines of most recent log and filter for errors
tail -n 100 logs/$(ls -t logs/app_*.log | head -1) | grep ERROR

# View logs from a specific date (all log files for that date)
grep "2026-01-16" logs/app_*.log
```

## Log Levels

Configure log level via environment variable:
```bash
# Show only INFO and above (default)
export LOG_LEVEL=INFO
python app.py

# Show DEBUG and above (more verbose)
export LOG_LEVEL=DEBUG
python app.py

# Show only WARNING and above
export LOG_LEVEL=WARNING
python app.py
```

## Log File Configuration

### Default Behavior (Timestamped Files)
By default, each app run creates a new timestamped log file:
```bash
# Creates: logs/app_20260116_133925.log (timestamped automatically)
python app.py
```

### Use a Single Log File (Disable Timestamping)
If you prefer a single log file instead:
```bash
# Use a single log file (appends to same file each run)
export LOG_FILE=logs/app.log
export USE_TIMESTAMPED_LOGS=false
python app.py
```

### Custom Log File Path
```bash
# Use a custom log file path
export LOG_FILE=/path/to/your/custom.log
export USE_TIMESTAMPED_LOGS=false
python app.py
```

### Disable File Logging (Console Only)
```bash
# No file logging, only console output
export LOG_FILE=""
export USE_TIMESTAMPED_LOGS=false
python app.py
```

## Log Format

Each log entry includes:
- **Timestamp**: `YYYY-MM-DD HH:MM:SS`
- **Logger Name**: Module/component name
- **Level**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Message**: Log message

Example:
```
2026-01-16 13:39:25 - __main__ - INFO - Starting Veo Video Generation application on port 5000
2026-01-16 13:39:29 - services.video_service - INFO - Video generation task created: abc123def456
```

## Managing Log Files

### Find log files:
```bash
# List all log files with details (sorted by modification time)
ls -lht logs/app_*.log

# Count how many log files you have
ls -1 logs/app_*.log | wc -l

# Find the oldest log file
ls -t logs/app_*.log | tail -1

# Find the newest log file
ls -t logs/app_*.log | head -1
```

### Archive or delete old logs:
```bash
# Archive logs older than 7 days
find logs/ -name "app_*.log" -mtime +7 -exec mv {} logs/archive/ \;

# Delete logs older than 30 days (be careful!)
find logs/ -name "app_*.log" -mtime +30 -delete

# Compress old log files to save space
gzip logs/app_*.log
```

### Keep only recent logs:
```bash
# Keep only the last 10 log files, delete older ones
ls -t logs/app_*.log | tail -n +11 | xargs rm -f
```

## Production Recommendations

For production environments, consider:
1. **Log Rotation**: Use `RotatingFileHandler` instead of `FileHandler`
2. **External Logging**: Send logs to centralized systems (e.g., CloudWatch, Datadog, ELK)
3. **Log Levels**: Set to `WARNING` or `ERROR` in production to reduce noise
4. **Monitoring**: Set up alerts on ERROR and CRITICAL log entries

