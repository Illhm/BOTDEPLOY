import io
import logging
from pathlib import Path

import run


def test_release_instance_lock_skips_closed_handlers(tmp_path, capsys):
    """Ensure cleanup does not raise logging errors when a handler's stream is closed."""

    lock_path = tmp_path / "bot.lock"
    lock_path.write_text("123")
    run._INSTANCE_LOCK = Path(lock_path)

    closed_stream = io.StringIO()
    closed_stream.close()
    handler = logging.StreamHandler(closed_stream)
    run.logger.addHandler(handler)

    try:
        run.release_instance_lock()
    finally:
        run.logger.removeHandler(handler)

    captured = capsys.readouterr()
    assert "Logging error" not in captured.err
    assert not lock_path.exists()
