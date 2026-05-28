"""
Cache manager for optimizing repeated operations
"""
import os
import hashlib
import json
import time
import threading
from functools import wraps
from typing import Any, Callable, Optional

class SimpleCache:
    """Thread-safe in-memory cache with TTL support"""

    def __init__(self, max_size: int = 100, default_ttl: int = 3600):
        self._cache: dict = {}
        self._access_times: dict = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    self._access_times[key] = time.time()
                    return value
                # Expired — remove
                del self._cache[key]
                self._access_times.pop(key, None)
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache with TTL"""
        with self._lock:
            if len(self._cache) >= self.max_size:
                if self._access_times:
                    oldest_key = min(self._access_times, key=self._access_times.get)
                    self._cache.pop(oldest_key, None)
                    self._access_times.pop(oldest_key, None)
            ttl = ttl or self.default_ttl
            expiry = time.time() + ttl
            self._cache[key] = (value, expiry)
            self._access_times[key] = time.time()

    def clear(self):
        """Clear all cache"""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()

    def remove(self, key: str):
        """Remove specific key from cache"""
        with self._lock:
            self._cache.pop(key, None)
            self._access_times.pop(key, None)


# Global cache instances
file_hash_cache = SimpleCache(max_size=200, default_ttl=7200)  # 2 hours
ocr_cache = SimpleCache(max_size=50, default_ttl=3600)  # 1 hour
preview_cache = SimpleCache(max_size=100, default_ttl=1800)  # 30 minutes


def get_file_hash(file_path: str) -> str:
    """Get MD5 hash of file with caching"""
    # Check cache first
    cache_key = f"hash_{file_path}_{os.path.getmtime(file_path)}"
    cached_hash = file_hash_cache.get(cache_key)
    if cached_hash:
        return cached_hash
    
    # Calculate hash
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    
    file_hash = hash_md5.hexdigest()
    file_hash_cache.set(cache_key, file_hash)
    return file_hash


def cache_result(cache_instance: SimpleCache, ttl: Optional[int] = None):
    """Decorator to cache function results"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = f"{func.__name__}_{str(args)}_{str(kwargs)}"
            
            # Check cache
            cached_result = cache_instance.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Cache result
            cache_instance.set(cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator
