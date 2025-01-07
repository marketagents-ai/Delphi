import psycopg2
from psycopg2.errors import DuplicateDatabase


class DatabaseConnection:
    def __init__(self, config):
        self.config = config
        self.conn = None
        self.cursor = None

    def connect(self):
        """Establish a connection to the database."""
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

    def close(self):
        """Close the database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def _ensure_database_exists(self):
        """Ensure the database exists, creating it if necessary."""
        try:
            temp_conn = psycopg2.connect(
                dbname="postgres",
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

    def create_knowledge_base_tables(self, base_name: str):
        """Create separate tables for a specific knowledge base."""
        self.connect()
        knowledge_objects_table = f"{base_name}_knowledge_objects"
        knowledge_chunks_table = f"{base_name}_knowledge_chunks"

        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {knowledge_objects_table} (
                knowledge_id UUID PRIMARY KEY,
                content TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB DEFAULT '{{}}'::jsonb
            );
        """)

        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {knowledge_chunks_table} (
                id SERIAL PRIMARY KEY,
                knowledge_id UUID REFERENCES {knowledge_objects_table}(knowledge_id),
                text TEXT,
                start_pos INTEGER,
                end_pos INTEGER,
                embedding vector({self.config.vector_dim}),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Add vector index for the chunks
        self.cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS {base_name}_chunks_index
            ON {knowledge_chunks_table} USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {self.config.lists});
        """)

        self.conn.commit()

    def create_agent_memory_table(self, agent_id: str):
        """Create a separate memory table for a specific agent."""
        self.connect()
        agent_memory_table = f"agent_{agent_id}_memory"

        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {agent_memory_table} (
                memory_id UUID PRIMARY KEY,
                cognitive_step TEXT,
                content TEXT,
                embedding vector({self.config.vector_dim}),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB DEFAULT '{{}}'::jsonb
            );
        """)

        index_name = f"agent_{agent_id}_memory_index"

        self.cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {agent_memory_table} USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {self.config.lists});
        """)

        self.conn.commit()


    def init_agent_memory(self, agent_ids: list):
        """Initialize memory tables for multiple agents."""
        for agent_id in agent_ids:
            self.create_agent_memory_table(agent_id)

    def clear_agent_memory(self, agent_id: str):
        """Clear all memory entries for a specific agent."""
        self.connect()
        agent_memory_table = f"agent_{agent_id}_memory"
        try:
            self.cursor.execute(f"TRUNCATE TABLE {agent_memory_table};")
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise e
        
    def ensure_connection(self):
        """Ensure database connection is active, reconnect if needed"""
        try:
            self.cursor.execute("SELECT 1")
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            self.connect()
