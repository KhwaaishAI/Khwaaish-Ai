# requirements.txt

# amazon_automator/run_automator.py
"""
Entry point for Amazon Checkout Automator.

Example usage:
    python run_automator.py search --query "wireless mouse"
    python run_automator.py dry-run --query "keyboard" --headful
    python run_automator.py test-session
"""

import sys
from pathlib import Path

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from amazon_automator.cli import main

if __name__ == '__main__':
    main()





# tests/test_automator.py


# amazon_automator/spec_finder.py


# amazon_automator/test_dry_run.py
