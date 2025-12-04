"""
Bot Deploy Manager v2.0 - Professional Edition

A Telegram bot for deploying and managing Python scripts remotely.
Features: Process monitoring, auto-restart, logging, and web API.

Author: Bot Deploy Manager Team
Version: 2.0.0
License: MIT
"""

import os
import sys
import asyncio
import logging
import tempfile
import subprocess
from threading import Thread, Lock
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path

import requests
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from flask import Flask, request, jsonify
from logging.handlers import RotatingFileHandler

# Import configuration
try:
    import config
except ImportError:
    print("=" * 70)
    print("ERROR: config.py not found!")
    print("=" * 70)
    print("Please create config.py from config.py.example:")
    print("  1. Copy config.py.example to config.py")
    print("  2. Edit config.py and fill in your credentials")
    print("  3. Run this script again")
    print("=" * 70)
    sys.exit(1)


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging():
    """Configure logging with rotating file handler and console output"""
    log_dir = Path(getattr(config, 'LOG_DIR', './logs'))
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.INFO)
    
    # File handler with rotation
    max_log_size = getattr(config, 'MAX_LOG_SIZE', 10 * 1024 * 1024)
    log_backup_count = getattr(config, 'LOG_BACKUP_COUNT', 5)
    
    file_handler = RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=max_log_size,
        backupCount=log_backup_count
    )
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.DEBUG)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    return logging.getLogger(__name__)


logger = setup_logging()


# ============================================================================
# CONFIGURATION VALIDATION
# ============================================================================

