"""
File grouping algorithms for Comics and Audiobooks
This module contains the logic to group files into appropriate entities for Phase 1 implementation
"""

import os
import re
from typing import Dict, List
import logging

logger = logging.getLogger("books.scanner")


class ComicFileGrouper:
    """Groups comic files by series/title"""

    def __init__(self):
        # Common patterns for comic file naming
        self.comic_patterns = [
            # "Batman #001.cbr" -> "Batman"
            r'^([^#]+?)(?:\s*#\s*\d+)',
            # "Spider-Man Vol 1 #001.cbz" -> "Spider-Man Vol 1"
            r'^(.+?)(?:\s+Vol\.?\s+\d+)?\s*#\s*\d+',
            # "Amazing Spider-Man (2018) #001.cbr" -> "Amazing Spider-Man (2018)"
            r'^(.+?)(?:\s*\(\d{4}\))?\s*#?\s*\d+',
            # "Batman - Detective Comics 001.cbr" -> "Batman - Detective Comics"
            r'^(.+?)\s+\d{3,4}(?:\.\w+)?$',
            # Folder-based: "/comics/Batman/Batman 001.cbr" -> "Batman"
            r'([^/\\]+)(?:/|\\)[^/\\]*\d+',
        ]

    def group_files(self, file_paths: List[str]) -> Dict[str, List[str]]:
        """
        Group comic files by series name
        Returns: {series_name: [file_paths]}
        """
        groups = {}

        for file_path in file_paths:
            series_name = self.extract_series_name(file_path)

            if series_name not in groups:
                groups[series_name] = []
            groups[series_name].append(file_path)

        return groups

    def extract_series_name(self, file_path: str) -> str:
        """Extract comic series name from file path"""
        filename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(filename)[0]

        # Try each pattern
        for pattern in self.comic_patterns:
            match = re.search(pattern, name_without_ext, re.IGNORECASE)
            if match:
                series_name = match.group(1).strip()
                if series_name:
                    return self.clean_series_name(series_name)

        # Fallback: use directory name if file doesn't match patterns
        parent_dir = os.path.basename(os.path.dirname(file_path))
        if parent_dir and parent_dir.lower() not in ['comics', 'comic']:
            return self.clean_series_name(parent_dir)

        # Last resort: use filename without number
        cleaned = re.sub(r'\s*\d{2,4}\s*$', '', name_without_ext)
        return self.clean_series_name(cleaned) if cleaned else name_without_ext

    def extract_issue_info(self, file_path: str, series_name: str) -> Dict[str, any]:
        """Extract issue number and other info from filename"""
        filename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(filename)[0]

        info = {
            'issue_number': None,
            'volume': 1,
            'year': None
        }

        # Look for issue number patterns
        issue_patterns = [
            r'#\s*(\d+(?:\.\d+)?)',  # #001 or #1.5
            r'(?:Issue|Iss)\s*(\d+(?:\.\d+)?)',  # Issue 1
            r'\b(\d{2,3})\s*(?:\.\w+)?$',  # 001.cbr (at end)
            r'(\d+(?:\.\d+)?)\s*(?:\.\w+)?$',  # 1.cbr (at end)
        ]

        for pattern in issue_patterns:
            match = re.search(pattern, name_without_ext, re.IGNORECASE)
            if match:
                info['issue_number'] = match.group(1)
                break

        # Look for volume
        vol_match = re.search(r'Vol\.?\s*(\d+)', name_without_ext, re.IGNORECASE)
        if vol_match:
            info['volume'] = int(vol_match.group(1))

        # Look for year
        year_match = re.search(r'\((\d{4})\)', name_without_ext)
        if year_match:
            info['year'] = int(year_match.group(1))

        return info

    def clean_series_name(self, name: str) -> str:
        """Clean and normalize series name"""
        # Remove common prefixes/suffixes
        name = re.sub(r'^(The|A|An)\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+', ' ', name)  # Normalize whitespace
        name = name.strip(' -_')
        return name.title()


