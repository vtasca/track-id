import pytest
import tempfile
import os


@pytest.fixture
def sample_mp3_path():
    """Create a temporary MP3 file path for testing"""
    # This is just a path - actual file creation would be done in specific tests
    return "test_sample.mp3"


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def mock_mp3_file(temp_dir):
    """Create a mock MP3 file in temporary directory"""
    mp3_path = os.path.join(temp_dir, "test.mp3")
    # Create an empty file with .mp3 extension
    with open(mp3_path, 'w') as f:
        f.write("mock mp3 content")
    return mp3_path


@pytest.fixture
def sample_id3_tags():
    """Sample ID3 tags for testing"""
    return {
        'TIT2': 'Test Title',
        'TPE1': 'Test Artist',
        'TALB': 'Test Album',
        'TRCK': '1',
        'TDRC': '2023'
    } 