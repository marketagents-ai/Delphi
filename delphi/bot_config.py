import os
from dotenv import load_dotenv

# Force reload of .env file
if os.path.exists('.env'):
    load_dotenv(override=True)

# Bot configuration
TOKEN = os.getenv('DISCORD_TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPO_NAME = os.getenv('GITHUB_REPO')

OLLAMA_API_BASE = os.getenv('OLLAMA_API_BASE', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL')

# Discord configuration
DISCORD_CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

# File extensions
ALLOWED_EXTENSIONS = {'.py', '.js', '.html', '.css', '.json', '.md', '.txt'}

# Add allowed image types
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}


# Inverted Index Search configuration
MAX_TOKENS = 1000
CONTEXT_CHUNKS = 4
CHUNK_PERCENTAGE = 10

# Conversation history
MAX_CONVERSATION_HISTORY = 5

# Persona intensity handling
DEFAULT_PERSONA_INTENSITY = 70
TEMPERATURE = DEFAULT_PERSONA_INTENSITY / 100.0

# Temporary directory
TEMP_DIR = os.getenv('TEMP_DIR', 'temp_files')

# Make sure the directory exists
os.makedirs(TEMP_DIR, exist_ok=True)

# Logging configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Notion configuration
NOTION_API_KEY = os.getenv('NOTION_API_KEY')
CALENDAR_DB_ID = os.getenv('CALENDAR_DB_ID')
PROJECTS_DB_ID = os.getenv('PROJECTS_DB_ID')
TASKS_DB_ID = os.getenv('TASKS_DB_ID')
KANBAN_DB_ID = os.getenv('KANBAN_DB_ID')

# Polling configuration
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', 120))



###############################################
# Added for experimental multi-platform support

# Twitter Configuration
TWITTER_USERNAME = os.getenv('TWITTER_USERNAME')
TWITTER_API_KEY = os.getenv('TWITTER_API_KEY')
TWITTER_API_SECRET = os.getenv('TWITTER_API_SECRET')
TWITTER_ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
TWITTER_ACCESS_SECRET = os.getenv('TWITTER_ACCESS_SECRET')
TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN')

# Twitter Limits
TWITTER_CHAR_LIMIT = 280
TWITTER_MEDIA_LIMIT = 4
TWITTER_GIF_LIMIT = 1
TWITTER_VIDEO_LIMIT = 1
TWITTER_REPLY_DEPTH_LIMIT = 25  # Maximum thread depth

# Twitter Rate Limits
TWITTER_TWEET_RATE_LIMIT = 300  # per 3 hours
TWITTER_DM_RATE_LIMIT = 1000  # per 24 hours

# Web Server Configuration
FASTAPI_HOST = os.getenv('FASTAPI_HOST', 'localhost')
FASTAPI_PORT = int(os.getenv('FASTAPI_PORT', 8000))
FASTAPI_CORS_ORIGINS = os.getenv('FASTAPI_CORS_ORIGINS', '*').split(',')

# Web Rate Limits (following Twitter's pattern)
WEB_REQUEST_RATE_LIMIT = 100  # per minute
WEB_UPLOAD_RATE_LIMIT = 50    # per minute
WEB_WEBSOCKET_RATE_LIMIT = 60 # per minute

# Web Limits (following Twitter's pattern)
WEB_MAX_UPLOAD_SIZE = 1000000  # 1MB, matches existing file size limits
WEB_MAX_CONCURRENT_CONNECTIONS = 1000
WEB_MAX_WEBSOCKET_MESSAGE_SIZE = 16384  # 16KB
WEB_MAX_REQUEST_SIZE = 5000000  # 5MB for total request size

# Web Timeouts
WEB_WEBSOCKET_TIMEOUT = 60  # seconds
WEB_REQUEST_TIMEOUT = 30    # seconds
WEB_UPLOAD_TIMEOUT = 120    # seconds

# Web Session Management
WEB_SESSION_LIFETIME = 3600         # 1 hour in seconds
WEB_MAX_SESSIONS_PER_USER = 5       # Maximum concurrent sessions per user
WEB_SESSION_CLEANUP_INTERVAL = 300  # Clean up expired sessions every 5 minu