"""
Shared pytest fixtures and configuration for the test suite.
"""

import pytest
from pathlib import Path
import tempfile


@pytest.fixture(scope="session")
def temp_data_root():
    """Create a temporary directory for all test data that persists across the session."""
    with tempfile.TemporaryDirectory(prefix="mlentory_test_") as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary directory for individual test data."""
    return tmp_path


@pytest.fixture(scope="session")
def test_config():
    """Test configuration dictionary."""
    return {
        "timeout": 60,  # seconds for network operations
        "max_retries": 3,
        "test_models": [
            "nineninesix/kani-tts-370m",
            "ibm-granite/granite-4.0-h-small"
        ]
    }

