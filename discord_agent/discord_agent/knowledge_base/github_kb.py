import base64
import logging
import os
from typing import Optional, List
from github import Github, GithubException, RateLimitExceededException

from market_agents.memory.setup_db import DatabaseConnection
from market_agents.memory.embedding import MemoryEmbedder
from market_agents.memory.knowledge_base import KnowledgeChunk, KnowledgeChunker, MarketKnowledgeBase

import re
import time
from datetime import datetime, timezone

class GitHubKnowledgeBase(MarketKnowledgeBase):
    def __init__(self, config, db_conn: DatabaseConnection, embedding_service: MemoryEmbedder, table_prefix: str = "github"):
        """
        :param config: dict-like configuration
        :param db_conn: DatabaseConnection instance
        :param embedding_service: MemoryEmbedder instance
        :param table_prefix: Will create/use table_prefix_knowledge_objects and table_prefix_knowledge_chunks
        """
        super().__init__(
            config=config,
            db_conn=db_conn,
            embedding_service=embedding_service,
            table_prefix=table_prefix,
            chunking_method=CodeChunker()
        )

    ALLOWED_EXTENSIONS = {'.py', '.md', '.txt', '.yaml', '.yml', '.json'}

    def _check_file_ingestion(self, file_path: str, repo_name: str) -> bool:
        """Check if a file has already been ingested into the knowledge base."""
        self.db.connect()
        # Use the prefix-based knowledge_objects_table
        knowledge_objects_table = f"{self.table_prefix}_knowledge_objects"

        self.db.cursor.execute(f"""
            SELECT COUNT(*)
            FROM {knowledge_objects_table}
            WHERE metadata->>'source' = 'github'
              AND metadata->>'file_path' = %s
              AND metadata->>'repo_name' = %s
        """, (file_path, repo_name))
        return self.db.cursor.fetchone()[0] > 0

    def ingest_from_github_repo(
        self,
        token: str,
        repo_name: str,
        max_depth: Optional[int] = None,
        branch: str = 'main',
        current_path: str = "",
        current_depth: int = 0
    ):
        """
        Recursively ingest all allowed files from a GitHub repo into the knowledge base.
        :param token: Personal access token (PAT) for GitHub
        :param repo_name: "username/reponame" or org
        :param max_depth: Depth limit for folder traversal
        :param branch: Which branch to pull from
        :param current_path: Internally used for recursion
        :param current_depth: Internally used for recursion
        """
        if max_depth is not None and current_depth > max_depth:
            return

        g = Github(token)
        
        # Check rate limit before making requests
        rate_limit = g.get_rate_limit()
        if rate_limit.core.remaining < 10:  # Buffer of 10 requests
            reset_timestamp = rate_limit.core.reset.replace(tzinfo=timezone.utc)
            sleep_time = (reset_timestamp - datetime.now(timezone.utc)).total_seconds()
            if sleep_time > 0:
                logging.warning(f"Rate limit nearly exceeded. Sleeping for {sleep_time:.2f} seconds until reset.")
                time.sleep(sleep_time + 1)  # Add 1 second buffer

        repo = g.get_repo(repo_name)

        try:
            contents = repo.get_contents(current_path, ref=branch)
        except RateLimitExceededException:
            rate_limit = g.get_rate_limit()
            reset_timestamp = rate_limit.core.reset.replace(tzinfo=timezone.utc)
            sleep_time = (reset_timestamp - datetime.now(timezone.utc)).total_seconds()
            if sleep_time > 0:
                logging.warning(f"Rate limit exceeded. Sleeping for {sleep_time:.2f} seconds until reset.")
                time.sleep(sleep_time + 1)
                # Retry the request after waiting
                contents = repo.get_contents(current_path, ref=branch)
        except GithubException as e:
            logging.error(f"Error getting contents of {current_path} on branch '{branch}': {str(e)}")
            return

        # Process contents in batches to avoid rate limiting
        batch_size = 10
        for i in range(0, len(contents), batch_size):
            batch = contents[i:i + batch_size]
            
            for content in batch:
                if content.type == 'dir':
                    self.ingest_from_github_repo(
                        token,
                        repo_name,
                        max_depth,
                        branch,
                        content.path,
                        current_depth + 1
                    )
                elif content.type == 'file':
                    # Skip large files (>1MB)
                    if content.size > 1000000:
                        logging.info(f"Skipping large file: {content.path}")
                        continue

                    _, file_extension = os.path.splitext(content.path)
                    if file_extension.lower() not in self.ALLOWED_EXTENSIONS:
                        logging.debug(f"Skipping unsupported file extension: {content.path}")
                        continue

                    # Check if file is already ingested
                    if self._check_file_ingestion(content.path, repo_name):
                        logging.info(f"File already ingested: {content.path}")
                        continue

                    # Check rate limit before each file
                    rate_limit = g.get_rate_limit()
                    if rate_limit.core.remaining < 10:
                        reset_timestamp = rate_limit.core.reset.replace(tzinfo=timezone.utc)
                        sleep_time = (reset_timestamp - datetime.now(timezone.utc)).total_seconds()
                        if sleep_time > 0:
                            logging.warning(f"Rate limit nearly exceeded. Sleeping for {sleep_time:.2f} seconds until reset.")
                            time.sleep(sleep_time + 1)

                    # Attempt to decode content
                    try:
                        file_data = base64.b64decode(content.content).decode('utf-8')
                    except UnicodeDecodeError:
                        logging.warning(f"Skipping binary or non-UTF8 file: {content.path}")
                        continue
                    except Exception as decode_err:
                        logging.error(f"Error decoding file {content.path}: {str(decode_err)}")
                        continue

                    # Ingest into knowledge base
                    metadata = {
                        "source": "github",
                        "repo_name": repo_name,
                        "file_path": content.path,
                        "branch": branch
                    }

                    try:
                        knowledge_id = self.ingest_knowledge(file_data, metadata=metadata)
                        logging.info(f"Ingested {content.path} with ID: {knowledge_id}")
                    except Exception as ingest_err:
                        logging.error(f"Error ingesting {content.path}: {str(ingest_err)}")

            # Slight delay to be polite to GitHub’s API
            time.sleep(1)


