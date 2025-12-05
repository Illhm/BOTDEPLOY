"""
Bot Deploy Manager v2.0 - Professional Edition

A Telegram bot for deploying and managing Python scripts remotely.
Features: Process monitoring, auto-restart, logging, dependency management, and web API.

Author: Bot Deploy Manager Team
Version: 2.1.0
License: MIT
"""

import os
import sys
import re
import ast
import asyncio
import logging
import tempfile
import subprocess
import venv
from threading import Thread, Lock
from typing import Dict, Optional, Set, List
from datetime import datetime
from pathlib import Path

import requests
from telebot.async_telebot import AsyncTeleBot
from telebot import types as tele_types
from flask import Flask, request, jsonify
from logging.handlers import RotatingFileHandler

# Import configuration with environment variable fallback
try:
    import config  # type: ignore
except ImportError:
    class EnvConfig:  # pragma: no cover - simple container for env vars
        pass

    config = EnvConfig()  # type: ignore

# Override config values with environment variables when provided
def _load_env_overrides():
    """Load configuration values from environment variables when present."""

    env_mapping = {
        "BOT_TOKEN": "BOT_TOKEN",
        "ALLOWED_USERS": "ALLOWED_USERS",
        "SHUTDOWN_TOKEN": "SHUTDOWN_TOKEN",
        "FLASK_PORT": "PORT",  # Common PaaS convention
        "FLASK_HOST": "FLASK_HOST",
        "MAX_PROCESSES": "MAX_PROCESSES",
        "MONITOR_INTERVAL": "MONITOR_INTERVAL",
        "PROCESS_TIMEOUT": "PROCESS_TIMEOUT",
        "MAX_RESTART_ATTEMPTS": "MAX_RESTART_ATTEMPTS",
        "TEMP_DIR": "TEMP_DIR",
        "LOG_DIR": "LOG_DIR",
        "MAX_LOG_SIZE": "MAX_LOG_SIZE",
        "LOG_BACKUP_COUNT": "LOG_BACKUP_COUNT",
        "USE_VENV": "USE_VENV",
        "AUTO_INSTALL_DEPS": "AUTO_INSTALL_DEPS",
        "VENV_DIR": "VENV_DIR",
        "CLEANUP_VENV": "CLEANUP_VENV",
    }

    int_fields = {"FLASK_PORT", "MAX_PROCESSES", "MONITOR_INTERVAL", "PROCESS_TIMEOUT", "MAX_RESTART_ATTEMPTS"}

    for attr_name, env_name in env_mapping.items():
        env_value = os.getenv(env_name)
        if env_value is None:
            continue

        # Simple parsing for list/integer/boolean values
        if attr_name == "ALLOWED_USERS":
            try:
                parsed_users = [int(user.strip()) for user in env_value.split(",") if user.strip()]
                setattr(config, attr_name, parsed_users)
            except ValueError:
                logger.warning("Invalid ALLOWED_USERS env format, expected comma-separated integers")
            continue

        if env_value.lower() in {"true", "false"}:
            setattr(config, attr_name, env_value.lower() == "true")
            continue

        if attr_name in int_fields:
            try:
                setattr(config, attr_name, int(str(env_value).strip()))
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid integer value for %s from environment (%s); using default", attr_name, env_value
                )
            continue

        setattr(config, attr_name, env_value)


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

# Apply environment variable overrides after logger is ready
_load_env_overrides()


# ============================================================================
# CONFIGURATION VALIDATION
# ============================================================================

