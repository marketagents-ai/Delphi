import asyncio
import argparse

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from agent.api_client import initialize_api_client, call_api, encode_image

async def test_text_query(api_type, model=None):
    args = argparse.Namespace(api=api_type, model=model)
    initialize_api_client(args)
    
    prompt = "What is the capital of France?"
    system_prompt = "You are a helpful assistant."
    
    response = await call_api(prompt, system_prompt=system_prompt)
    print(f"\nText Query Test ({api_type}):")
    print(f"Prompt: {prompt}")
    print(f"Response: {response}")

async def test_image_query(api_type, model=None):
    args = argparse.Namespace(api=api_type, model=model)
    initialize_api_client(args)
    
    image_path = "assets/serain-tars4.jpg"  # Replace with an actual image path
    
    prompt = "Describe this image in detail."
    system_prompt = "You are a helpful assistant capable of analyzing images."
    
    response = await call_api(
        prompt=prompt, 
        system_prompt=system_prompt,
        image_paths=[image_path]  # Updated to use image_paths parameter
    )
    print(f"\nImage Query Test ({api_type}):")
    print(f"Prompt: {prompt}")
    print(f"Response: {response}")

async def main():
    # Define API types and their corresponding models
    api_configs = {
        #'openai': 'chatgpt-4o-latest',
        #'anthropic': 'claude-3-5-sonnet-20241022',
        'ollama': 'llama3.2-vision:latest'
    }
    
    for api_type, model in api_configs.items():
        try:
            await test_text_query(api_type, model)
            await test_image_query(api_type, model)
        except Exception as e:
            print(f"Error testing {api_type} with model {model}: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
