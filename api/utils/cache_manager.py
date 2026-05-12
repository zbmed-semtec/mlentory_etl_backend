"""
Cache manager for entity data with TTL support and memory-efficient storage.

This module provides a centralized caching solution for entity details
to improve API response times and reduce database load.
"""

import time
import threading
from typing import Dict, Any, Optional
import json
import hashlib
from datetime import datetime, timedelta


class _CacheEntry:
    """Internal cache entry with timestamp for TTL support."""
    
    def __init__(self, data: Dict[str, Any], expiry_time: float):
        self.data = data
        self.expiry_time = expiry_time
        self.access_time = time.time()
    
    def is_expired(self) -> bool:
        return time.time() > self.expiry_time
    
    def touch(self):
        """Update access time for LRU tracking."""
        self.access_time = time.time()


class EntityCacheManager:
    """
    Thread-safe cache manager for entity data with configurable TTL and size limits.
    
    Features:
    - TTL-based expiration (default: 15 minutes)
    - LRU eviction when size limit is reached
    - Thread-safe operations
    - Cache statistics for monitoring
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 900):
        """
        Initialize the cache manager.
        
        Args:
            max_size: Maximum number of entities to cache
            ttl_seconds: Time-to-live for cached entries in seconds (default: 15 minutes)
        """
        self.cache: Dict[str, _CacheEntry] = {}
        self.max_size = max_size
        self.lock = threading.RLock()
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "evictions": 0
        }
        self.ttl_seconds = ttl_seconds
        
    def _generate_cache_key(self, entity_id: str) -> str:
        """
        Generate a consistent cache key for an entity ID.
        
        Args:
            entity_id: The entity identifier
            
        Returns:
            str: Hashed cache key
        """
        # Use hash to handle long URIs and ensure consistent key format
        return hashlib.sha256(entity_id.encode('utf-8')).hexdigest()[:16]
    
    def _cleanup_expired(self):
        """Remove expired entries from cache."""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.cache.items() 
            if entry.is_expired()
        ]
        for key in expired_keys:
            del self.cache[key]
    
    def _evict_lru_if_needed(self):
        """Evict least recently used entry if cache is at capacity."""
        if len(self.cache) >= self.max_size:
            # Find LRU entry
            lru_key = min(self.cache.keys(), key=lambda k: self.cache[k].access_time)
            del self.cache[lru_key]
            self.stats["evictions"] += 1
    
    def get(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve entity data from cache.
        
        Args:
            entity_id: The entity identifier to lookup
            
        Returns:
            Dict containing entity data if found, None otherwise
        """
        if not entity_id or not entity_id.strip():
            return None
            
        cache_key = self._generate_cache_key(entity_id.strip())
        
        with self.lock:
            # Clean up expired entries
            self._cleanup_expired()
            
            entry = self.cache.get(cache_key)
            if entry and not entry.is_expired():
                entry.touch()  # Update access time for LRU
                self.stats["hits"] += 1
                return entry.data
            elif entry:
                # Entry exists but is expired
                del self.cache[cache_key]
                
            self.stats["misses"] += 1
            return None
    
    def set(self, entity_id: str, entity_data: Dict[str, Any]) -> None:
        """
        Store entity data in cache.
        
        Args:
            entity_id: The entity identifier
            entity_data: The entity data to cache
        """
        if not entity_id or not entity_id.strip():
            return
            
        cache_key = self._generate_cache_key(entity_id.strip())
        
        with self.lock:
            # Clean up expired entries first
            self._cleanup_expired()
            
            # Evict LRU if needed (only if not updating existing entry)
            if cache_key not in self.cache:
                self._evict_lru_if_needed()
            
            # Create new cache entry with expiry time
            expiry_time = time.time() + self.ttl_seconds
            self.cache[cache_key] = _CacheEntry(entity_data, expiry_time)
            self.stats["sets"] += 1
    
    def invalidate(self, entity_id: str) -> bool:
        """
        Remove specific entity from cache.
        
        Args:
            entity_id: The entity identifier to remove
            
        Returns:
            bool: True if entity was removed, False if not found
        """
        if not entity_id or not entity_id.strip():
            return False
            
        cache_key = self._generate_cache_key(entity_id.strip())
        
        with self.lock:
            if cache_key in self.cache:
                del self.cache[cache_key]
                return True
            return False
    
    def clear(self) -> None:
        """Clear all cached entries."""
        with self.lock:
            self.cache.clear()
            # Reset stats except for historical counters
            self.stats["evictions"] = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dict containing cache performance metrics
        """
        with self.lock:
            # Clean up expired entries for accurate size
            self._cleanup_expired()
            
            hit_rate = (
                self.stats["hits"] / (self.stats["hits"] + self.stats["misses"])
                if (self.stats["hits"] + self.stats["misses"]) > 0
                else 0.0
            )
            
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "hits": self.stats["hits"],
                "misses": self.stats["misses"],
                "sets": self.stats["sets"],
                "evictions": self.stats["evictions"],
                "hit_rate": round(hit_rate, 3),
                "memory_efficiency": round(len(self.cache) / self.max_size, 3) if self.max_size > 0 else 0.0
            }
    
    def get_cache_info(self) -> str:
        """
        Get human-readable cache information.
        
        Returns:
            str: Formatted cache statistics
        """
        stats = self.get_stats()
        return (
            f"Cache Stats: {stats['size']}/{stats['max_size']} entries, "
            f"Hit Rate: {stats['hit_rate']:.1%}, "
            f"TTL: {stats['ttl_seconds']}s"
        )


# Global cache instance
_entity_cache_manager = None


def get_entity_cache_manager() -> EntityCacheManager:
    """
    Get the global entity cache manager instance.
    
    Returns:
        EntityCacheManager: The singleton cache manager
    """
    global _entity_cache_manager
    if _entity_cache_manager is None:
        # Initialize with reasonable defaults for production
        # 1000 entities max, 15-minute TTL
        _entity_cache_manager = EntityCacheManager(max_size=50000, ttl_seconds=1500)
    return _entity_cache_manager


def configure_entity_cache(max_size: int = None, ttl_seconds: int = None) -> EntityCacheManager:
    """
    Configure the global entity cache manager.
    
    Args:
        max_size: Maximum number of entities to cache
        ttl_seconds: Time-to-live for cached entries in seconds
        
    Returns:
        EntityCacheManager: The configured cache manager
    """
    global _entity_cache_manager
    
    # Use existing values if not provided
    if _entity_cache_manager is not None:
        current_max_size = _entity_cache_manager.cache.maxsize
        current_ttl = _entity_cache_manager.ttl_seconds
        max_size = max_size if max_size is not None else current_max_size
        ttl_seconds = ttl_seconds if ttl_seconds is not None else current_ttl
    else:
        max_size = max_size if max_size is not None else 1000
        ttl_seconds = ttl_seconds if ttl_seconds is not None else 900
    
    _entity_cache_manager = EntityCacheManager(max_size=max_size, ttl_seconds=ttl_seconds)
    return _entity_cache_manager 