def validate_config():
    """Validate required configuration parameters"""
    errors = []
    
    # Required fields
    required_fields = {
        'API_ID': 'Telegram API ID',
        'API_HASH': 'Telegram API Hash',
        'BOT_TOKEN': 'Telegram Bot Token'
    }
    
    for field, description in required_fields.items():
        value = getattr(config, field, None)
        if not value or str(value).startswith('YOUR_'):
            errors.append(f"{description} ({field}) is not configured")
    
    if errors:
        logger.error("Configuration validation failed:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.error("\nPlease edit config.py and provide valid credentials")
        raise ValueError("Invalid configuration")
    
    # Create directories
    temp_dir = Path(getattr(config, 'TEMP_DIR', '/tmp/botdeploy'))
    log_dir = Path(getattr(config, 'LOG_DIR', './logs'))
    temp_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("Configuration validated successfully")


# Validate configuration at startup
try:
    validate_config()
except ValueError as e:
    logger.critical(f"Configuration error: {e}")
    sys.exit(1)


# ============================================================================
# PROCESS INFORMATION
# ============================================================================

class ProcessInfo:
    """Information about a running process"""
    
    def __init__(self, pid: int, process: subprocess.Popen, 
                 file_path: Path, log_path: Path, chat_id: int):
        self.pid = pid
        self.process = process
        self.file_path = file_path
        self.log_path = log_path
        self.chat_id = chat_id
        self.created_at = datetime.now()
        self.restart_count = 0
        self.max_restarts = getattr(config, 'MAX_RESTART_ATTEMPTS', 3)
        self._status = "running"
    
    @property
    def status(self) -> str:
        """Get current process status with emoji"""
        if self._status == "stopped":
            return "⏹️ Stopped"
        
        return_code = self.process.poll()
        if return_code is None:
            return "✅ Running"
        elif return_code == 0:
            self._status = "stopped"
            return "✅ Completed"
        else:
            return f"❌ Failed (Exit Code: {return_code})"
    
    @property
    def is_running(self) -> bool:
        """Check if process is still running"""
        return self.process.poll() is None
    
    @property
    def runtime(self) -> str:
        """Get human-readable runtime"""
        delta = datetime.now() - self.created_at
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"
    
    def get_log_tail(self, lines: int = 50) -> str:
        """Get last N lines from log file"""
        try:
            if not self.log_path.exists():
                return "Log file not found"
            
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
            return f"Error reading log: {e}"
    
    def cleanup(self):
        """Cleanup process resources"""
        try:
            if self.is_running:
                logger.info(f"Terminating process {self.pid}")
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Process {self.pid} did not terminate, killing")
                    self.process.kill()
                    self.process.wait()
            
            # Remove temporary script file
            if self.file_path.exists():
                self.file_path.unlink()
                logger.debug(f"Removed script file: {self.file_path}")
            
            logger.info(f"Cleaned up process {self.pid}")
            
        except Exception as e:
            logger.error(f"Error cleaning up process {self.pid}: {e}")


# ============================================================================
# PROCESS MANAGER
# ============================================================================

class ProcessManager:
    """Thread-safe manager for running processes"""
    
    def __init__(self):
        self._processes: Dict[int, ProcessInfo] = {}
        self._lock = Lock()
        self._bot_client: Optional[Client] = None
        self._max_processes = getattr(config, 'MAX_PROCESSES', 10)
    
    def set_bot_client(self, client: Client):
        """Set bot client for notifications"""
        self._bot_client = client
    
    def add_process(self, process_info: ProcessInfo) -> bool:
        """Add process to registry"""
        with self._lock:
            if len(self._processes) >= self._max_processes:
                logger.warning(f"Maximum process limit reached ({self._max_processes})")
                return False
            
            self._processes[process_info.pid] = process_info
            logger.info(f"Added process {process_info.pid} to registry")
            return True
    
    def get_process(self, pid: int) -> Optional[ProcessInfo]:
        """Get process info by PID"""
        with self._lock:
            return self._processes.get(pid)
    
    def remove_process(self, pid: int) -> Optional[ProcessInfo]:
        """Remove process from registry"""
        with self._lock:
            process_info = self._processes.pop(pid, None)
            if process_info:
                logger.info(f"Removed process {pid} from registry")
            return process_info
    
    def get_all_processes(self) -> Dict[int, ProcessInfo]:
        """Get all processes (thread-safe copy)"""
        with self._lock:
            return self._processes.copy()
    
    def get_stats(self) -> dict:
        """Get process statistics"""
        processes = self.get_all_processes()
        return {
            'total': len(processes),
            'running': sum(1 for p in processes.values() if p.is_running),
            'max': self._max_processes
        }
    
    def cleanup_all(self):
        """Cleanup all processes"""
        logger.info("Cleaning up all processes...")
        with self._lock:
            for process_info in list(self._processes.values()):
                process_info.cleanup()
            self._processes.clear()
        logger.info("All processes cleaned up")
    
    async def monitor_processes(self):
        """Monitor all processes and handle failures"""
        monitor_interval = getattr(config, 'MONITOR_INTERVAL', 5)
        logger.info(f"Process monitor started (interval: {monitor_interval}s)")
        
        while True:
            try:
                await asyncio.sleep(monitor_interval)
                
                processes = self.get_all_processes()
                for pid, process_info in processes.items():
                    if not process_info.is_running and process_info._status != "stopped":
                        await self._handle_process_failure(process_info)
                
            except asyncio.CancelledError:
                logger.info("Process monitor stopped")
                break
            except Exception as e:
                logger.error(f"Error in process monitor: {e}", exc_info=True)
    
    async def _handle_process_failure(self, process_info: ProcessInfo):
        """Handle process failure and attempt restart"""
        return_code = process_info.process.poll()
        logger.warning(f"Process {process_info.pid} failed with exit code {return_code}")
        
        # Get error log
        error_log = process_info.get_log_tail(50)
        
        # Send notification
        if self._bot_client:
            message = (
                f"⚠️ **Process Failure Alert**\n\n"
                f"**PID:** `{process_info.pid}`\n"
                f"**Exit Code:** `{return_code}`\n"
                f"**File:** `{process_info.file_path.name}`\n"
                f"**Runtime:** {process_info.runtime}\n\n"
                f"**Last 50 lines of log:**\n"
                f"```\n{error_log[-2500:]}\n```"
            )
            
            try:
                await self._bot_client.send_message(
                    process_info.chat_id,
                    message,
                    parse_mode="markdown"
                )
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")
        
        # Attempt restart if under limit
        if process_info.restart_count < process_info.max_restarts:
            await self._restart_process(process_info)
        else:
            logger.warning(
                f"Process {process_info.pid} exceeded max restarts "
                f"({process_info.max_restarts})"
            )
            self.remove_process(process_info.pid)
            process_info.cleanup()
    
    async def _restart_process(self, old_process: ProcessInfo):
        """Restart a failed process"""
        try:
            logger.info(f"Attempting to restart process {old_process.pid}")
            
            # Append restart marker to log
            with open(old_process.log_path, "a") as log_file:
                log_file.write(f"\n\n{'='*60}\n")
                log_file.write(f"RESTART #{old_process.restart_count + 1} at {datetime.now()}\n")
                log_file.write(f"{'='*60}\n\n")
                
                # Start new process
                new_process = subprocess.Popen(
                    ['python3', str(old_process.file_path)],
                    stdout=log_file,
                    stderr=log_file,
                    env=os.environ,
                    cwd=old_process.file_path.parent
                )
            
            # Create new process info
            new_process_info = ProcessInfo(
                pid=new_process.pid,
                process=new_process,
                file_path=old_process.file_path,
                log_path=old_process.log_path,
                chat_id=old_process.chat_id
            )
            new_process_info.restart_count = old_process.restart_count + 1
            
            # Replace in registry
            self.remove_process(old_process.pid)
            self.add_process(new_process_info)
            
            # Send notification
            if self._bot_client:
                await self._bot_client.send_message(
                    old_process.chat_id,
                    f"🔄 **Process Restarted**\n\n"
                    f"**Old PID:** `{old_process.pid}`\n"
                    f"**New PID:** `{new_process.pid}`\n"
                    f"**Restart Count:** {new_process_info.restart_count}/{new_process_info.max_restarts}",
                    parse_mode="markdown"
                )
            
            logger.info(f"Process restarted successfully: {new_process.pid}")
            
        except Exception as e:
            logger.error(f"Failed to restart process: {e}", exc_info=True)
            if self._bot_client:
                await self._bot_client.send_message(
                    old_process.chat_id,
                    f"❌ **Failed to restart process**\n\n"
                    f"Error: `{str(e)}`"
                )


# Global process manager
process_manager = ProcessManager()


# ============================================================================
# TELEGRAM BOT
# ============================================================================

# Initialize bot
app = Client(
    "deploy_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN
)

# Set bot client in process manager
process_manager.set_bot_client(app)


def is_authorized(message: Message) -> bool:
    """Check if user is authorized to use bot"""
    allowed_users = getattr(config, 'ALLOWED_USERS', [])
    
    if not allowed_users:
        return True  # No restriction if not configured
    
    return message.from_user.id in allowed_users


@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    welcome_text = (
        "👋 **Welcome to Bot Deploy Manager v2.0**\n\n"
        "This bot allows you to deploy and manage Python scripts remotely.\n\n"
        "**Available Commands:**\n"
        "• `/deploy <url>` - Deploy script from URL\n"
        "• Send Python file - Deploy uploaded script\n"
        "• `/status` - Check all running processes\n"
        "• `/log <pid>` - Get log file for process\n"
        "• `/stop <pid>` - Stop a running process\n"
        "• `/help` - Show this help message\n\n"
        "**Features:**\n"
        "✅ Auto-restart on failure (max 3 attempts)\n"
        "✅ Real-time monitoring and notifications\n"
        "✅ Comprehensive logging\n"
        "✅ Process statistics\n\n"
        "⚠️ **Security Notice:**\n"
        "Only authorized users can use this bot."
    )
    await message.reply(welcome_text, parse_mode="markdown")


@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Handle /help command"""
    await start_command(client, message)


@app.on_message(filters.command("deploy") | filters.document)
async def deploy_command(client: Client, message: Message):
    """Handle script deployment"""
    
    # Authorization check
    if not is_authorized(message):
        await message.reply(
            "❌ **Access Denied**\n\n"
            "You are not authorized to use this bot.\n"
            "Contact the bot administrator for access."
        )
        logger.warning(f"Unauthorized access attempt by user {message.from_user.id}")
        return
    
    try:
        # Check process limit
        stats = process_manager.get_stats()
        if stats['total'] >= stats['max']:
            await message.reply(
                f"❌ **Process Limit Reached**\n\n"
                f"Maximum concurrent processes: {stats['max']}\n"
                f"Currently running: {stats['running']}\n\n"
                "Please stop some processes first using `/stop <pid>`"
            )
            return
        
        # Get script file
        file_path = None
        temp_dir = Path(getattr(config, 'TEMP_DIR', '/tmp/botdeploy'))
        
        if message.document and message.document.file_name.endswith(".py"):
            # File upload
            await message.reply("📥 **Downloading script file...**")
            downloaded_path = await message.download()
            
            # Move to temp directory with unique name
            timestamp = datetime.now().timestamp()
            file_path = temp_dir / f"script_{timestamp}_{message.document.file_name}"
            Path(downloaded_path).rename(file_path)
            
        elif message.command and len(message.command) > 1:
            # URL download
            url = message.command[1]
            await message.reply(f"📥 **Downloading script from URL...**")
            
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                
                # Save to temp file
                timestamp = datetime.now().timestamp()
                file_path = temp_dir / f"script_{timestamp}.py"
                file_path.write_bytes(response.content)
                
            except requests.exceptions.RequestException as e:
                await message.reply(
                    f"❌ **Download Failed**\n\n"
                    f"Error: `{str(e)}`\n\n"
                    "Please check the URL and try again."
                )
                logger.error(f"Download failed: {e}")
                return
        else:
            await message.reply(
                "❌ **Invalid Command**\n\n"
                "Please provide a script:\n"
                "• Send a Python file directly, or\n"
                "• Use `/deploy <url>` with a direct link to a Python file"
            )
            return
        
        # Validate file
        if not file_path or not file_path.exists():
            await message.reply("❌ **Failed to save script file**")
            return
        
        # Create log file
        log_dir = Path(getattr(config, 'LOG_DIR', './logs'))
        timestamp = datetime.now().timestamp()
        log_path = log_dir / f"process_{timestamp}.log"
        
        # Start process
        await message.reply("🚀 **Starting process...**")
        
        with open(log_path, "w") as log_file:
            log_file.write(f"{'='*60}\n")
            log_file.write(f"Bot Deploy Manager - Process Log\n")
            log_file.write(f"{'='*60}\n")
            log_file.write(f"Started: {datetime.now()}\n")
            log_file.write(f"Script: {file_path.name}\n")
            log_file.write(f"User ID: {message.from_user.id}\n")
            log_file.write(f"User: @{message.from_user.username or 'N/A'}\n")
            log_file.write(f"{'='*60}\n\n")
            
            process = subprocess.Popen(
                ['python3', str(file_path)],
                stdout=log_file,
                stderr=log_file,
                env=os.environ,
                cwd=temp_dir
            )
        
        # Create process info
        process_info = ProcessInfo(
            pid=process.pid,
            process=process,
            file_path=file_path,
            log_path=log_path,
            chat_id=message.chat.id
        )
        
        # Add to manager
        if process_manager.add_process(process_info):
            await message.reply(
                f"✅ **Process Started Successfully**\n\n"
                f"**PID:** `{process.pid}`\n"
                f"**File:** `{file_path.name}`\n"
                f"**Log:** `{log_path.name}`\n\n"
                f"**Monitoring:** Enabled\n"
                f"**Auto-restart:** Up to {process_info.max_restarts} attempts\n\n"
                "Use `/status` to check process status\n"
                "Use `/log {process.pid}` to view logs",
                parse_mode="markdown"
            )
            logger.info(
                f"Process {process.pid} started by user {message.from_user.id} "
                f"(@{message.from_user.username or 'N/A'})"
            )
        else:
            process.terminate()
            await message.reply("❌ **Failed to register process**")
            
    except Exception as e:
        logger.error(f"Error in deploy command: {e}", exc_info=True)
        await message.reply(
            f"❌ **An error occurred**\n\n"
            f"Error: `{str(e)}`\n\n"
            "Please try again or contact the administrator."
        )


@app.on_message(filters.command("status"))
async def status_command(client: Client, message: Message):
    """Handle status check command"""
    
    if not is_authorized(message):
        await message.reply("❌ You are not authorized to use this bot.")
        return
    
    processes = process_manager.get_all_processes()
    stats = process_manager.get_stats()
    
    if not processes:
        await message.reply(
            "ℹ️ **No Active Processes**\n\n"
            f"Maximum capacity: {stats['max']} processes\n\n"
            "Use `/deploy <url>` to start a new process"
        )
        return
    
    status_text = (
        f"📊 **Process Status**\n\n"
        f"**Total:** {stats['total']} / {stats['max']}\n"
        f"**Running:** {stats['running']}\n"
        f"{'─'*30}\n\n"
    )
    
    for pid, process_info in processes.items():
        status_text += (
            f"**PID:** `{pid}`\n"
            f"**Status:** {process_info.status}\n"
            f"**File:** `{process_info.file_path.name}`\n"
            f"**Runtime:** {process_info.runtime}\n"
            f"**Restarts:** {process_info.restart_count}/{process_info.max_restarts}\n"
            f"{'─'*30}\n"
        )
    
    await message.reply(status_text, parse_mode="markdown")


@app.on_message(filters.command("log"))
async def log_command(client: Client, message: Message):
    """Handle log retrieval command"""
    
    if not is_authorized(message):
        await message.reply("❌ You are not authorized to use this bot.")
        return
    
    if len(message.command) < 2:
        await message.reply(
            "❌ **Invalid Command**\n\n"
            "Usage: `/log <pid>`\n\n"
            "Example: `/log 12345`"
        )
        return
    
    try:
        pid = int(message.command[1])
        process_info = process_manager.get_process(pid)
        
        if not process_info:
            await message.reply(
                f"❌ **Process Not Found**\n\n"
                f"PID `{pid}` does not exist.\n\n"
                "Use `/status` to see active processes"
            )
            return
        
        if not process_info.log_path.exists():
            await message.reply("❌ **Log file not found**")
            return
        
        # Check file size
        file_size = process_info.log_path.stat().st_size
        max_telegram_size = 50 * 1024 * 1024  # 50MB Telegram limit
        
        if file_size > max_telegram_size:
            await message.reply(
                f"⚠️ **Log File Too Large**\n\n"
                f"File size: {file_size / 1024 / 1024:.2f} MB\n"
                f"Telegram limit: 50 MB\n\n"
                "Sending last 1000 lines instead..."
            )
            
            log_tail = process_info.get_log_tail(1000)
            
            # Save to temp file
            temp_dir = Path(getattr(config, 'TEMP_DIR', '/tmp/botdeploy'))
            temp_log = temp_dir / f"log_tail_{pid}.txt"
            temp_log.write_text(log_tail)
            
            await message.reply_document(
                str(temp_log),
                caption=f"📄 Last 1000 lines of log for PID {pid}"
            )
            
            temp_log.unlink()
        else:
            await message.reply_document(
                str(process_info.log_path),
                caption=f"📄 Complete log for PID {pid}\n"
                        f"Size: {file_size / 1024:.2f} KB"
            )
        
        logger.info(f"Log file sent for process {pid}")
        
    except ValueError:
        await message.reply("❌ PID must be a number")
    except Exception as e:
        logger.error(f"Error in log command: {e}", exc_info=True)
        await message.reply(f"❌ An error occurred: `{str(e)}`")


@app.on_message(filters.command("stop"))
async def stop_command(client: Client, message: Message):
    """Handle process stop command"""
    
    if not is_authorized(message):
        await message.reply("❌ You are not authorized to use this bot.")
        return
    
    if len(message.command) < 2:
        await message.reply(
            "❌ **Invalid Command**\n\n"
            "Usage: `/stop <pid>`\n\n"
            "Example: `/stop 12345`"
        )
        return
    
    try:
        pid = int(message.command[1])
        process_info = process_manager.get_process(pid)
        
        if not process_info:
            await message.reply(
                f"❌ **Process Not Found**\n\n"
                f"PID `{pid}` does not exist.\n\n"
                "Use `/status` to see active processes"
            )
            return
        
        # Mark as stopped to prevent restart
        process_info._status = "stopped"
        
        # Remove from manager and cleanup
        process_manager.remove_process(pid)
        process_info.cleanup()
        
        await message.reply(
            f"✅ **Process Stopped**\n\n"
            f"**PID:** `{pid}`\n"
            f"**File:** `{process_info.file_path.name}`\n"
            f"**Runtime:** {process_info.runtime}\n"
            f"**Log:** `{process_info.log_path.name}`\n\n"
            "The log file has been preserved for review.",
            parse_mode="markdown"
        )
        
        logger.info(
            f"Process {pid} stopped by user {message.from_user.id} "
            f"(@{message.from_user.username or 'N/A'})"
        )
        
    except ValueError:
        await message.reply("❌ PID must be a number")
    except Exception as e:
        logger.error(f"Error in stop command: {e}", exc_info=True)
        await message.reply(f"❌ An error occurred: `{str(e)}`")


# ============================================================================
# FLASK WEB SERVER
# ============================================================================

web_app = Flask(__name__)


@web_app.route('/')
def home():
    """Health check endpoint"""
    stats = process_manager.get_stats()
    return jsonify({
        "status": "running",
        "service": "Bot Deploy Manager",
        "version": "2.0.0",
        "processes": stats,
        "timestamp": datetime.now().isoformat()
    })


@web_app.route('/health')
def health():
    """Detailed health check"""
    stats = process_manager.get_stats()
    
    return jsonify({
        "status": "healthy",
        "version": "2.0.0",
        "processes": stats,
        "timestamp": datetime.now().isoformat()
    }), 200


@web_app.route('/stats')
def stats():
    """Process statistics endpoint"""
    processes = process_manager.get_all_processes()
    
    process_list = []
    for pid, info in processes.items():
        process_list.append({
            "pid": pid,
            "status": info.status,
            "file": info.file_path.name,
            "runtime": info.runtime,
            "restarts": info.restart_count,
            "max_restarts": info.max_restarts
        })
    
    return jsonify({
        "total": len(processes),
        "processes": process_list,
        "timestamp": datetime.now().isoformat()
    })


@web_app.route('/shutdown', methods=['POST'])
def shutdown():
    """Shutdown endpoint (protected)"""
    shutdown_token = getattr(config, 'SHUTDOWN_TOKEN', '')
    
    if not shutdown_token:
        return jsonify({"error": "Shutdown endpoint not configured"}), 403
    
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if token != shutdown_token:
        logger.warning("Unauthorized shutdown attempt")
        return jsonify({"error": "Unauthorized"}), 401
    
    logger.warning("Shutdown requested via API")
    
    # Cleanup all processes
    process_manager.cleanup_all()
    
    # Shutdown Flask
    func = request.environ.get('werkzeug.server.shutdown')
    if func:
        func()
    
    return jsonify({"status": "shutting down"})


def run_flask():
    """Run Flask server in thread"""
    flask_host = getattr(config, 'FLASK_HOST', '0.0.0.0')
    flask_port = getattr(config, 'FLASK_PORT', 5000)
    
    logger.info(f"Starting Flask server on {flask_host}:{flask_port}")
    web_app.run(
        host=flask_host,
        port=flask_port,
        threaded=True,
        debug=False
    )


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main():
    """Main async entry point"""
    logger.info("="*70)
    logger.info("Bot Deploy Manager v2.0.0 - Professional Edition")
    logger.info("="*70)
    
    try:
        # Start Flask in background thread
        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("✓ Flask server started")
        
        # Start bot
        await app.start()
        logger.info("✓ Telegram bot started")
        
        # Start process monitor
        monitor_task = asyncio.create_task(process_manager.monitor_processes())
        logger.info("✓ Process monitor started")
        
        logger.info("="*70)
        logger.info("All systems operational - Bot is ready!")
        logger.info("="*70)
        
        # Keep running
        await idle()
        
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Shutting down...")
        
        # Cleanup
        process_manager.cleanup_all()
        
        # Stop bot
        await app.stop()
        logger.info("✓ Bot stopped")
        
        logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical(f"Failed to start: {e}", exc_info=True)
        sys.exit(1)
