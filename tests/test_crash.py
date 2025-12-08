import os
import sys
import shutil
import tempfile
import unittest
import logging
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

# Create a mock config module
mock_config = MagicMock()
mock_config.BOT_TOKEN = "123:test-token"
mock_config.API_ID = "test-api-id"
mock_config.ALLOWED_USERS = [12345]
mock_config.LOG_DIR = "./logs_test"
mock_config.MAX_LOG_SIZE = 10 * 1024 * 1024
mock_config.LOG_BACKUP_COUNT = 5
mock_config.LOCK_FILE = "/tmp/botdeploy_crash_test.lock"
mock_config.TEMP_DIR = "/tmp/botdeploy_crash_test"
mock_config.VENV_DIR = "./venvs_crash_test"
mock_config.USE_VENV = True
mock_config.AUTO_INSTALL_DEPS = False

# Mock modules to avoid side effects during import
sys.modules['telebot'] = MagicMock()
sys.modules['telebot.async_telebot'] = MagicMock()
sys.modules['flask'] = MagicMock()
sys.modules['requests'] = MagicMock()

# Patch config module
with patch.dict(sys.modules, {'config': mock_config}):
    # We need to ensure logging doesn't interfere
    with patch('logging.handlers.RotatingFileHandler') as mock_rfh:
        mock_rfh.return_value.level = logging.NOTSET
        from run import ProcessManager

class TestCrash(unittest.TestCase):
    def setUp(self):
        self.manager = ProcessManager()
        self.test_dir = tempfile.mkdtemp()
        self.venv_dir = Path(self.test_dir) / "venvs"
        self.venv_dir.mkdir()

        # Setup mock venv
        self.venv_name = "test_venv"
        self.venv_path = self.venv_dir / self.venv_name
        self.venv_bin = self.venv_path / "bin"
        self.venv_bin.mkdir(parents=True)

        # Create mock python executable
        self.python_exe = self.venv_bin / "python"
        with open(self.python_exe, "w") as f:
            f.write("#!/bin/sh\necho 'Python executed'\n")
        os.chmod(self.python_exe, 0o755)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_run_script_relative_path_crash(self):
        """
        Test that run_script correctly handles relative venv paths
        and doesn't crash with FileNotFoundError when changing cwd.
        """
        script_path = Path(self.test_dir) / "script.py"
        script_path.touch()
        log_path = Path(self.test_dir) / "script.log"

        # Calculate relative path to venv from current working directory
        # We need to be careful: the bug happens when venv_path passed to run_script is relative.
        # And run_script changes CWD to script_path.parent (which is self.test_dir).

        # So if we pass "venvs/test_venv", it resolves relative to CWD (root).
        # But inside Popen(cwd=script_path.parent), it would resolve relative to script_path.parent if not absolute.

        # We need to simulate the condition where venv_path is relative to the *bot's* CWD.
        # But script is in *TEMP_DIR* (self.test_dir).

        # Let's say bot CWD is `os.getcwd()`.
        # We create a venv in `os.getcwd()/venvs_crash_test` (matching mock_config).

        # Actually, let's use the layout from my reproduction script which worked.
        # Create venv in current directory.

        cwd = Path.cwd()
        local_venv_dir = cwd / "venvs_crash_test_temp"
        if local_venv_dir.exists():
            shutil.rmtree(local_venv_dir)

        local_venv_bin = local_venv_dir / "bin"
        local_venv_bin.mkdir(parents=True)
        local_python = local_venv_bin / "python"
        with open(local_python, "w") as f:
            f.write("#!/bin/sh\necho 'Python executed'\n")
        os.chmod(local_python, 0o755)

        try:
            relative_venv_path = Path("venvs_crash_test_temp")

            # The script is in self.test_dir (temp dir)
            # The venv is in ./venvs_crash_test_temp

            # This triggers the bug:
            # Popen cwd = self.test_dir
            # executable = ./venvs_crash_test_temp/bin/python (relative)
            # Popen looks for self.test_dir/venvs_crash_test_temp/bin/python -> Not found!

            process = self.manager.run_script(
                script_path=script_path,
                log_path=log_path,
                venv_path=relative_venv_path,
                chat_id=123
            )

            self.assertIsNotNone(process, "run_script returned None, meaning it failed to start")

            if process:
                process.wait()
                self.assertEqual(process.returncode, 0)

        finally:
            if local_venv_dir.exists():
                shutil.rmtree(local_venv_dir)

if __name__ == '__main__':
    unittest.main()
