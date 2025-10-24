"""Environment and secrets loading."""

import os
from pathlib import Path

from dotenv import load_dotenv


def load_env() -> None:
    """Load environment variables from .env file."""
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file, override=False)


# Load on import
load_env()
