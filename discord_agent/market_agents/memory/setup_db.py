import psycopg2
from psycopg2.errors import DuplicateDatabase


class DatabaseConnection:
    def __init__(self, config):
        self.config = config
        self.conn = None
        self.cursor = None

    def connect(self):
        if not self.conn:
            self._ensure_database_exists()

            self.conn = psycopg2.connect(
                dbname=self.config.dbname,
                user=self.config.user,
                password=self.config.password,
                host=self.config.host,
                port=self.config.port
            )
            self.cursor = self.conn.cursor()
            self._init_tables()

    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def _ensure_database_exists(self):
        try:
            temp_conn = psycopg2.connect(
                dbname='postgres',
                user=self.config.user,
                password=self.config.password,
                host=self.config.host,
                port=self.config.port
            )
            temp_conn.autocommit = True
            temp_cur = temp_conn.cursor()
            try:
                temp_cur.execute(f"CREATE DATABASE {self.config.dbname}")
            except DuplicateDatabase:
                pass
            finally:
                temp_cur.close()
                temp_conn.close()
        except Exception as e:
            print(f"Error ensuring database exists: {e}")
            raise

    def _init_tables(self):
        self.cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        # Documents table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                content TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Chunks table (for ingested documents)
        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(id),
                text TEXT,
                start_pos INTEGER,
                end_pos INTEGER,
                embedding vector({self.config.vector_dim}),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Agent memory table (procedural/episodic memory)
        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS agent_memory (
                memory_id UUID PRIMARY KEY,
                agent_id TEXT,
                cognitive_step TEXT,
                content TEXT,
                embedding vector({self.config.vector_dim}),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB DEFAULT '{{}}'::jsonb
            );
        """)

        # Vector index for chunks
        self.cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS document_chunks_embedding_idx 
            ON document_chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {self.config.lists});
        """)

        # Vector index for agent_memory
        self.cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS agent_memory_embedding_idx 
            ON agent_memory USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {self.config.lists});
        """)

        self.conn.commit()
