from __future__ import annotations
import logging
from collections import deque
from datetime import datetime
from typing import List, Dict

_buffer = deque(maxlen=5000)
class _MemoryHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        _buffer.append({
            "time": datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S"),
            "level": record.levelname, "name": record.name, "message": record.getMessage(),
        })
def get_logger() -> logging.Logger:
    logger = logging.getLogger("app")
    if not logger.handlers:
        logger.setLevel(logging.INFO); logger.addHandler(_MemoryHandler())
    return logger
def get_buffer() -> List[Dict]: return list(_buffer)
def clear_buffer() -> None: _buffer.clear()