def validate_config():
    """Validate required configuration parameters"""
    errors = []

    # Required fields
    required_fields = {
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
    venv_dir = Path(getattr(config, 'VENV_DIR', './venvs'))
    
    temp_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    venv_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("Configuration validated successfully")


# Validate configuration at startup
try:
    validate_config()
except ValueError as e:
    logger.critical(f"Configuration error: {e}")
    sys.exit(1)


# ============================================================================
# DEPENDENCY MANAGER
# ============================================================================

class DependencyManager:
    """Manage dependencies for deployed scripts"""
    
    # Standard library modules (no need to install)
    STDLIB_MODULES = {
        'abc', 'aifc', 'argparse', 'array', 'ast', 'asynchat', 'asyncio', 'asyncore',
        'atexit', 'audioop', 'base64', 'bdb', 'binascii', 'binhex', 'bisect', 'builtins',
        'bz2', 'calendar', 'cgi', 'cgitb', 'chunk', 'cmath', 'cmd', 'code', 'codecs',
        'codeop', 'collections', 'colorsys', 'compileall', 'concurrent', 'configparser',
        'contextlib', 'copy', 'copyreg', 'cProfile', 'crypt', 'csv', 'ctypes', 'curses',
        'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib', 'dis', 'distutils', 'doctest',
        'email', 'encodings', 'enum', 'errno', 'faulthandler', 'fcntl', 'filecmp', 'fileinput',
        'fnmatch', 'formatter', 'fractions', 'ftplib', 'functools', 'gc', 'getopt', 'getpass',
        'gettext', 'glob', 'grp', 'gzip', 'hashlib', 'heapq', 'hmac', 'html', 'http', 'imaplib',
        'imghdr', 'imp', 'importlib', 'inspect', 'io', 'ipaddress', 'itertools', 'json', 'keyword',
        'lib2to3', 'linecache', 'locale', 'logging', 'lzma', 'mailbox', 'mailcap', 'marshal',
        'math', 'mimetypes', 'mmap', 'modulefinder', 'multiprocessing', 'netrc', 'nis', 'nntplib',
        'numbers', 'operator', 'optparse', 'os', 'ossaudiodev', 'parser', 'pathlib', 'pdb',
        'pickle', 'pickletools', 'pipes', 'pkgutil', 'platform', 'plistlib', 'poplib', 'posix',
        'posixpath', 'pprint', 'profile', 'pstats', 'pty', 'pwd', 'py_compile', 'pyclbr', 'pydoc',
        'queue', 'quopri', 'random', 're', 'readline', 'reprlib', 'resource', 'rlcompleter',
        'runpy', 'sched', 'secrets', 'select', 'selectors', 'shelve', 'shlex', 'shutil', 'signal',
        'site', 'smtpd', 'smtplib', 'sndhdr', 'socket', 'socketserver', 'spwd', 'sqlite3', 'ssl',
        'stat', 'statistics', 'string', 'stringprep', 'struct', 'subprocess', 'sunau', 'symbol',
        'symtable', 'sys', 'sysconfig', 'syslog', 'tabnanny', 'tarfile', 'telnetlib', 'tempfile',
        'termios', 'test', 'textwrap', 'threading', 'time', 'timeit', 'tkinter', 'token',
        'tokenize', 'trace', 'traceback', 'tracemalloc', 'tty', 'turtle', 'turtledemo', 'types',
        'typing', 'unicodedata', 'unittest', 'urllib', 'uu', 'uuid', 'venv', 'warnings', 'wave',
        'weakref', 'webbrowser', 'winreg', 'winsound', 'wsgiref', 'xdrlib', 'xml', 'xmlrpc',
        'zipapp', 'zipfile', 'zipimport', 'zlib', '_thread'
    }
    
    @staticmethod
    def extract_imports(script_path: Path) -> Set[str]:
        """Extract all import statements from a Python script"""
        imports = set()
        
        try:
            with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Parse AST
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.add(alias.name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imports.add(node.module.split('.')[0])
            except SyntaxError:
                logger.warning(f"Syntax error in {script_path}, falling back to regex")
                # Fallback to regex
                import_pattern = r'^\s*(?:from\s+(\S+)|import\s+(\S+))'
                for match in re.finditer(import_pattern, content, re.MULTILINE):
                    module = match.group(1) or match.group(2)
                    imports.add(module.split('.')[0].split(' ')[0])
            
            # Filter out standard library
            external_imports = imports - DependencyManager.STDLIB_MODULES
            
            logger.debug(f"Found imports: {external_imports}")
            return external_imports
            
        except Exception as e:
            logger.error(f"Error extracting imports: {e}")
            return set()
    
    @staticmethod
    def create_venv(venv_path: Path) -> bool:
        """Create a virtual environment"""
        try:
            logger.info(f"Creating virtual environment at {venv_path}")
            venv.create(venv_path, with_pip=True, clear=True)
            logger.info("Virtual environment created successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to create venv: {e}")
            return False
    
    @staticmethod
    def install_packages(venv_path: Path, packages: List[str]) -> tuple[bool, str]:
        """Install packages in virtual environment"""
        if not packages:
            return True, "No packages to install"
        
        pip_path = venv_path / "bin" / "pip"
        if not pip_path.exists():
            pip_path = venv_path / "Scripts" / "pip.exe"  # Windows
        
        if not pip_path.exists():
            return False, "pip not found in venv"
        
        try:
            logger.info(f"Installing packages: {packages}")
            
            # Install packages
            cmd = [str(pip_path), "install", "--no-cache-dir"] + packages
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )
            
            if result.returncode == 0:
                logger.info("Packages installed successfully")
                return True, result.stdout
            else:
                logger.error(f"Package installation failed: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Installation timeout (5 minutes)"
        except Exception as e:
            logger.error(f"Error installing packages: {e}")
            return False, str(e)
    
    @staticmethod
    def install_from_requirements(venv_path: Path, requirements_file: Path) -> tuple[bool, str]:
        """Install packages from requirements.txt"""
        pip_path = venv_path / "bin" / "pip"
        if not pip_path.exists():
            pip_path = venv_path / "Scripts" / "pip.exe"
        
        if not pip_path.exists():
            return False, "pip not found in venv"
        
        try:
            logger.info(f"Installing from requirements: {requirements_file}")
            
            cmd = [str(pip_path), "install", "--no-cache-dir", "-r", str(requirements_file)]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                logger.info("Requirements installed successfully")
                return True, result.stdout
            else:
                logger.error(f"Requirements installation failed: {result.stderr}")
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "Installation timeout (5 minutes)"
        except Exception as e:
            logger.error(f"Error installing requirements: {e}")
            return False, str(e)


# ============================================================================
# PROCESS INFORMATION
# ============================================================================

class ProcessInfo:
    """Information about a running process"""
    
    def __init__(
        self,
        pid: int,
        process: subprocess.Popen,
        file_path: Path,
        log_path: Path,
        chat_id: int,
        venv_path: Optional[Path] = None,
        requirements_file: Optional[Path] = None,
        max_restarts: Optional[int] = None,
    ):
        self.pid = pid
        self.process = process
        self.file_path = file_path
        self.log_path = log_path
        self.chat_id = chat_id
        self.venv_path = venv_path
        self.requirements_file = requirements_file
        self.created_at = datetime.now()
        self.restart_count = 0
        self.max_restarts = max_restarts if max_restarts is not None else getattr(
            config, 'MAX_RESTART_ATTEMPTS', 3
        )
        self._status = "running"
        self.dependencies_installed = False
    
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
            
            # Remove requirements file if exists
            if self.requirements_file and self.requirements_file.exists():
                self.requirements_file.unlink()
                logger.debug(f"Removed requirements file: {self.requirements_file}")
            
            # Optionally remove venv (configurable)
            if getattr(config, 'CLEANUP_VENV', False) and self.venv_path:
                if self.venv_path.exists():
                    import shutil
                    shutil.rmtree(self.venv_path, ignore_errors=True)
                    logger.debug(f"Removed venv: {self.venv_path}")
            
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
        self._bot_client: Optional[AsyncTeleBot] = None
        self._max_processes = getattr(config, 'MAX_PROCESSES', 10)
        self._dependency_manager = DependencyManager()
    
    def set_bot_client(self, client: AsyncTeleBot):
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
    
    async def setup_dependencies(self, script_path: Path, requirements_file: Optional[Path] = None) -> tuple[Optional[Path], str]:
        """Setup virtual environment and install dependencies"""
        use_venv = getattr(config, 'USE_VENV', True)
        auto_install = getattr(config, 'AUTO_INSTALL_DEPS', True)
        
        if not use_venv and not auto_install:
            return None, "Dependency management disabled"
        
        # Create venv directory
        venv_dir = Path(getattr(config, 'VENV_DIR', './venvs'))
        timestamp = datetime.now().timestamp()
        venv_path = venv_dir / f"venv_{timestamp}"
        
        messages = []
        
        try:
            # Create virtual environment
            if use_venv:
                messages.append("📦 Creating virtual environment...")
                if not self._dependency_manager.create_venv(venv_path):
                    return None, "Failed to create virtual environment"
                messages.append("✅ Virtual environment created")
            
            # Install from requirements.txt if provided
            if requirements_file and requirements_file.exists():
                messages.append(f"📥 Installing from {requirements_file.name}...")
                success, output = self._dependency_manager.install_from_requirements(venv_path, requirements_file)
                
                if success:
                    messages.append("✅ Requirements installed successfully")
                else:
                    messages.append(f"⚠️ Requirements installation failed:\n{output[:500]}")
                    # Continue anyway, script might still work
            
            # Auto-detect and install dependencies
            elif auto_install:
                messages.append("🔍 Detecting dependencies...")
                imports = self._dependency_manager.extract_imports(script_path)
                
                if imports:
                    messages.append(f"📦 Found packages: {', '.join(imports)}")
                    messages.append("⏳ Installing packages...")
                    
                    success, output = self._dependency_manager.install_packages(venv_path, list(imports))
                    
                    if success:
                        messages.append("✅ Dependencies installed successfully")
                    else:
                        messages.append(f"⚠️ Some packages failed to install:\n{output[:500]}")
                        messages.append("⚠️ Script will run with available packages")
                else:
                    messages.append("ℹ️ No external dependencies detected")
            
            return venv_path if use_venv else None, "\n".join(messages)
            
        except Exception as e:
            logger.error(f"Error setting up dependencies: {e}")
            return None, f"❌ Dependency setup failed: {str(e)}"
    
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

    def run_script(
        self,
        script_path: Path,
        log_path: Path,
        venv_path: Optional[Path],
        chat_id: int,
    ) -> Optional[subprocess.Popen]:
        """Start a script as a subprocess with optional virtual environment.

        Returns the Popen object or None when startup fails.
        """

        try:
            python_path = Path(sys.executable)
            if venv_path:
                python_path = venv_path / "bin" / "python"
                if not python_path.exists():
                    python_path = venv_path / "Scripts" / "python.exe"

            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a") as log_file:
                process = subprocess.Popen(
                    [str(python_path), str(script_path)],
                    stdout=log_file,
                    stderr=log_file,
                    cwd=script_path.parent,
                    env=os.environ,
                )

            return process

        except Exception as exc:
            logger.error(
                "Failed to start script %s for chat %s: %s", script_path, chat_id, exc, exc_info=True
            )
            return None
    
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
                    parse_mode="Markdown"
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
            
            # Determine python executable
            if old_process.venv_path:
                python_path = old_process.venv_path / "bin" / "python"
                if not python_path.exists():
                    python_path = old_process.venv_path / "Scripts" / "python.exe"
            else:
                python_path = sys.executable
            
            # Append restart marker to log
            with open(old_process.log_path, "a") as log_file:
                log_file.write(f"\n\n{'='*60}\n")
                log_file.write(f"RESTART #{old_process.restart_count + 1} at {datetime.now()}\n")
                log_file.write(f"{'='*60}\n\n")
                
                # Start new process
                new_process = subprocess.Popen(
                    [str(python_path), str(old_process.file_path)],
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
                chat_id=old_process.chat_id,
                venv_path=old_process.venv_path,
                requirements_file=old_process.requirements_file
            )
            new_process_info.restart_count = old_process.restart_count + 1
            new_process_info.dependencies_installed = old_process.dependencies_installed
            
            # Replace in registry
            self.remove_process(old_process.pid)
            self.add_process(new_process_info)
            
            # Send notification
            if self._bot_client:
                restart_message = (
                    "🔄 **Process Restarted**\n\n"
                    f"**Old PID:** `{old_process.pid}`\n"
                    f"**New PID:** `{new_process.pid}`\n"
                    f"**Restart Count:** {new_process_info.restart_count}/{new_process_info.max_restarts}"
                )
                await self._bot_client.send_message(
                    old_process.chat_id,
                    restart_message,
                    parse_mode="Markdown"
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
bot = AsyncTeleBot(
    config.BOT_TOKEN,
    parse_mode="Markdown"
)

# Set bot client in process manager
process_manager.set_bot_client(bot)


def _parse_allowed_users(raw_value) -> List[int]:
    """Normalize ALLOWED_USERS to a list of integers."""

    if raw_value in (None, False):
        return []

    # Already a list or tuple: coerce each element to int when possible
    if isinstance(raw_value, (list, tuple, set)):
        parsed = []
        for user in raw_value:
            try:
                parsed.append(int(user))
            except (TypeError, ValueError):
                logger.warning("Ignoring invalid user id in ALLOWED_USERS: %s", user)
        return parsed

    # String input (e.g., environment variable or misconfigured value)
    if isinstance(raw_value, str):
        # Support both comma-separated numbers and bracketed lists
        cleaned = raw_value.strip().strip("[]")
        if not cleaned:
            return []

        parsed = []
        for user in cleaned.split(','):
            user = user.strip().strip("'\"")
            if not user:
                continue
            try:
                parsed.append(int(user))
            except ValueError:
                logger.warning("Ignoring invalid user id in ALLOWED_USERS: %s", user)
        return parsed

    logger.warning("Unsupported ALLOWED_USERS type: %s", type(raw_value))
    return []


def is_authorized(message: tele_types.Message) -> bool:
    """Check if user is authorized to use bot."""

    if not getattr(message, "from_user", None):
        logger.warning("Received message without from_user; rejecting for safety")
        return False

    allowed_users = _parse_allowed_users(getattr(config, 'ALLOWED_USERS', []))

    if not allowed_users:
        return True  # No restriction if not configured

    return message.from_user.id in allowed_users


def _parse_command(message: tele_types.Message) -> List[str]:
    """Split incoming command text into parts."""

    text = (message.text or message.caption or "").strip()
    if not text.startswith('/'):
        return []
    return text.split()


async def _reply(message: tele_types.Message, text: str, **kwargs):
    """Convenience wrapper for sending replies."""

    return await bot.send_message(message.chat.id, text, **kwargs)


async def _reply_document(message: tele_types.Message, file_path: Path, **kwargs):
    """Send a document to the chat."""

    with open(file_path, "rb") as doc_file:
        return await bot.send_document(message.chat.id, doc_file, **kwargs)


async def _download_document(message: tele_types.Message, destination: Path) -> Path:
    file_info = await bot.get_file(message.document.file_id)
    file_bytes = await bot.download_file(file_info.file_path)
    destination.write_bytes(file_bytes)
    return destination


# Global storage for pending deployments (waiting for requirements.txt)
pending_deployments: Dict[int, dict] = {}


@bot.message_handler(commands=["start"])
async def start_command(message: tele_types.Message):
    """Handle /start command"""
    welcome_text = (
        "👋 **Welcome to Bot Deploy Manager v2.1**\n\n"
        "This bot allows you to deploy and manage Python scripts remotely with automatic dependency management.\n\n"
        "**Available Commands:**\n"
        "• `/deploy <url>` - Deploy script from URL\n"
        "• Send Python file - Deploy uploaded script\n"
        "• Send requirements.txt - Upload dependencies\n"
        "• `/status` - Check all running processes\n"
        "• `/log <pid>` - Get log file for process\n"
        "• `/stop <pid>` - Stop a running process\n"
        "• `/help` - Show this help message\n\n"
        "**Features:**\n"
        "✅ Auto-detect and install dependencies\n"
        "✅ Virtual environment per process\n"
        "✅ Auto-restart on failure (max 3 attempts)\n"
        "✅ Real-time monitoring and notifications\n"
        "✅ Comprehensive logging\n\n"
        "⚠️ **Security Notice:**\n"
        "Only authorized users can use this bot."
    )
    await _reply(message, welcome_text)


@bot.message_handler(commands=["help"])
async def help_command(message: tele_types.Message):
    """Handle /help command"""
    await start_command(message)


async def _handle_deploy(message: tele_types.Message, file_path: Path, requirements_file: Optional[Path]):
    """Shared deployment logic once script and requirements are available."""

    log_dir = Path(getattr(config, 'LOG_DIR', './logs'))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"log_{datetime.now().timestamp()}.txt"

    await _reply(message, "⚙️ **Preparing environment...**")

    venv_path, dep_status = await process_manager.setup_dependencies(
        file_path, requirements_file
    )

    await _reply(message, dep_status)

    process = process_manager.run_script(file_path, log_path, venv_path, message.chat.id)

    if not process:
        await _reply(message, "❌ Failed to start process")
        return

    process_info = ProcessInfo(
        pid=process.pid,
        process=process,
        file_path=file_path,
        log_path=log_path,
        chat_id=message.chat.id,
        venv_path=venv_path,
        requirements_file=requirements_file,
        max_restarts=getattr(config, 'MAX_RESTART_ATTEMPTS', 3)
    )
    process_info.dependencies_installed = dep_status.startswith("✅")

    if not process_manager.add_process(process_info):
        process.terminate()
        await _reply(message, "❌ **Process limit reached**")
        return

    await _reply(
        message,
        (
            f"✅ **Deployment Started**\n\n"
            f"**PID:** `{process.pid}`\n"
            f"**File:** `{file_path.name}`\n"
            f"**Log:** `{log_path.name}`\n\n"
            "Use `/status` to monitor progress"
        ),
    )

    logger.info(f"Started process {process.pid} for file {file_path}")


@bot.message_handler(commands=["deploy"])
async def deploy_command(message: tele_types.Message):
    """Handle script deployment from URL."""

    if not is_authorized(message):
        await _reply(
            message,
            "❌ **Access Denied**\n\n"
            "You are not authorized to use this bot.\n"
            "Contact the bot administrator for access."
        )
        logger.warning(f"Unauthorized access attempt by user {message.from_user.id}")
        return

    parts = _parse_command(message)
    if len(parts) < 2:
        await _reply(message, "❌ **Invalid Command**\n\nUsage: `/deploy <url>`")
        return

    stats = process_manager.get_stats()
    if stats['total'] >= stats['max']:
        await _reply(
            message,
            f"❌ **Process Limit Reached**\n\n"
            f"Maximum concurrent processes: {stats['max']}\n"
            f"Currently running: {stats['running']}\n\n"
            "Please stop some processes first using `/stop <pid>`"
        )
        return

    url = parts[1]
    if not re.match(r'^https?://', url):
        await _reply(
            message,
            "❌ **Invalid URL**\n\n"
            "Please provide a valid HTTP/HTTPS URL"
        )
        return

    temp_dir = Path(getattr(config, 'TEMP_DIR', '/tmp/botdeploy'))
    await _reply(message, "🌐 **Downloading script from URL...**")

    file_path = temp_dir / f"script_{datetime.now().timestamp()}.py"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        file_path.write_text(response.text, encoding='utf-8')
    except Exception as e:
        logger.error(f"Failed to download script: {e}")
        await _reply(
            message,
            "❌ **Download Failed**\n\n"
            f"Error: `{str(e)}`"
        )
        return

    await _handle_deploy(message, file_path, None)


@bot.message_handler(content_types=['document'])
async def deploy_document(message: tele_types.Message):
    """Handle script and requirements file uploads."""

    if not is_authorized(message):
        await _reply(message, "❌ You are not authorized to use this bot.")
        return

    stats = process_manager.get_stats()
    if stats['total'] >= stats['max']:
        await _reply(
            message,
            f"❌ **Process Limit Reached**\n\n"
            f"Maximum concurrent processes: {stats['max']}\n"
            f"Currently running: {stats['running']}\n\n"
            "Please stop some processes first using `/stop <pid>`"
        )
        return

    temp_dir = Path(getattr(config, 'TEMP_DIR', '/tmp/botdeploy'))
    temp_dir.mkdir(parents=True, exist_ok=True)

    if message.document.file_name == "requirements.txt":
        user_id = message.from_user.id
        if user_id not in pending_deployments:
            await _reply(
                message,
                "⚠️ **No Pending Deployment**\n\n"
                "Please deploy a Python script first, then send requirements.txt"
            )
            return

        await _reply(message, "📥 **Downloading requirements.txt...**")
        requirements_path = temp_dir / f"requirements_{datetime.now().timestamp()}.txt"
        await _download_document(message, requirements_path)

        pending = pending_deployments.pop(user_id)
        await _reply(
            message,
            "✅ **Requirements received!**\n\n"
            "Starting deployment with custom requirements..."
        )
        await _handle_deploy(message, pending['file_path'], requirements_path)
        return

    if not message.document.file_name.endswith('.py'):
        await _reply(message, "❌ Only Python files (.py) are supported for deployment.")
        return

    await _reply(message, "📥 **Downloading script file...**")
    timestamp = datetime.now().timestamp()
    script_path = temp_dir / f"script_{timestamp}_{message.document.file_name}"
    await _download_document(message, script_path)

    user_id = message.from_user.id
    pending_deployments[user_id] = {'file_path': script_path, 'timestamp': timestamp}

    await _reply(
        message,
        "✅ **Script received!**\n\n"
        "📋 **Optional:** Send `requirements.txt` now for custom dependencies\n"
        "⏭️ **Or** wait 10 seconds for auto-detection\n\n"
        "Auto-deployment will start automatically..."
    )

    await asyncio.sleep(10)

    if user_id in pending_deployments:
        pending_deployments.pop(user_id)
        await _handle_deploy(message, script_path, None)


@bot.message_handler(commands=["status"])
async def status_command(message: tele_types.Message):
    """Handle status command"""

    if not is_authorized(message):
        await _reply(message, "❌ You are not authorized to use this bot.")
        return

    processes = process_manager.get_all_processes()

    if not processes:
        await _reply(message, "ℹ️ No active processes at the moment.")
        return

    status_messages = ["📊 **Process Status**\n"]

    for process in processes.values():
        status_messages.append(
            f"PID: `{process.pid}`\n"
            f"Status: {'✅ Running' if process.is_running else '❌ Stopped'}\n"
            f"File: {process.file_path.name}\n"
            f"Runtime: {process.runtime}\n"
            f"Restarts: {process.restart_count}/{process.max_restarts}\n"
            f"Log: {process.log_path.name}\n"
            "──────────────────────────────\n"
        )

    await _reply(message, "\n".join(status_messages))


@bot.message_handler(commands=["log"])
async def log_command(message: tele_types.Message):
    """Handle log retrieval command"""

    if not is_authorized(message):
        await _reply(message, "❌ You are not authorized to use this bot.")
        return

    parts = _parse_command(message)
    if len(parts) < 2:
        await _reply(
            message,
            "❌ **Invalid Command**\n\n"
            "Usage: `/log <pid>`\n\n"
            "Example: `/log 12345`"
        )
        return

    try:
        pid = int(parts[1])
        process_info = process_manager.get_process(pid)

        if not process_info:
            await _reply(
                message,
                f"❌ **Process Not Found**\n\n"
                f"PID `{pid}` does not exist.\n\n"
                "Use `/status` to see active processes"
            )
            return

        if not process_info.log_path.exists():
            await _reply(message, "❌ **Log file not found**")
            return

        file_size = process_info.log_path.stat().st_size
        max_telegram_size = 50 * 1024 * 1024

        if file_size > max_telegram_size:
            await _reply(
                message,
                f"⚠️ **Log File Too Large**\n\n"
                f"File size: {file_size / 1024 / 1024:.2f} MB\n"
                f"Telegram limit: 50 MB\n\n"
                "Sending last 1000 lines instead..."
            )

            log_tail = process_info.get_log_tail(1000)
            temp_dir = Path(getattr(config, 'TEMP_DIR', '/tmp/botdeploy'))
            temp_log = temp_dir / f"log_tail_{pid}.txt"
            temp_log.write_text(log_tail)

            await _reply_document(
                message,
                temp_log,
                caption=f"📄 Last 1000 lines of log for PID {pid}"
            )

            temp_log.unlink()
        else:
            await _reply_document(
                message,
                process_info.log_path,
                caption=(
                    f"📄 Complete log for PID {pid}\n"
                    f"Size: {file_size / 1024:.2f} KB"
                )
            )

        logger.info(f"Log file sent for process {pid}")

    except ValueError:
        await _reply(message, "❌ PID must be a number")
    except Exception as e:
        logger.error(f"Error in log command: {e}", exc_info=True)
        await _reply(message, f"❌ An error occurred: `{str(e)}`")


@bot.message_handler(commands=["stop"])
async def stop_command(message: tele_types.Message):
    """Handle process stop command"""

    if not is_authorized(message):
        await _reply(message, "❌ You are not authorized to use this bot.")
        return

    parts = _parse_command(message)
    if len(parts) < 2:
        await _reply(
            message,
            "❌ **Invalid Command**\n\n"
            "Usage: `/stop <pid>`\n\n"
            "Example: `/stop 12345`"
        )
        return

    try:
        pid = int(parts[1])
        process_info = process_manager.get_process(pid)

        if not process_info:
            await _reply(
                message,
                f"❌ **Process Not Found**\n\n"
                f"PID `{pid}` does not exist.\n\n"
                "Use `/status` to see active processes"
            )
            return

        process_info._status = "stopped"
        process_manager.remove_process(pid)
        process_info.cleanup()

        await _reply(
            message,
            (
                f"✅ **Process Stopped**\n\n"
                f"**PID:** `{pid}`\n"
                f"**File:** `{process_info.file_path.name}`\n"
                f"**Runtime:** {process_info.runtime}\n"
                f"**Log:** `{process_info.log_path.name}`\n\n"
                "The log file has been preserved for review."
            ),
        )

        logger.info(
            f"Process {pid} stopped by user {message.from_user.id} "
            f"(@{message.from_user.username or 'N/A'})"
        )

    except ValueError:
        await _reply(message, "❌ PID must be a number")
    except Exception as e:
        logger.error(f"Error in stop command: {e}", exc_info=True)
        await _reply(message, f"❌ An error occurred: `{str(e)}`")
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
        "version": "2.1.0",
        "processes": stats,
        "features": {
            "dependency_management": True,
            "virtual_environments": getattr(config, 'USE_VENV', True),
            "auto_install": getattr(config, 'AUTO_INSTALL_DEPS', True)
        },
        "timestamp": datetime.now().isoformat()
    })


@web_app.route('/health')
def health():
    """Detailed health check"""
    stats = process_manager.get_stats()
    
    return jsonify({
        "status": "healthy",
        "version": "2.1.0",
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
            "max_restarts": info.max_restarts,
            "has_venv": info.venv_path is not None,
            "has_requirements": info.requirements_file is not None
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
    logger.info("Bot Deploy Manager v2.1.0 - Professional Edition")
    logger.info("Features: Dependency Management + Virtual Environments")
    logger.info("="*70)

    monitor_task = None
    try:
        # Start Flask in background thread
        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()
        logger.info("✓ Flask server started")
        
        # Start process monitor
        monitor_task = asyncio.create_task(process_manager.monitor_processes())
        logger.info("✓ Process monitor started")

        logger.info("="*70)
        logger.info("All systems operational - Bot is ready!")
        logger.info("="*70)

        # Start bot polling
        await bot.infinity_polling()
        
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Shutting down...")
        
        # Cleanup
        process_manager.cleanup_all()
        
        if monitor_task:
            monitor_task.cancel()
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
