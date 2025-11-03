import logging
import sys
import asyncio
from typing import Optional

# --- WebSocket Log Handler Class ---
# We define this here so it's self-contained with the logger setup.
class WebSocketLogHandler(logging.Handler):
    """
    A custom logging handler that puts formatted log records into an asyncio Queue.
    This handler is thread-safe (and asyncio-safe) because logging.Handler
    has its own lock, and queue.put_nowait() is safe to call
    from a synchronous context.
    """
    def __init__(self, queue: asyncio.Queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        """
        This method is called by the logging framework for each log record.
        """
        log_entry = self.format(record)
        try:
            # Use put_nowait for a non-blocking put from a sync context
            self.queue.put_nowait(log_entry)
        except asyncio.QueueFull:
            # Handle queue full (e.g., drop message, log to stderr)
            print("Log queue is full, dropping message.", file=sys.stderr)
        except Exception as e:
            # Handle other potential errors, e.g., queue closed
            print(f"Error in WebSocketLogHandler: {e}", file=sys.stderr)

# --- Your setup_logger function, MODIFIED ---
def setup_logger(name: str, queue: Optional[asyncio.Queue] = None) -> logging.Logger:
    """
    Setup comprehensive logging configuration.
    
    If an asyncio.Queue is provided, it will also add a WebSocketLogHandler
    to forward logs to the WebSocket server.
    """
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # --- IMPORTANT ---
    # Clear handlers *only if you are sure* you want to reconfigure
    # this logger from scratch every time. If multiple parts of your
    # app call setup_logger("amazon"), this will remove old handlers.
    logger.handlers.clear()
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    file_handler = logging.FileHandler(f'{name}.log', encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # === NEW: Conditionally add the WebSocket Handler ===
    if queue:
        ws_handler = WebSocketLogHandler(queue)
        ws_handler.setFormatter(formatter)
        logger.addHandler(ws_handler)
        logger.info(f"WebSocketLogHandler added to logger: {name}")
    # ===================================================
    
    return logger
