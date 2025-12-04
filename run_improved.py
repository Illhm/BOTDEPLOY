"""
Bot Telegram untuk Deployment dan Manajemen Skrip Python

Bot ini memungkinkan pengguna untuk:
- Deploy skrip Python dari URL atau file upload
- Monitor status proses yang berjalan
- Melihat log dari proses
- Menghentikan proses yang berjalan

Author: Improved Version
Version: 2.0.0
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


# ============================================================================
# KONFIGURASI LOGGING
# ============================================================================

def setup_logging():
    """Setup logging dengan rotating file handler"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Format log yang informatif
    log_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    console_handler.setLevel(logging.INFO)
    
    # File handler dengan rotation
    file_handler = RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(log_format)
    file_handler.setLevel(logging.DEBUG)
    
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    return logging.getLogger(__name__)


logger = setup_logging()


# ============================================================================
# KONFIGURASI ENVIRONMENT
# ============================================================================

class Config:
    """Konfigurasi aplikasi dari environment variables"""
    
    # Telegram API Configuration (WAJIB)
    API_ID = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # Security Configuration
    ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",")
    ALLOWED_USERS = [int(uid.strip()) for uid in ALLOWED_USERS if uid.strip()]
    
    SHUTDOWN_TOKEN = os.getenv("SHUTDOWN_TOKEN", "")
    
    # Flask Configuration
    FLASK_PORT = int(os.getenv("PORT", 5000))
    FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    
    # Process Configuration
    MAX_PROCESSES = int(os.getenv("MAX_PROCESSES", 10))
    PROCESS_TIMEOUT = int(os.getenv("PROCESS_TIMEOUT", 3600))  # 1 hour
    MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", 5))  # 5 seconds
    
    # File Configuration
    TEMP_DIR = Path(os.getenv("TEMP_DIR", tempfile.gettempdir())) / "botdeploy"
    LOG_DIR = Path("logs")
    MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
    
    @classmethod
    def validate(cls):
        """Validasi konfigurasi wajib"""
        errors = []
        
        if not cls.API_ID:
            errors.append("API_ID environment variable is required")
        if not cls.API_HASH:
            errors.append("API_HASH environment variable is required")
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN environment variable is required")
        
        if errors:
            for error in errors:
                logger.error(error)
            raise ValueError("Configuration validation failed. Check logs for details.")
        
        # Create directories
        cls.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        logger.info("Configuration validated successfully")


# Validasi konfigurasi saat startup
try:
    Config.validate()
except ValueError as e:
    logger.critical(f"Configuration error: {e}")
    sys.exit(1)


# ============================================================================
# PROCESS MANAGER
# ============================================================================

class ProcessInfo:
    """Informasi tentang proses yang berjalan"""
    
    def __init__(self, pid: int, process: subprocess.Popen, 
                 file_path: Path, log_path: Path, chat_id: int):
        self.pid = pid
        self.process = process
        self.file_path = file_path
        self.log_path = log_path
        self.chat_id = chat_id
        self.created_at = datetime.now()
        self.restart_count = 0
        self.max_restarts = 3
        self._status = "running"
    
    @property
    def status(self) -> str:
        """Get current process status"""
        if self._status == "stopped":
            return "❌ Stopped"
        
        return_code = self.process.poll()
        if return_code is None:
            return "✅ Running"
        elif return_code == 0:
            self._status = "stopped"
            return "✅ Completed"
        else:
            return f"❌ Failed (Code: {return_code})"
    
    @property
    def is_running(self) -> bool:
        """Check if process is still running"""
        return self.process.poll() is None
    
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
            # Terminate process if still running
            if self.is_running:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            
            # Remove temporary files
            if self.file_path.exists():
                self.file_path.unlink()
            
            # Keep log file for debugging
            logger.info(f"Cleaned up process {self.pid}")
            
        except Exception as e:
            logger.error(f"Error cleaning up process {self.pid}: {e}")


