import json
import uuid
from uuid import UUID
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from market_agents.memory.embedding import MemoryEmbedder
from market_agents.memory.setup_db import DatabaseConnection

class MemoryObject(BaseModel):
    memory_id: UUID = Field(default_factory=uuid.uuid4)
    agent_id: str
    cognitive_step: str
    content: str
    embedding: Optional[List[float]] = None
    created_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

class MarketMemory:

    def __init__(self, config, db_conn: DatabaseConnection, embedder: MemoryEmbedder, agent_id: str):
        self.config = config
        self.db = db_conn
        self.embedder = embedder
        self.agent_id = agent_id
        self.memory_table = f"agent_{agent_id}_memory"

        self.db.create_agent_memory_table(agent_id)

    def store_memory(self, memory_object: MemoryObject):
        """Store a memory object in the agent's specific memory table."""
        self.db.connect()
        try:
            # Generate embedding if not provided
            if memory_object.embedding is None:
                memory_object.embedding = self.embedder.get_embeddings(memory_object.content)

            self.db.cursor.execute(f"""
                INSERT INTO {self.memory_table} (memory_id, cognitive_step, content, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING created_at;
            """, (
                str(memory_object.memory_id),
                memory_object.cognitive_step,
                memory_object.content,
                memory_object.embedding,
                json.dumps(memory_object.metadata) if memory_object.metadata else json.dumps({})
            ))
            memory_object.created_at = self.db.cursor.fetchone()[0]
            self.db.conn.commit()
        except Exception as e:
            self.db.conn.rollback()
            raise e

    def get_memories(
        self,
        limit: int = 10,
        cognitive_step: Union[str, List[str], None] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[MemoryObject]:
        """Retrieve memories from the agent's specific memory table."""
        self.db.connect()

        conditions = []
        params = []

        if cognitive_step:
            if isinstance(cognitive_step, str):
                conditions.append("cognitive_step = %s")
                params.append(cognitive_step)
            else:
                placeholders = ", ".join(["%s"] * len(cognitive_step))
                conditions.append(f"cognitive_step IN ({placeholders})")
                params.extend(cognitive_step)

        if metadata_filters:
            for k, v in metadata_filters.items():
                conditions.append("metadata->>%s = %s")
                params.append(k)
                params.append(str(v))

        if start_time:
            conditions.append("created_at >= %s")
            params.append(start_time)

        if end_time:
            conditions.append("created_at <= %s")
            params.append(end_time)

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        query = f"""
            SELECT memory_id, cognitive_step, content, embedding, created_at, metadata
            FROM {self.memory_table}
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s;
        """
        params.append(limit)

        try:
            self.db.cursor.execute(query, tuple(params))
            rows = self.db.cursor.fetchall()
            memories = []
            for row in rows:
                mem_id, step, content, embedding, created_at, metadata = row
                if isinstance(embedding, str):
                    embedding = [float(x) for x in embedding.strip('[]').split(',')]
                mem = MemoryObject(
                    memory_id=UUID(mem_id),
                    agent_id=self.agent_id,
                    cognitive_step=step,
                    content=content,
                    embedding=embedding,
                    created_at=created_at,
                    metadata=metadata if metadata else {}
                )
                memories.append(mem)
            return memories
        except Exception as e:
            raise e

    def delete_memories(
        self,
        cognitive_step: Union[str, List[str], None] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> int:
        """Delete memories from the agent's specific memory table."""
        self.db.connect()

        conditions = []
        params = []

        if cognitive_step:
            if isinstance(cognitive_step, str):
                conditions.append("cognitive_step = %s")
                params.append(cognitive_step)
            else:
                placeholders = ", ".join(["%s"] * len(cognitive_step))
                conditions.append(f"cognitive_step IN ({placeholders})")
                params.extend(cognitive_step)

        if metadata_filters:
            for k, v in metadata_filters.items():
                conditions.append("metadata->>%s = %s")
                params.append(k)
                params.append(str(v))

        if start_time:
            conditions.append("created_at >= %s")
            params.append(start_time)

        if end_time:
            conditions.append("created_at <= %s")
            params.append(end_time)

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        try:
            self.db.cursor.execute(f"DELETE FROM {self.memory_table} WHERE {where_clause} RETURNING *;", tuple(params))
            deleted_count = self.db.cursor.rowcount
            self.db.conn.commit()
            return deleted_count
        except Exception as e:
            self.db.conn.rollback()
            raise e
