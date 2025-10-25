"""Configuration template for Amazon Automator."""

import os
from pathlib import Path


class Config:
    """Configuration management."""
    
    # Browser settings
    HEADFUL = os.getenv('AMAZON_AUTOMATOR_HEADFUL', 'false').lower() == 'true'
    DRY_RUN = os.getenv('AMAZON_AUTOMATOR_DRY_RUN', 'false').lower() == 'true'
    HEADLESS = not HEADFUL
    
    # Network settings
    PROXY = os.getenv('AMAZON_AUTOMATOR_PROXY', None)  # format: http://user:pass@host:port
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    ]
    
    # Timing settings
    THROTTLE = float(os.getenv('AMAZON_AUTOMATOR_THROTTLE', '2.0'))
    TIMEOUT = int(os.getenv('AMAZON_AUTOMATOR_TIMEOUT', '30000'))
    
    # Session storage
    SESSION_STORE_PATH = os.getenv(
        'AMAZON_AUTOMATOR_SESSION_PATH',
        str(Path.home() / '.amazon_automator_session.json')
    )
    
    # Logging
    LOG_LEVEL = os.getenv('AMAZON_AUTOMATOR_LOG_LEVEL', 'INFO')
    
    @classmethod
    def to_dict(cls):
        """Return config as dict."""
        return {
            'headful': cls.HEADFUL,
            'dry_run': cls.DRY_RUN,
            'proxy': cls.PROXY,
            'throttle': cls.THROTTLE,
            'timeout': cls.TIMEOUT,
            'session_store_path': cls.SESSION_STORE_PATH,
            'log_level': cls.LOG_LEVEL,
        }
