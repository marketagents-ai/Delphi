import asyncio
import argparse
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from agent.api_client import initialize_api_client, get_embeddings


async def test_embeddings(api_type, model=None):
    # Test texts
    test_texts = [
        "The quick brown fox jumps over the lazy dog",
        "Machine learning is a subset of artificial intelligence",
        "Python is a versatile programming language"
    ]
    
    print(f"\nTesting embeddings for {api_type}" + (f" with model {model}" if model else ""))
    print("-" * 50)
    
    for text in test_texts:
        try:
            print(f"\nInput text: {text}")
            embeddings = await get_embeddings(text, model)
            
            # Print embedding details
            if isinstance(embeddings, list):
                print(f"Embedding dimension: {len(embeddings)}")
                print(f"First 5 values: {embeddings[:5]}")
            else:
                print(f"Embedding output: {embeddings}")
                
        except Exception as e:
            print(f"Error getting embeddings: {str(e)}")

async def search_similar_texts(query_text, reference_texts, model=None):
    print("\nPerforming similarity search")
    print("-" * 50)
    print(f"Query: {query_text}")
    
    # Get embeddings for query and reference texts
    query_embedding = await get_embeddings(query_text, model)
    reference_embeddings = []
    
    for text in reference_texts:
        embedding = await get_embeddings(text, model)
        reference_embeddings.append(embedding)
    
    # Convert to numpy arrays for efficient computation
    query_embedding = np.array(query_embedding)
    reference_embeddings = np.array(reference_embeddings)
    
    # Calculate dot product similarities
    similarities = np.dot(reference_embeddings, query_embedding)
    
    # Sort and return results
    results = list(zip(reference_texts, similarities))
    results.sort(key=lambda x: x[1], reverse=True)
    
    print("\nSearch Results:")
    for text, score in results:
        print(f"Score: {score:.4f} - Text: {text}")

async def main_async(args):
    # Initialize the API client
    initialize_api_client(args)
    
    # Run the embedding tests
    await test_embeddings(args.api, args.model)
    
    # If search flag is set, perform similarity search test
    if args.search:
        reference_texts = [
            "The quick brown fox jumps over the lazy dog",
            "Machine learning is a subset of artificial intelligence",
            "Python is a versatile programming language",
            "Natural language processing is fascinating",
            "Deep learning models require significant computing power"
        ]
        query = "Tell me about AI and machine learning"
        await search_similar_texts(query, reference_texts, args.model)

def main():
    parser = argparse.ArgumentParser(description='Test embedding models')
    parser.add_argument('--api', required=True, choices=['ollama', 'openai', 'anthropic', 'vllm'],
                      help='API type to use')
    parser.add_argument('--model', help='Override default embedding model')
    parser.add_argument('--search', action='store_true', help='Perform similarity search test')
    args = parser.parse_args()
    
    # Run all async operations in a single event loop
    asyncio.run(main_async(args))

if __name__ == "__main__":
    main() 