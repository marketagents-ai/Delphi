from typing import List
from pydantic import BaseModel

class RetrievedMemory(BaseModel):
    text: str
    similarity: float
    context: str = ""

class MemoryRetriever:
    """
    MemoryRetriever provides methods to search stored documents or agent memories
    based on embedding similarity, dynamically referencing tables.
    """
    def __init__(self, config, db_conn, embedding_service):
        self.config = config
        self.db = db_conn
        self.embedding_service = embedding_service
        self.full_text = ""

    def search_knowledge_base(self, table_prefix: str, query: str, top_k: int = None) -> List[RetrievedMemory]:
        """
        Search a specific knowledge base for relevant content based on semantic similarity.
        """
        self.db.connect()
        query_embedding = self.embedding_service.get_embeddings(query)
        top_k = top_k or self.config.top_k

        knowledge_chunks_table = f"{table_prefix}_knowledge_chunks"
        knowledge_objects_table = f"{table_prefix}_knowledge_objects"

        self.db.cursor.execute(f"""
            WITH ranked_chunks AS (
                SELECT DISTINCT ON (c.text)
                    c.id, c.text, c.start_pos, c.end_pos, k.content,
                    (1 - (c.embedding <=> %s::vector)) AS similarity
                FROM {knowledge_chunks_table} c
                JOIN {knowledge_objects_table} k ON c.knowledge_id = k.knowledge_id
                WHERE (1 - (c.embedding <=> %s::vector)) >= %s
                ORDER BY c.text, similarity DESC
            )
            SELECT * FROM ranked_chunks
            ORDER BY similarity DESC
            LIMIT %s;
        """, (query_embedding, query_embedding, self.config.similarity_threshold, top_k))

        results = []
        rows = self.db.cursor.fetchall()
        for row in rows:
            _, text, start_pos, end_pos, full_content, sim = row
            self.full_text = full_content
            context = self._get_context(start_pos, end_pos, full_content)
            results.append(RetrievedMemory(text=text, similarity=sim, context=context))

        return results

    def search_agent_memory(self, agent_id: str, query: str, top_k: int = None) -> List[RetrievedMemory]:
        """
        Search a specific agent's memory for relevant content based on semantic similarity.
        """
        self.db.connect()
        query_embedding = self.embedding_service.get_embeddings(query)
        top_k = top_k or self.config.top_k

        agent_memory_table = f"agent_{agent_id}_memory"

        self.db.cursor.execute(f"""
            SELECT content,
                   (1 - (embedding <=> %s::vector)) AS similarity
            FROM {agent_memory_table}
            ORDER BY similarity DESC
            LIMIT %s;
        """, (query_embedding, top_k))

        results = []
        rows = self.db.cursor.fetchall()
        for row in rows:
            content, sim = row
            results.append(RetrievedMemory(text=content, similarity=sim))

        return results

    def _get_context(self, start: int, end: int, full_text: str) -> str:
        """
        Extracts context around a specific text chunk within a full document.
        """
        start_idx = max(0, start - self.config.context_window)
        end_idx = min(len(full_text), end + self.config.context_window)
        context = full_text[start_idx:end_idx].strip()
        if start_idx > 0:
            context = "..." + context
        if end_idx < len(full_text):
            context = context + "..."
        return context

if __name__ == "__main__":
    import os
    from market_agents.memory.config import load_config_from_yaml
    from market_agents.memory.setup_db import DatabaseConnection
    from market_agents.memory.embedding import MemoryEmbedder
    from market_agents.memory.knowledge_base import MarketKnowledgeBase
    from market_agents.memory.memory import MarketMemory, MemoryObject
    from market_agents.memory.vector_search import MemoryRetriever

    # Load configuration and initialize services
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, "memory_config.yaml")

    config = load_config_from_yaml(config_path)
    db_conn = DatabaseConnection(config)
    embedder = MemoryEmbedder(config)

    # Specify table prefixes
    knowledge_base_prefix = "quarterly_earnings"
    agent_id = "crypto_agent_123"

    # Initialize MarketKnowledgeBase
    knowledge_base = MarketKnowledgeBase(config, db_conn, embedder, table_prefix=knowledge_base_prefix)

    # Store a test document in the knowledge base
    test_doc = """
    Q4 2023 Quarterly Earnings Report
    
    Revenue increased 15% year-over-year to $2.3B. 
    Operating margin expanded to 28%.
    Strong performance in cloud services division.
    Earnings per share of $1.45 exceeded analyst estimates.
    """
    metadata = {"source": "earnings_report", "category": "financial_report"}
    knowledge_base.ingest_knowledge(test_doc, metadata=metadata)

    # Initialize MarketMemory for the agent
    memory_store = MarketMemory(config, db_conn, embedder, agent_id=agent_id)

    # Store a test memory for the agent
    test_memory = MemoryObject(
        agent_id=agent_id,
        cognitive_step="reflection",
        content="Given recent market volatility, I'm shifting my strategy to focus more on stablecoins and established cryptocurrencies. The risk-reward ratio for altcoins seems unfavorable in current conditions.",
        metadata={"topic": "market_strategy"}
    )
    memory_store.store_memory(test_memory)

    # Initialize MemoryRetriever for searches
    retriever = MemoryRetriever(config, db_conn, embedder)

    # Perform a search in the knowledge base
    print("\nDocument Search Results:")
    doc_results = retriever.search_knowledge_base(knowledge_base_prefix, "quarterly earnings", top_k=5)
    for r in doc_results:
        print(f"Text: {r.text}\nSimilarity: {r.similarity}\nContext: {r.context}\n")

    # Perform a search in the agent's memory
    print("\nAgent Memory Search Results:")
    agent_mem_results = retriever.search_agent_memory(agent_id, "strategy shift", top_k=3)
    for r in agent_mem_results:
        print(f"Text: {r.text}\nSimilarity: {r.similarity}\n")
