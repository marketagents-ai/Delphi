import re
from typing import List
from datetime import datetime
from pydantic import BaseModel

class DocumentChunk(BaseModel):
    text: str
    start: int
    end: int
    embedding: List[float] = None
    document_id: int = None

class DocumentProcessor:
    def __init__(self, config, db_conn, embedding_service):
        self.config = config
        self.db = db_conn
        self.embedding_service = embedding_service
        self.full_text = ""

    def ingest_document(self, text: str) -> int:
        """Process document: chunk, embed, and store."""
        chunks = self._semantic_split(text)
        embeddings = self.embedding_service.get_embeddings([c.text for c in chunks])
        
        # Assign embeddings
        for chunk, emb in zip(chunks, embeddings):
            chunk.embedding = emb

        document_id = self._save_document_and_chunks(text, chunks)
        return document_id

    def _semantic_split(self, text: str) -> List[DocumentChunk]:
        """Split text into semantic chunks according to simple rules."""
        self.full_text = text
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        splits = [
            r'(?<=\n\n)',
            r'(?<=\.)\s+(?=[A-Z])',
            r'(?<=\n)\s*[-•\*]\s+',
            r'(?<=\n)\s*\d+\.\s+',
            r'(?<=,)\s+',
            r'(?<=;)\s+',
            r'\s+(?=and|but|or)\s+',
            r'\s+(?=because|however)\s+'
        ]
        
        pattern = '|'.join(splits)
        segments = re.split(pattern, text.strip())

        chunks = []
        current_chunk = []
        current_length = 0
        current_pos = 0
        chunk_start = 0

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            if current_length + len(segment) > self.config.max_chunk_size and current_chunk:
                chunk_text = ' '.join(current_chunk)
                chunks.append(DocumentChunk(text=chunk_text, start=chunk_start, end=chunk_start+len(chunk_text)))
                current_chunk = []
                current_length = 0
                chunk_start = current_pos

            current_chunk.append(segment)
            current_length += len(segment)
            current_pos += len(segment) + 1

            if current_length >= self.config.min_chunk_size:
                chunk_text = ' '.join(current_chunk)
                chunks.append(DocumentChunk(text=chunk_text, start=chunk_start, end=chunk_start+len(chunk_text)))
                current_chunk = []
                current_length = 0
                chunk_start = current_pos

        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            chunks.append(DocumentChunk(text=chunk_text, start=chunk_start, end=chunk_start+len(chunk_text)))

        return chunks

    def _save_document_and_chunks(self, document_text: str, chunks: List[DocumentChunk]) -> int:
        self.db.connect()
        try:
            # Insert document
            self.db.cursor.execute(
                "INSERT INTO documents (content) VALUES (%s) RETURNING id;",
                (document_text,)
            )
            document_id = self.db.cursor.fetchone()[0]

            # Insert chunks
            for chunk in chunks:
                self.db.cursor.execute("""
                    INSERT INTO document_chunks (document_id, text, start_pos, end_pos, embedding)
                    VALUES (%s, %s, %s, %s, %s);
                """, (document_id, chunk.text, chunk.start, chunk.end, chunk.embedding))

            self.db.conn.commit()
            return document_id
        except Exception as e:
            self.db.conn.rollback()
            raise e

if __name__ == "__main__":
    import os
    from config import load_config_from_yaml
    from setup_db import DatabaseConnection
    from embedding import MemoryEmbedder

    # Load configuration and initialize services
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, "memory_config.yaml")

    config = load_config_from_yaml(config_path)
    db_conn = DatabaseConnection(config)
    embedder = MemoryEmbedder(config)
    
    # Initialize document processor
    doc_processor = DocumentProcessor(config, db_conn, embedder)
    
    # Test document for ingestion
    test_doc = """
    Market Analysis Report - Q4 2023
    
    The technology sector showed strong performance in Q4 2023. Cloud computing companies reported significant growth, with major players expanding their market share. AI-driven solutions saw increased adoption across industries.
    
    Key Highlights:
    • Cloud revenue grew by 25% YoY
    • Enterprise AI adoption increased 40%
    • Cybersecurity spending up 15%
    
    Market leaders continued to invest heavily in R&D, focusing on next-generation technologies. The semiconductor shortage showed signs of easing, though supply chain challenges persist in some areas.
    """
    
    try:
        # Ingest the test document: chunk, embed, and store in DB
        document_id = doc_processor.ingest_document(test_doc)
        print(f"Successfully ingested document with ID: {document_id}")
        
        # Verify that the document was stored
        db_conn.cursor.execute("SELECT content FROM documents WHERE id = %s", (document_id,))
        stored_doc = db_conn.cursor.fetchone()
        print("\nStored document content:")
        if stored_doc:
            print(stored_doc[0])
        else:
            print("Document not found in database.")
        
        # Retrieve and display chunks
        db_conn.cursor.execute("SELECT text, embedding FROM document_chunks WHERE document_id = %s", (document_id,))
        chunks = db_conn.cursor.fetchall()
        print(f"\nRetrieved {len(chunks)} chunks from the database:")
        for i, (chunk_text, chunk_embedding) in enumerate(chunks, 1):
            print(f"\nChunk {i}:")
            print("Text:", chunk_text)
            print("Embedding present:", "Yes" if chunk_embedding is not None else "No")
            
    except Exception as e:
        print(f"Error during document ingestion or retrieval: {e}")
    finally:
        db_conn.conn.close()