class CodeChunker(KnowledgeChunker):
    def __init__(self, min_size: int = 100, max_size: int = 2000):
        self.min_size = min_size
        self.max_size = max_size

    def chunk(self, text: str) -> List[KnowledgeChunk]:
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        splits = [
            # Split on class definitions while including the following method
            r'(?=\n(?:class)\s+[a-zA-Z_]\w*\s*[\(\:](?:(?!\n(?:class|def)\s+).)*?\n\s+(?:def)\s+)',
            # Split on standalone method definitions
            r'(?=\n\s*(?:def)\s+[a-zA-Z_]\w*\s*\()',
            # Split on decorated class/method definitions
            r'(?=\n\s*@\w+\s*\n\s*(?:class|def))',
            # Split on main block
            r'(?=\n\s*if\s+__name__\s*==)',
        ]
        
        pattern = '|'.join(splits)
        segments = re.split(pattern, text.strip())
        
        chunks = []
        current_pos = 0
        current_chunk = []
        current_length = 0
        
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            
            # If it's purely import statements, accumulate them
            if re.match(r'^(\s*(?:from|import)\s+[a-zA-Z_]\w*[\s\w\.,]*)+$', segment):
                if current_chunk:
                    current_chunk.append(segment)
                    current_length += len(segment)
                else:
                    current_chunk = [segment]
                    current_length = len(segment)
                continue

            # If it's a class definition with an internal method, we split that out first
            if re.match(r'^\s*class\s+', segment):
                method_match = re.search(r'(.*?\n\s*def\s+.*?)(?=\n\s*def|\Z)', segment, re.DOTALL)
                if method_match:
                    first_part = method_match.group(1)
                    rest = segment[len(first_part):].strip()
                    
                    chunks.append(KnowledgeChunk(
                        text=first_part,
                        start=current_pos,
                        end=current_pos + len(first_part)
                    ))
                    current_pos += len(first_part) + 1
                    
                    if rest:
                        segment = rest
                    else:
                        continue

            # If adding this segment to current_chunk would exceed max_size, finalize the existing chunk
            if current_length + len(segment) > self.max_size:
                if current_chunk:
                    chunk_text = '\n\n'.join(current_chunk)
                    chunks.append(KnowledgeChunk(
                        text=chunk_text,
                        start=current_pos,
                        end=current_pos + len(chunk_text)
                    ))
                    current_pos += len(chunk_text) + 1
                    current_chunk = []
                    current_length = 0
                
                # Put the new segment in its own chunk
                chunks.append(KnowledgeChunk(
                    text=segment,
                    start=current_pos,
                    end=current_pos + len(segment)
                ))
                current_pos += len(segment) + 1
            else:
                # Accumulate the segment
                current_chunk.append(segment)
                current_length += len(segment)
        
        # If something remains in current_chunk, flush it
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            chunks.append(KnowledgeChunk(
                text=chunk_text,
                start=current_pos,
                end=current_pos + len(chunk_text)
            ))
        
        return chunks

if __name__ == "__main__":
    import os
    import logging
    from dotenv import load_dotenv
    from market_agents.memory.config import load_config_from_yaml

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    TEST_REPO = "marketagents-ai/MarketAgents"
    TEST_BRANCH = "main"
    MAX_DEPTH = 2

    try:
        GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
        if not GITHUB_TOKEN:
            raise ValueError("GITHUB_TOKEN environment variable is not set")

        config_path = os.path.join("market_agents/memory", "memory_config.yaml")
        logging.info(f"Loading config from {config_path}")
        config = load_config_from_yaml(config_path)

        db_conn = DatabaseConnection(config)
        embedder = MemoryEmbedder(config)
        
        # Initialize GitHubKnowledgeBase with prefix "github"
        kb = GitHubKnowledgeBase(config, db_conn, embedder, table_prefix="github")
        
        logging.info(f"Starting ingestion of {TEST_REPO}")
        kb.ingest_from_github_repo(
            token=GITHUB_TOKEN,
            repo_name=TEST_REPO,
            max_depth=MAX_DEPTH,
            branch=TEST_BRANCH
        )
        
        logging.info("Successfully finished indexing GitHub repo")

    except Exception as e:
        logging.error(f"Error during ingestion: {str(e)}", exc_info=True)
        raise
