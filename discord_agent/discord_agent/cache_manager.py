import os
import json
from collections import deque
import tempfile
import shutil
import logging
from datetime import datetime, timedelta
import uuid

class CacheManager:
    def __init__(self, repo_name, max_history=5, temp_file_ttl=3600):
        """Initialize cache manager with repository name and conversation history limit.
        
        Args:
            repo_name (str): Name of the repository for cache organization
            max_history (int, optional): Maximum number of conversation entries to keep. Defaults to 5.
            temp_file_ttl (int, optional): Time to live for temporary files in seconds. Defaults to 1 hour.
        """
        self.repo_name = repo_name
        self.max_history = max_history
        self.temp_file_ttl = temp_file_ttl
        self.base_cache_dir = os.path.join('cache', self.repo_name)
        self.conversation_dir = os.path.join(self.base_cache_dir, 'conversations')
        self.temp_base_dir = os.path.join(self.base_cache_dir, 'temp')
        
        # Create necessary directories
        for directory in [self.conversation_dir, self.temp_base_dir]:
            os.makedirs(directory, exist_ok=True)
            
        # Clean up old temporary files on initialization
        self.cleanup_temp_files()

    def get_conversation_history(self, user_id):
        """Retrieves conversation history for a user from JSONL file, up to max_history messages."""
        file_path = os.path.join(self.conversation_dir, f"{user_id}.jsonl")
        history = deque(maxlen=self.max_history)
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                for line in f:
                    history.append(json.loads(line.strip()))
        return list(history)

    def append_to_conversation(self, user_id, message):
        """Appends message to user's conversation history and trims to max history items."""
        history = self.get_conversation_history(user_id)
        history.append(message)
        if len(history) > self.max_history:
            history = history[-self.max_history:]
        file_path = os.path.join(self.conversation_dir, f"{user_id}.jsonl")
        with open(file_path, 'w') as f:
            for item in history:
                f.write(json.dumps(item) + '\n')

    def get_cache_dir(self, cache_type):
        """Creates and returns a cache directory for a given type."""
        cache_dir = os.path.join(self.base_cache_dir, cache_type)
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def get_user_temp_dir(self, user_id):
        """Get or create a temporary directory for a specific user.
        
        Args:
            user_id (str): Discord user ID
            
        Returns:
            str: Path to the user's temporary directory
        """
        user_temp_dir = os.path.join(self.temp_base_dir, str(user_id))
        os.makedirs(user_temp_dir, exist_ok=True)
        return user_temp_dir

    def create_temp_file(self, user_id, prefix=None, suffix=None, content=None):
        """Creates a temporary file with optional content and returns its path.
        
        Args:
            user_id (str): Discord user ID
            prefix (str, optional): Prefix for the temporary filename
            suffix (str, optional): Suffix for the temporary filename (e.g., '.txt')
            content (str/bytes, optional): Content to write to the temporary file
            
        Returns:
            tuple: (str: Path to the created temporary file, str: Unique file ID)
        """
        # Generate a unique ID for this file
        file_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Construct filename with all components
        filename_parts = []
        if prefix:
            filename_parts.append(prefix)
        filename_parts.extend([timestamp, file_id])
        filename = '_'.join(filename_parts)
        if suffix:
            filename += suffix
            
        # Get user's temp directory and create full path
        user_temp_dir = self.get_user_temp_dir(user_id)
        temp_path = os.path.join(user_temp_dir, filename)
        
        # Write content to file
        mode = 'wb' if isinstance(content, bytes) else 'w'
        encoding = None if isinstance(content, bytes) else 'utf-8'
        
        try:
            with open(temp_path, mode, encoding=encoding) as f:
                if content is not None:
                    f.write(content)
            logging.info(f"Created temporary file for user {user_id}: {temp_path}")
            
            # Create metadata file to store creation time and other info
            metadata = {
                'created_at': datetime.now().isoformat(),
                'user_id': user_id,
                'file_id': file_id,
                'original_filename': filename
            }
            metadata_path = f"{temp_path}.meta"
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f)
                
            return temp_path, file_id
            
        except Exception as e:
            logging.error(f"Error creating temporary file for user {user_id}: {str(e)}")
            raise

    def get_temp_file(self, user_id, file_id):
        """Retrieve a temporary file path by its ID and verify user ownership.
        
        Args:
            user_id (str): Discord user ID
            file_id (str): Unique file ID
            
        Returns:
            str: Path to the temporary file if found and owned by user, None otherwise
        """
        user_temp_dir = self.get_user_temp_dir(user_id)
        
        try:
            for filename in os.listdir(user_temp_dir):
                if filename.endswith('.meta'):
                    metadata_path = os.path.join(user_temp_dir, filename)
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                        
                    if metadata['file_id'] == file_id and metadata['user_id'] == user_id:
                        file_path = metadata_path[:-5]  # Remove .meta extension
                        if os.path.exists(file_path):
                            return file_path
                            
            return None
            
        except Exception as e:
            logging.error(f"Error retrieving temporary file {file_id} for user {user_id}: {str(e)}")
            return None

    def cleanup_temp_files(self, force=False):
        """Removes temporary files older than TTL.
        
        Args:
            force (bool, optional): If True, removes all temporary files regardless of age
        """
        current_time = datetime.now()
        
        try:
            # Iterate through user directories
            for user_id in os.listdir(self.temp_base_dir):
                user_temp_dir = os.path.join(self.temp_base_dir, user_id)
                if not os.path.isdir(user_temp_dir):
                    continue
                    
                for filename in os.listdir(user_temp_dir):
                    if filename.endswith('.meta'):
                        continue
                        
                    file_path = os.path.join(user_temp_dir, filename)
                    metadata_path = f"{file_path}.meta"
                    
                    try:
                        if os.path.exists(metadata_path):
                            with open(metadata_path, 'r') as f:
                                metadata = json.load(f)
                            created_at = datetime.fromisoformat(metadata['created_at'])
                            file_age = current_time - created_at
                        else:
                            file_age = current_time - datetime.fromtimestamp(os.path.getctime(file_path))
                            
                        if force or file_age > timedelta(seconds=self.temp_file_ttl):
                            self.remove_temp_file(metadata['user_id'], metadata['file_id'])
                            
                    except Exception as e:
                        logging.error(f"Error processing temporary file {file_path}: {str(e)}")
                        
                # Remove empty user directories
                if not os.listdir(user_temp_dir):
                    os.rmdir(user_temp_dir)
                    
        except Exception as e:
            logging.error(f"Error during temp file cleanup: {str(e)}")

    def remove_temp_file(self, user_id, file_id):
        """Safely removes a specific temporary file.
        
        Args:
            user_id (str): Discord user ID
            file_id (str): Unique file ID
        """
        file_path = self.get_temp_file(user_id, file_id)
        if not file_path:
            return
            
        try:
            # Remove the main file
            if os.path.exists(file_path):
                os.remove(file_path)
                
            # Remove the metadata file
            metadata_path = f"{file_path}.meta"
            if os.path.exists(metadata_path):
                os.remove(metadata_path)
                
            logging.info(f"Removed temporary file {file_id} for user {user_id}")
            
        except Exception as e:
            logging.error(f"Error removing temporary file {file_id} for user {user_id}: {str(e)}")
            raise