class AudiobookFileGrouper:
    """Groups audio files by audiobook"""

    def __init__(self):
        pass

    def group_files(self, file_paths: List[str]) -> Dict[str, List[str]]:
        """
        Group audio files by audiobook
        Returns: {audiobook_key: [file_paths]}
        """
        groups = {}

        for file_path in file_paths:
            book_key = self.extract_audiobook_key(file_path)

            if book_key not in groups:
                groups[book_key] = []
            groups[book_key].append(file_path)

        # Filter out single files that might be standalone
        # Only group if multiple files share the same key
        filtered_groups = {}
        for key, files in groups.items():
            if len(files) > 1:
                filtered_groups[key] = files
            else:
                # Single file - create unique key
                unique_key = self.extract_title_from_single_file(files[0])
                filtered_groups[unique_key] = files

        return filtered_groups

    def extract_audiobook_key(self, file_path: str) -> str:
        """Extract audiobook identifier from file path"""

        # Strategy 1: Use parent directory name
        parent_dir = os.path.basename(os.path.dirname(file_path))
        if parent_dir and parent_dir.lower() not in ['audiobooks', 'audio']:
            return self.clean_audiobook_name(parent_dir)

        # Strategy 2: Extract common prefix from filename
        filename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(filename)[0]

        # Remove common patterns like "Chapter 01", "CD1", "Disc 1", etc.
        patterns_to_remove = [
            r'\s*-?\s*(?:Chapter|Ch|Part|Pt)\s*\d+.*$',
            r'\s*-?\s*(?:CD|Disc|Disk)\s*\d+.*$',
            r'\s*-?\s*\d{2,3}(?:\s*-.*)?$',  # " - 01" or " 01"
            r'\s*\(\d+\).*$',  # (1) at end
        ]

        cleaned_name = name_without_ext
        for pattern in patterns_to_remove:
            cleaned_name = re.sub(pattern, '', cleaned_name, flags=re.IGNORECASE)

        return self.clean_audiobook_name(cleaned_name)

    def extract_title_from_single_file(self, file_path: str) -> str:
        """Extract title from single audiobook file"""
        filename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(filename)[0]

        # For single files, use the full filename as title
        return self.clean_audiobook_name(name_without_ext)

    def extract_file_info(self, file_path: str, audiobook_key: str) -> Dict[str, any]:
        """Extract chapter/track info from filename"""
        filename = os.path.basename(file_path)
        name_without_ext = os.path.splitext(filename)[0]

        info = {
            'chapter_number': None,
            'track_number': None,
            'chapter_title': None,
            'disc_number': None
        }

        # Look for chapter numbers
        chapter_patterns = [
            r'(?:Chapter|Ch)\s*(\d+)',
            r'(?:Part|Pt)\s*(\d+)',
            r'\b(\d{2,3})\b',  # Any 2-3 digit number
        ]

        for pattern in chapter_patterns:
            match = re.search(pattern, name_without_ext, re.IGNORECASE)
            if match:
                info['chapter_number'] = int(match.group(1))
                info['track_number'] = int(match.group(1))
                break

        # Look for disc number
        disc_match = re.search(r'(?:CD|Disc|Disk)\s*(\d+)', name_without_ext, re.IGNORECASE)
        if disc_match:
            info['disc_number'] = int(disc_match.group(1))

        # Extract chapter title (text after number)
        title_match = re.search(r'(?:Chapter|Ch|Part|Pt)\s*\d+\s*[-:]\s*(.+)', name_without_ext, re.IGNORECASE)
        if title_match:
            info['chapter_title'] = title_match.group(1).strip()

        return info

    def clean_audiobook_name(self, name: str) -> str:
        """Clean and normalize audiobook name"""
        # Remove common patterns
        name = re.sub(r'\s*-\s*Unabridged\s*', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*\[.*?\]\s*', '', name)  # Remove [brackets]
        name = re.sub(r'\s+', ' ', name)  # Normalize whitespace
        name = name.strip(' -_')
        return name


def group_files_by_content_type(file_paths: List[str], content_type: str) -> Dict[str, List[str]]:
    """
    Main function to group files based on content type
    """
    if content_type == 'comics':
        grouper = ComicFileGrouper()
        return grouper.group_files(file_paths)
    elif content_type == 'audiobooks':
        grouper = AudiobookFileGrouper()
        return grouper.group_files(file_paths)
    else:
        # For ebooks, each file is its own group (existing behavior)
        return {os.path.basename(path): [path] for path in file_paths}


# Test functions for development
def test_comic_grouping():
    """Test comic grouping with sample files"""
    comic_files = [
        "/comics/Batman #001.cbr",
        "/comics/Batman #002.cbr",
        "/comics/Batman Annual #1.cbr",
        "/comics/Spider-Man Vol 1 #001.cbz",
        "/comics/Spider-Man Vol 1 #002.cbz",
        "/comics/Amazing Spider-Man (2018) #001.cbr"
    ]

    comic_grouper = ComicFileGrouper()
    comic_groups = comic_grouper.group_files(comic_files)
    print("Comic Groups:")
    for series, files in comic_groups.items():
        print(f"  {series}: {files}")
    return comic_groups


def test_audiobook_grouping():
    """Test audiobook grouping with sample files"""
    audiobook_files = [
        "/audiobooks/Book Title/Chapter 01.mp3",
        "/audiobooks/Book Title/Chapter 02.mp3",
        "/audiobooks/Book Title/Chapter 03.mp3",
        "/audiobooks/Another Book - CD1.m4a",
        "/audiobooks/Another Book - CD2.m4a",
        "/audiobooks/Single File Book.mp3"
    ]

    audiobook_grouper = AudiobookFileGrouper()
    audiobook_groups = audiobook_grouper.group_files(audiobook_files)
    print("\nAudiobook Groups:")
    for book, files in audiobook_groups.items():
        print(f"  {book}: {files}")
    return audiobook_groups


if __name__ == "__main__":
    test_comic_grouping()
    test_audiobook_grouping()
