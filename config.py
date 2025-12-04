"""
Bot Deploy Manager - Configuration File
Copy this file to config.py and fill in your credentials
"""

# ============================================================================
# TELEGRAM API CREDENTIALS (REQUIRED)
# ============================================================================
# Get these from https://my.telegram.org/apps
API_ID = "961780"  # Example: "12345678"
API_HASH = "bbbfa43f067e1e8e2fb41f334d32a6a7"  # Example: "0123456789abcdef0123456789abcdef"

# Get this from @BotFather on Telegram
BOT_TOKEN = "6486689995:AAEhCjdJsQCzlKcTFpai6Ux0GbRGqFh-gKk"  # Example: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"

# ============================================================================
# SECURITY SETTINGS (OPTIONAL)
# ============================================================================
# Whitelist of Telegram user IDs allowed to use the bot
# Leave empty list [] to allow all users (NOT RECOMMENDED for production)
# Get your user ID from @userinfobot on Telegram
ALLOWED_USERS = []  # Example: [123456789, 987654321]

# Token for shutdown endpoint authentication
# Generate with: import secrets; secrets.token_urlsafe(32)
SHUTDOWN_TOKEN = ""  # Example: "your_secure_random_token_here"

# ============================================================================
# SERVER SETTINGS (OPTIONAL)
# ============================================================================
# Flask server configuration
FLASK_PORT = 5000
FLASK_HOST = "0.0.0.0"

# ============================================================================
# PROCESS MANAGEMENT (OPTIONAL)
# ============================================================================
# Maximum number of concurrent processes
MAX_PROCESSES = 10

# Process monitoring interval in seconds
MONITOR_INTERVAL = 5

# Maximum process runtime in seconds (0 = unlimited)
PROCESS_TIMEOUT = 3600  # 1 hour

# Maximum restart attempts for failed processes
MAX_RESTART_ATTEMPTS = 3

# ============================================================================
# FILE PATHS (OPTIONAL)
# ============================================================================
# Directory for temporary script files
TEMP_DIR = "/tmp/botdeploy"

# Directory for log files
LOG_DIR = "./logs"

# Maximum log file size before rotation (in bytes)
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB

# Number of backup log files to keep
LOG_BACKUP_COUNT = 5

# ============================================================================
# DEPENDENCY MANAGEMENT (OPTIONAL)
# ============================================================================
# Use virtual environment for each process (RECOMMENDED)
USE_VENV = True

# Auto-detect and install dependencies from script imports
AUTO_INSTALL_DEPS = True

# Directory for virtual environments
VENV_DIR = "./venvs"

# Cleanup virtual environment after process stops
# Set to False to keep venvs for debugging
CLEANUP_VENV = False
