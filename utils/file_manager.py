"""
Optimized file management with immediate cleanup and streaming support
"""
import os
import time
from contextlib import contextmanager
from typing import List, Optional
import threading
from utils.logger import get_logger

_log = get_logger(__name__)

class FileManager:
    """Manages temporary files with automatic cleanup"""
    
    def __init__(self, upload_folder: str):
        self.upload_folder = upload_folder
        self.tracked_files = {}  # {file_path: creation_time}
        self.lock = threading.Lock()
    
    def track_file(self, file_path: str):
        """Track a file for cleanup"""
        with self.lock:
            self.tracked_files[file_path] = time.time()
    
    def cleanup_file(self, file_path: str):
        """Immediately cleanup a specific file"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                _log.debug("Cleaned up: %s", file_path)

            with self.lock:
                if file_path in self.tracked_files:
                    del self.tracked_files[file_path]
        except Exception as e:
            _log.warning("Error cleaning up %s: %s", file_path, e)
    
    def cleanup_files(self, file_paths: List[str]):
        """Cleanup multiple files"""
        for file_path in file_paths:
            self.cleanup_file(file_path)
    
    def cleanup_old_files(self, max_age: int = 1800):
        """Cleanup files older than max_age seconds.
        
        Scans both the tracked_files dict AND the actual upload folder
        on disk, so files saved without track_file() are also cleaned up.
        """
        now = time.time()
        files_to_remove = []

        # 1. Check tracked files (in-memory)
        with self.lock:
            for file_path, creation_time in list(self.tracked_files.items()):
                if now - creation_time > max_age:
                    files_to_remove.append(file_path)

        # 2. Scan upload folder on disk for any untracked old files
        if os.path.isdir(self.upload_folder):
            for fname in os.listdir(self.upload_folder):
                fpath = os.path.join(self.upload_folder, fname)
                if not os.path.isfile(fpath):
                    continue
                try:
                    file_age = now - os.path.getmtime(fpath)
                    if file_age > max_age and fpath not in files_to_remove:
                        files_to_remove.append(fpath)
                except OSError:
                    pass

        for file_path in files_to_remove:
            self.cleanup_file(file_path)
    
    def get_temp_path(self, filename: str) -> str:
        """Generate a unique temporary file path"""
        timestamp = int(time.time() * 1000)  # milliseconds for uniqueness
        return os.path.join(self.upload_folder, f"{timestamp}_{filename}")
    
    @contextmanager
    def temp_file(self, filename: str):
        """Context manager for temporary files with automatic cleanup"""
        file_path = self.get_temp_path(filename)
        self.track_file(file_path)
        
        try:
            yield file_path
        finally:
            # Cleanup after use
            self.cleanup_file(file_path)


# Global file manager instance
file_manager: Optional[FileManager] = None


def initialize_file_manager(upload_folder: str):
    """Initialize the global file manager"""
    global file_manager
    file_manager = FileManager(upload_folder)
    return file_manager


def get_file_manager() -> FileManager:
    """Get the global file manager instance"""
    if file_manager is None:
        raise RuntimeError("File manager not initialized")
    return file_manager