class ProcessManager:
    """Thread-safe manager untuk proses yang berjalan"""
    
    def __init__(self):
        self._processes: Dict[int, ProcessInfo] = {}
        self._lock = Lock()
        self._monitor_task: Optional[asyncio.Task] = None
        self._bot_client: Optional[Client] = None
    
    def set_bot_client(self, client: Client):
        """Set bot client untuk notifikasi"""
        self._bot_client = client
    
    def add_process(self, process_info: ProcessInfo) -> bool:
        """Add process to registry"""
        with self._lock:
            if len(self._processes) >= Config.MAX_PROCESSES:
                logger.warning("Maximum process limit reached")
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
    
    def cleanup_all(self):
        """Cleanup all processes"""
        logger.info("Cleaning up all processes...")
        with self._lock:
            for process_info in self._processes.values():
                process_info.cleanup()
            self._processes.clear()
    
    async def monitor_processes(self):
        """Monitor all processes and handle failures"""
        logger.info("Process monitor started")
        
        while True:
            try:
                await asyncio.sleep(Config.MONITOR_INTERVAL)
                
                processes = self.get_all_processes()
                for pid, process_info in processes.items():
                    if not process_info.is_running:
                        await self._handle_process_failure(process_info)
                
            except asyncio.CancelledError:
                logger.info("Process monitor stopped")
                break
            except Exception as e:
                logger.error(f"Error in process monitor: {e}", exc_info=True)
    
    async def _handle_process_failure(self, process_info: ProcessInfo):
        """Handle process failure and attempt restart"""
        return_code = process_info.process.poll()
        
        # Don't handle if already stopped manually
        if process_info._status == "stopped":
            return
        
        logger.warning(f"Process {process_info.pid} failed with code {return_code}")
        
        # Get error log
        error_log = process_info.get_log_tail(50)
        
        # Send notification
        if self._bot_client:
            message = (
                f"⚠️ **Process Failure Alert**\n\n"
                f"PID: `{process_info.pid}`\n"
                f"Exit Code: `{return_code}`\n"
                f"File: `{process_info.file_path.name}`\n\n"
                f"**Last 50 lines of log:**\n"
                f"```\n{error_log[-3000:]}\n```"
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
            logger.warning(f"Process {process_info.pid} exceeded max restarts")
            self.remove_process(process_info.pid)
            process_info.cleanup()
    
    async def _restart_process(self, old_process: ProcessInfo):
        """Restart a failed process"""
        try:
            logger.info(f"Attempting to restart process {old_process.pid}")
            
            # Create new process
            with open(old_process.log_path, "a") as log_file:
                log_file.write(f"\n\n{'='*50}\n")
                log_file.write(f"RESTART #{old_process.restart_count + 1} at {datetime.now()}\n")
                log_file.write(f"{'='*50}\n\n")
                
                new_process = subprocess.Popen(
                    ['python3', str(old_process.file_path)],
                    stdout=log_file,
                    stderr=log_file,
                    env=os.environ
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
                    f"🔄 Process restarted\n"
                    f"Old PID: `{old_process.pid}`\n"
                    f"New PID: `{new_process.pid}`\n"
                    f"Restart count: {new_process_info.restart_count}/{new_process_info.max_restarts}",
                    parse_mode="markdown"
                )
            
            logger.info(f"Process restarted successfully: {new_process.pid}")
            
        except Exception as e:
            logger.error(f"Failed to restart process: {e}", exc_info=True)
            if self._bot_client:
                await self._bot_client.send_message(
                    old_process.chat_id,
                    f"❌ Failed to restart process: {e}"
                )


# Global process manager
process_manager = ProcessManager()


# ============================================================================
# TELEGRAM BOT
# ============================================================================

# Initialize bot
app = Client(
    "deploy_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

# Set bot client in process manager
process_manager.set_bot_client(app)


def is_authorized(message: Message) -> bool:
    """Check if user is authorized to use bot"""
    if not Config.ALLOWED_USERS:
        return True  # No restriction if not configured
    
    return message.from_user.id in Config.ALLOWED_USERS


@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command"""
    welcome_text = (
        "👋 **Welcome to Bot Deploy Manager**\n\n"
        "Available commands:\n"
        "• `/deploy <url>` - Deploy script from URL\n"
        "• Send Python file - Deploy uploaded script\n"
        "• `/status` - Check all running processes\n"
        "• `/log <pid>` - Get log file for process\n"
        "• `/stop <pid>` - Stop a running process\n"
        "• `/help` - Show this help message\n\n"
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
        await message.reply("❌ You are not authorized to use this bot.")
        logger.warning(f"Unauthorized access attempt by user {message.from_user.id}")
        return
    
    try:
        # Check process limit
        if len(process_manager.get_all_processes()) >= Config.MAX_PROCESSES:
            await message.reply(
                f"❌ Maximum process limit reached ({Config.MAX_PROCESSES}). "
                "Please stop some processes first."
            )
            return
        
        # Get script file
        file_path = None
        
        if message.document and message.document.file_name.endswith(".py"):
            # File upload
            await message.reply("📥 Downloading script file...")
            downloaded_path = await message.download()
            
            # Move to temp directory with unique name
            file_path = Config.TEMP_DIR / f"script_{datetime.now().timestamp()}_{message.document.file_name}"
            Path(downloaded_path).rename(file_path)
            
        elif message.command and len(message.command) > 1:
            # URL download
            url = message.command[1]
            await message.reply(f"📥 Downloading script from URL...")
            
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                
                # Save to temp file
                file_path = Config.TEMP_DIR / f"script_{datetime.now().timestamp()}.py"
                file_path.write_bytes(response.content)
                
            except requests.exceptions.RequestException as e:
                await message.reply(f"❌ Failed to download script: {e}")
                logger.error(f"Download failed: {e}")
                return
        else:
            await message.reply(
                "❌ Please provide a script:\n"
                "• Send a Python file, or\n"
                "• Use `/deploy <url>` with a direct link"
            )
            return
        
        # Validate file
        if not file_path or not file_path.exists():
            await message.reply("❌ Failed to save script file")
            return
        
        # Create log file
        log_path = Config.LOG_DIR / f"process_{datetime.now().timestamp()}.log"
        
        # Start process
        await message.reply("🚀 Starting process...")
        
        with open(log_path, "w") as log_file:
            log_file.write(f"Process started at {datetime.now()}\n")
            log_file.write(f"Script: {file_path.name}\n")
            log_file.write(f"User: {message.from_user.id}\n")
            log_file.write(f"{'='*50}\n\n")
            
            process = subprocess.Popen(
                ['python3', str(file_path)],
                stdout=log_file,
                stderr=log_file,
                env=os.environ,
                cwd=Config.TEMP_DIR
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
                f"PID: `{process.pid}`\n"
                f"File: `{file_path.name}`\n"
                f"Log: `{log_path.name}`\n\n"
                f"Use `/status` to check process status\n"
                f"Use `/log {process.pid}` to view logs",
                parse_mode="markdown"
            )
            logger.info(f"Process {process.pid} started by user {message.from_user.id}")
        else:
            process.terminate()
            await message.reply("❌ Failed to register process")
            
    except Exception as e:
        logger.error(f"Error in deploy command: {e}", exc_info=True)
        await message.reply(f"❌ An error occurred: {e}")


@app.on_message(filters.command("status"))
async def status_command(client: Client, message: Message):
    """Handle status check command"""
    
    if not is_authorized(message):
        await message.reply("❌ You are not authorized to use this bot.")
        return
    
    processes = process_manager.get_all_processes()
    
    if not processes:
        await message.reply("ℹ️ No processes are currently running.")
        return
    
    status_text = "📊 **Process Status**\n\n"
    
    for pid, process_info in processes.items():
        runtime = datetime.now() - process_info.created_at
        hours, remainder = divmod(int(runtime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        status_text += (
            f"**PID:** `{pid}`\n"
            f"Status: {process_info.status}\n"
            f"File: `{process_info.file_path.name}`\n"
            f"Runtime: {hours}h {minutes}m {seconds}s\n"
            f"Restarts: {process_info.restart_count}/{process_info.max_restarts}\n"
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
        await message.reply("❌ Usage: `/log <pid>`")
        return
    
    try:
        pid = int(message.command[1])
        process_info = process_manager.get_process(pid)
        
        if not process_info:
            await message.reply(f"❌ Process with PID `{pid}` not found.")
            return
        
        if not process_info.log_path.exists():
            await message.reply("❌ Log file not found.")
            return
        
        # Check file size
        file_size = process_info.log_path.stat().st_size
        
        if file_size > 50 * 1024 * 1024:  # 50MB Telegram limit
            await message.reply(
                f"⚠️ Log file too large ({file_size / 1024 / 1024:.2f} MB)\n"
                f"Sending last 1000 lines instead..."
            )
            
            log_tail = process_info.get_log_tail(1000)
            
            # Save to temp file
            temp_log = Config.TEMP_DIR / f"log_tail_{pid}.txt"
            temp_log.write_text(log_tail)
            
            await message.reply_document(
                str(temp_log),
                caption=f"Last 1000 lines of log for PID {pid}"
            )
            
            temp_log.unlink()
        else:
            await message.reply_document(
                str(process_info.log_path),
                caption=f"Complete log for PID {pid}"
            )
        
        logger.info(f"Log file sent for process {pid}")
        
    except ValueError:
        await message.reply("❌ PID must be a number")
    except Exception as e:
        logger.error(f"Error in log command: {e}", exc_info=True)
        await message.reply(f"❌ An error occurred: {e}")


@app.on_message(filters.command("stop"))
async def stop_command(client: Client, message: Message):
    """Handle process stop command"""
    
    if not is_authorized(message):
        await message.reply("❌ You are not authorized to use this bot.")
        return
    
    if len(message.command) < 2:
        await message.reply("❌ Usage: `/stop <pid>`")
        return
    
    try:
        pid = int(message.command[1])
        process_info = process_manager.get_process(pid)
        
        if not process_info:
            await message.reply(f"❌ Process with PID `{pid}` not found.")
            return
        
        # Mark as stopped to prevent restart
        process_info._status = "stopped"
        
        # Remove from manager and cleanup
        process_manager.remove_process(pid)
        process_info.cleanup()
        
        await message.reply(
            f"✅ **Process Stopped**\n\n"
            f"PID: `{pid}`\n"
            f"File: `{process_info.file_path.name}`\n"
            f"Log saved at: `{process_info.log_path.name}`",
            parse_mode="markdown"
        )
        
        logger.info(f"Process {pid} stopped by user {message.from_user.id}")
        
    except ValueError:
        await message.reply("❌ PID must be a number")
    except Exception as e:
        logger.error(f"Error in stop command: {e}", exc_info=True)
        await message.reply(f"❌ An error occurred: {e}")


# ============================================================================
# FLASK WEB SERVER
# ============================================================================

web_app = Flask(__name__)


@web_app.route('/')
def home():
    """Health check endpoint"""
    return jsonify({
        "status": "running",
        "service": "Bot Deploy Manager",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat()
    })


@web_app.route('/health')
def health():
    """Detailed health check"""
    processes = process_manager.get_all_processes()
    
    return jsonify({
        "status": "healthy",
        "processes": {
            "total": len(processes),
            "running": sum(1 for p in processes.values() if p.is_running),
            "max": Config.MAX_PROCESSES
        },
        "uptime": "N/A",  # Could track this
        "timestamp": datetime.now().isoformat()
    })


@web_app.route('/shutdown', methods=['POST'])
def shutdown():
    """Shutdown endpoint (protected)"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not Config.SHUTDOWN_TOKEN or token != Config.SHUTDOWN_TOKEN:
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
    logger.info(f"Starting Flask server on {Config.FLASK_HOST}:{Config.FLASK_PORT}")
    web_app.run(
        host=Config.FLASK_HOST,
        port=Config.FLASK_PORT,
        threaded=True,
        debug=False
    )


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

async def main():
    """Main async entry point"""
    logger.info("="*50)
    logger.info("Bot Deploy Manager v2.0.0")
    logger.info("="*50)
    
    try:
        # Start Flask in background thread
        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("Flask server started")
        
        # Start bot
        await app.start()
        logger.info("Telegram bot started")
        
        # Start process monitor
        monitor_task = asyncio.create_task(process_manager.monitor_processes())
        logger.info("Process monitor started")
        
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
        logger.info("Bot stopped")
        
        logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.critical(f"Failed to start: {e}", exc_info=True)
        sys.exit(1)
