import os
import json
import pickle
import logging
from datetime import datetime
from collections import defaultdict, Counter
import tiktoken
from typing import List, Tuple, Optional, Dict, Any
import string
import re

from discord_agent.bot_config import *
from discord_agent.cache_manager import CacheManager

# Memory

class UserMemoryIndex:
    """A class for indexing and searching user memories with efficient caching.
    
    This class provides functionality to store, index, and search through user memories
    using an inverted index approach. It handles caching of memories to disk and 
    supports per-user memory isolation.

    Attributes:
        cache_manager (CacheManager): Manager for handling cache operations
        cache_dir (str): Directory path for storing cache files
        max_tokens (int): Maximum number of tokens allowed in search results
        context_chunks (int): Number of context chunks to maintain
        tokenizer: Tokenizer for counting tokens in text
        inverted_index (defaultdict): Inverted index mapping words to memory IDs
        memories (list): List of all memory texts
        stopwords (set): Set of common words to ignore during indexing
        user_memories (defaultdict): Mapping of user IDs to their memory IDs
    """

    def __init__(self, cache_type, max_tokens=MAX_TOKENS, context_chunks=CONTEXT_CHUNKS):
        """Initialize the UserMemoryIndex.

        Args:
            cache_type (str): Type of cache to use (e.g., 'user_memory_index')
            max_tokens (int, optional): Maximum tokens in search results. Defaults to MAX_TOKENS.
            context_chunks (int, optional): Number of context chunks. Defaults to CONTEXT_CHUNKS.
        """
        self.cache_manager = CacheManager('discord_bot')
        self.cache_dir = self.cache_manager.get_cache_dir(cache_type)
        self.max_tokens = max_tokens
        self.context_chunks = context_chunks
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.inverted_index = defaultdict(list)
        self.memories = []
        self.stopwords = set(['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'])
        self.user_memories = defaultdict(list)
        self.load_cache()

    def clean_text(self, text):
        """Clean and normalize text for indexing/searching.

        Args:
            text (str): Text to clean

        Returns:
            str: Cleaned text with punctuation removed, numbers removed, and stopwords filtered
        """
        text = text.lower()
        text = text.translate(str.maketrans('', '', string.punctuation))
        text = re.sub(r'\d+', '', text)
        words = text.split()
        words = [word for word in words if word not in self.stopwords]
        return ' '.join(words)

    def add_memory(self, user_id, memory_text):
        """Add a new memory for a user.

        Args:
            user_id (str): ID of the user this memory belongs to
            memory_text (str): Text content of the memory
        """
        memory_id = len(self.memories)
        self.memories.append(memory_text)
        self.user_memories[user_id].append(memory_id)
        
        cleaned_text = self.clean_text(memory_text)
        words = cleaned_text.split()
        for word in words:
            self.inverted_index[word].append(memory_id)
        
        logging.info(f"Added new memory for user {user_id}: {memory_text[:100]}...")
        self.save_cache()

    def clear_user_memories(self, user_id):
        """Clear all memories for a specific user.

        Args:
            user_id (str): ID of user whose memories should be cleared
        """
        if user_id in self.user_memories:
            memory_ids_to_remove = self.user_memories[user_id]
            for memory_id in memory_ids_to_remove:
                self.memories[memory_id] = None  # Mark as removed
            
            # Update inverted index
            for word, ids in self.inverted_index.items():
                self.inverted_index[word] = [id for id in ids if id not in memory_ids_to_remove]
            
            del self.user_memories[user_id]
            logging.info(f"Cleared memories for user {user_id}")
            self.save_cache()

    def search(self, query, k=5, user_id=None, similarity_threshold=0.85):
        """Search for relevant memories matching a query, removing duplicates.

        Args:
            query (str): Search query text
            k (int, optional): Maximum number of results to return. Defaults to 5.
            user_id (str, optional): If provided, only search this user's memories.
            similarity_threshold (float, optional): Threshold for considering memories as duplicates. 
                Higher values mean more strict duplicate detection. Defaults to 0.85.

        Returns:
            list: List of tuples containing (memory_text, relevance_score)
        """
        cleaned_query = self.clean_text(query)
        query_words = cleaned_query.split()
        memory_scores = Counter()

        # If user_id is provided, only search that user's memories
        if user_id:
            relevant_memory_ids = self.user_memories.get(user_id, [])
        else:
            relevant_memory_ids = range(len(self.memories))

        # Score memories based on word matches
        for word in query_words:
            for memory_id in self.inverted_index.get(word, []):
                if memory_id in relevant_memory_ids:
                    memory_scores[memory_id] += 1
        
        # Normalize scores by memory length
        for memory_id, score in memory_scores.items():
            memory_scores[memory_id] = score / len(self.clean_text(self.memories[memory_id]).split())
        
        sorted_memories = sorted(memory_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Deduplication process
        results = []
        total_tokens = 0
        seen_content = set()  # Track unique content fingerprints
        
        for memory_id, score in sorted_memories:
            memory = self.memories[memory_id]
            memory_tokens = self.count_tokens(memory)

            if total_tokens + memory_tokens > self.max_tokens:
                break

            # Create a content fingerprint by cleaning and normalizing the text
            cleaned_memory = self.clean_text(memory)
            
            # Check for similar content using n-gram comparison
            is_duplicate = False
            for seen in seen_content:
                similarity = self._calculate_similarity(cleaned_memory, seen)
                if similarity > similarity_threshold:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                results.append((memory, score))
                seen_content.add(cleaned_memory)
                total_tokens += memory_tokens
                
                if len(results) >= k:
                    break

        logging.info(f"Found {len(results)} unique memories for query: {query[:100]}...")
        return results

    def _calculate_similarity(self, text1, text2):
        """Calculate similarity between two texts using character n-grams.
        
        Args:
            text1 (str): First text to compare
            text2 (str): Second text to compare
            
        Returns:
            float: Similarity score between 0 and 1
        """
        # Use 3-character n-grams for comparison
        def get_ngrams(text, n=3):
            return set(text[i:i+n] for i in range(len(text)-n+1))
        
        # Get n-grams for both texts
        ngrams1 = get_ngrams(text1)
        ngrams2 = get_ngrams(text2)
        
        # Calculate Jaccard similarity
        intersection = len(ngrams1.intersection(ngrams2))
        union = len(ngrams1.union(ngrams2))
        
        return intersection / union if union > 0 else 0
    def count_tokens(self, text):
        """Count the number of tokens in text.

        Args:
            text (str): Text to count tokens in

        Returns:
            int: Number of tokens
        """
        return len(self.tokenizer.encode(text))
    
    def save_cache(self):
        """Save the current state to cache file."""
        cache_data = {
            'inverted_index': self.inverted_index,
            'memories': self.memories,
            'user_memories': self.user_memories
        }
        with open(os.path.join(self.cache_dir, 'memory_cache.pkl'), 'wb') as f:
            pickle.dump(cache_data, f)
        logging.info("Memory cache saved successfully.")

    def load_cache(self):
        """Load the state from cache file if it exists.

        Returns:
            bool: True if cache was loaded successfully, False otherwise
        """
        cache_file = os.path.join(self.cache_dir, 'memory_cache.pkl')
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)
            self.inverted_index = cache_data.get('inverted_index', defaultdict(list))
            self.memories = cache_data.get('memories', [])
            self.user_memories = cache_data.get('user_memories', defaultdict(list))
            logging.info("Memory cache loaded successfully.")
            return True
        return False