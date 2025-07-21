import pytest
from track_id import ID3_TAG_NAMES


class TestID3Tags:
    """Test cases for ID3 tag mapping functionality"""
    
    def test_id3_tag_names_is_dict(self):
        """Test that ID3_TAG_NAMES is a dictionary"""
        assert isinstance(ID3_TAG_NAMES, dict)
    
    def test_id3_tag_names_not_empty(self):
        """Test that ID3_TAG_NAMES is not empty"""
        assert len(ID3_TAG_NAMES) > 0
    
    def test_common_tags_exist(self):
        """Test that common ID3 tags are present"""
        common_tags = ['TIT2', 'TPE1', 'TALB', 'TRCK', 'TDRC']
        for tag in common_tags:
            assert tag in ID3_TAG_NAMES
    
    def test_tag_names_are_strings(self):
        """Test that all tag names are strings"""
        for tag_id, tag_name in ID3_TAG_NAMES.items():
            assert isinstance(tag_id, str)
            assert isinstance(tag_name, str)
    
    def test_specific_tag_mappings(self):
        """Test specific tag ID to name mappings"""
        expected_mappings = {
            'TIT2': 'Title',
            'TPE1': 'Artist',
            'TALB': 'Album',
            'TRCK': 'Track Number',
            'TDRC': 'Year'
        }
        
        for tag_id, expected_name in expected_mappings.items():
            assert ID3_TAG_NAMES[tag_id] == expected_name
    
    def test_no_duplicate_tag_ids(self):
        """Test that there are no duplicate tag IDs"""
        tag_ids = list(ID3_TAG_NAMES.keys())
        assert len(tag_ids) == len(set(tag_ids))