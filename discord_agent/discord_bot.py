import discord
from discord import TextChannel
from discord.ext import commands

import logging
import asyncio
import os
import mimetypes
import tiktoken
import json
from datetime import datetime

import re
import pickle
from collections import defaultdict, Counter
import yaml
import argparse
from github import Github
from github import GithubException, UnknownObjectException  

import base64
import string
import threading
import nltk
nltk.download('punkt', quiet=True)
from nltk.tokenize import sent_tokenize

# Configuration imports
from discord_agent.bot_config import *
# Removed the import for call_api
# from agent.api_client import initialize_api_client, call_api
from discord_agent.cache_manager import CacheManager
from market_agents.orchestrators.discord_orchestrator import MessageProcessor

# Image handling
from PIL import Image
import io
import traceback

# Import tools
from discord_agent.tools.discordSUMMARISER import ChannelSummarizer
from discord_agent.tools.discordGITHUB import *

# Import memory module
from discord_agent.memory import UserMemoryIndex

script_dir = os.path.dirname(os.path.abspath(__file__))

# Set up logging
log_level = os.getenv('LOGLEVEL', 'INFO')
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

# JSONL logging setup
def log_to_jsonl(data):
    with open('bot_log.jsonl', 'a') as f:
        json.dump(data, f)
        f.write('\n')

# Persona intensity handling

def update_temperature(intensity):
    """Updates the global temperature parameter for LLM sampling based on persona intensity.
    
    The persona intensity (0-100) is mapped linearly to temperature (0.0-1.0).
    Higher temperatures result in more random/creative outputs, while lower 
    temperatures make the LLM responses more focused and deterministic.
    
    Args:
        intensity (int): Persona intensity value between 0-100
            0 = Most focused/deterministic (temp = 0.0)
            100 = Most random/creative (temp = 1.0)
    """
    global TEMPERATURE
    TEMPERATURE = intensity / 100.0
    logging.info(f"Updated temperature to {TEMPERATURE}")

# Since repo_processing_event is used but not defined, let's define it
repo_processing_event = threading.Event()
repo_processing_event.set()

def start_background_processing_thread(repo, memory_index, max_depth=None, branch='main'):
    """
    Start a background thread to process and index repository contents.

    Args:
        repo (GitHubRepo): The GitHub repository interface to process
        memory_index (UserMemoryIndex): Index for storing repository content memories
        max_depth (int, optional): Maximum directory depth to process. None means unlimited. Defaults to None.
        branch (str, optional): Git branch to process. Defaults to 'main'.

    The function:
    1. Creates a new thread targeting run_background_processing()
    2. Starts the thread to process repo contents asynchronously 
    3. Logs the start of background processing
    """
    thread = threading.Thread(target=run_background_processing, args=(repo, memory_index, max_depth, branch))
    thread.start()
    logging.info(f"Started background processing of repository contents in a separate thread (Branch: {branch}, Max Depth: {max_depth if max_depth is not None else 'Unlimited'})")

# Update the run_background_processing function to include the branch parameter
def run_background_processing(repo, memory_index, max_depth=None, branch='main'):
    global repo_processing_event
    repo_processing_event.clear()
    try:
        asyncio.run(process_repo_contents(repo, '', memory_index, max_depth, branch))
        memory_index.save_cache()  # Save the cache after indexing
    except Exception as e:
        logging.error(f"Error in background processing for branch '{branch}': {str(e)}")
    finally:
        repo_processing_event.set()

# Message processing

async def process_message(message, memory_index, cache_manager, bot, is_command=False):
    """
    Process an incoming Discord message and generate an appropriate response using the agent.

    Args:
        message (discord.Message): The Discord message to process
        memory_index (UserMemoryIndex): Index for storing and retrieving user interaction memories
        cache_manager (CacheManager): Manager for caching conversation history
        bot (commands.Bot): The bot instance
        is_command (bool, optional): Whether message is a command. Defaults to False.

    The function:
    1. Extracts message content and user info
    2. Retrieves relevant conversation history and messages
    3. Calls the agent to process the messages
    4. Sends the agent's action content back to the channel
    5. Saves interaction to memory and conversation history
    6. Logs the interaction
    """

    user_id = str(message.author.id)
    user_name = message.author.name

    if is_command:
        content = message.content.split(maxsplit=1)[1]
    else:
        if message.guild and message.guild.me:
            content = message.content.replace(f'<@!{message.guild.me.id}>', '').strip()
        else:
            content = message.content.strip()

    logging.info(f"Received message from {user_name} (ID: {user_id}): {content}")

    try:
        async with message.channel.typing():
            # Prepare channel_info
            channel_info = {
                'id': str(message.channel.id),
                'name': message.channel.name if hasattr(message.channel, 'name') else 'Direct Message'
            }

            # Prepare messages
            messages = []

            # Get the conversation history
            conversation_history = cache_manager.get_conversation_history(user_id)

            # Build messages from conversation_history
            if conversation_history:
                for conv in conversation_history[-10:]:
                    messages.append({
                        'content': conv['user_message'],
                        'author_id': user_id,
                        'author_name': user_name,
                        'timestamp': message.created_at.isoformat()
                    })
                    messages.append({
                        'content': conv['ai_response'],
                        'author_id': str(bot.user.id),
                        'author_name': bot.user.name,
                        'timestamp': message.created_at.isoformat()
                    })

            # Add recent messages from the channel history
            async for msg in message.channel.history(limit=10, oldest_first=True):
                messages.append({
                    'content': msg.content,
                    'author_id': str(msg.author.id),
                    'author_name': msg.author.name,
                    'timestamp': msg.created_at.isoformat()
                })

            # Append the current message
            messages.append({
                'content': content,
                'author_id': user_id,
                'author_name': user_name,
                'timestamp': message.created_at.isoformat()
            })

            # Call the agent to process the messages
            result = await bot.message_processor.process_messages(channel_info, messages)
            # Get the agent's action
            perception = result.get('perception')
            action_result = result.get('action')
            reflection = result.get('reflection')

            if action_result and action_result.get('content'):
                #response_content = f"```json\n<perception>\n{json.dumps(perception, indent=2)}\n</perception>```\n"
                response_content = action_result['content']['action']['content']
                #response_content += f"```json\n<reflection>\n{json.dumps(reflection, indent=2)}\n</reflection>```"
                await send_long_message(message.channel, response_content)
                # Fix the logging statement here
                logging.info(f"Sent response to {user_name} (ID: {user_id}): {response_content[:1000] if response_content else ''}")

                # Save interaction to memory and conversation history
                memory_text = f"User {user_name} in {message.channel.name if hasattr(message.channel, 'name') else 'DM'}: {content}\nYour response: {response_content}"
                memory_index.add_memory(user_id, memory_text)

                cache_manager.append_to_conversation(user_id, {
                    'user_name': user_name,
                    'user_message': content,
                    'ai_response': response_content
                })

                log_to_jsonl({
                    'event': 'chat_interaction',
                    'timestamp': datetime.now().isoformat(),
                    'user_id': user_id,
                    'user_name': user_name,
                    'channel': message.channel.name if hasattr(message.channel, 'name') else 'DM',
                    'user_message': content,
                    'ai_response': response_content
                })

            else:
                logging.error("No action content received from the agent")
                await message.channel.send("I'm sorry, I couldn't process that message.")

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        await message.channel.send(error_message)
        logging.error(f"Error in message processing for {user_name} (ID: {user_id}): {str(e)}")
        log_to_jsonl({
            'event': 'chat_error',
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'user_name': user_name,
            'channel': message.channel.name if hasattr(message.channel, 'name') else 'DM',
            'error': str(e)
        })

async def process_files(message, memory_index, cache_manager, bot, user_message=""):
    """Process multiple files from a Discord message using the agent."""
    user_id = str(message.author.id)
    user_name = message.author.name

    if not message.attachments:
        raise ValueError("No attachments found in message")

    logging.info(f"Processing files from {user_name} (ID: {user_id})")

    try:
        async with message.channel.typing():
            # Prepare channel_info
            channel_info = {
                'id': str(message.channel.id),
                'name': message.channel.name if hasattr(message.channel, 'name') else 'Direct Message'
            }

            # Prepare messages
            messages = []

            # Get the conversation history
            conversation_history = cache_manager.get_conversation_history(user_id)

            # Build messages from conversation_history
            if conversation_history:
                for conv in conversation_history[-10:]:
                    messages.append({
                        'content': conv['user_message'],
                        'author_id': user_id,
                        'author_name': user_name,
                        'timestamp': message.created_at.isoformat()
                    })
                    messages.append({
                        'content': conv['ai_response'],
                        'author_id': str(bot.user.id),
                        'author_name': bot.user.name,
                        'timestamp': message.created_at.isoformat()
                    })

            # Add the current message and describe the attachments
            attachment_descriptions = []
            for attachment in message.attachments:
                attachment_descriptions.append(f"{attachment.filename} ({attachment.url})")

            content = f"{message.content}\nAttachments: {', '.join(attachment_descriptions)}"

            messages.append({
                'content': content,
                'author_id': user_id,
                'author_name': user_name,
                'timestamp': message.created_at.isoformat()
            })

            # Call the agent to process the messages
            result = await bot.message_processor.process_messages(channel_info, messages)

            # Get the agent's action
            action_result = result.get('action')

            if action_result and action_result.get('content'):
                response_content = action_result['content']['action']['content']
                await send_long_message(message.channel, response_content)
                logging.info(f"Sent response to {user_name} (ID: {user_id}): {response_content[:1000]}...")

                # Save interaction to memory and conversation history
                memory_text = f"User {user_name} sent files: {', '.join(attachment_descriptions)}\nYour response: {response_content}"
                memory_index.add_memory(user_id, memory_text)

                cache_manager.append_to_conversation(user_id, {
                    'user_name': user_name,
                    'user_message': content,
                    'ai_response': response_content
                })

                log_to_jsonl({
                    'event': 'file_interaction',
                    'timestamp': datetime.now().isoformat(),
                    'user_id': user_id,
                    'user_name': user_name,
                    'channel': message.channel.name if hasattr(message.channel, 'name') else 'DM',
                    'user_message': content,
                    'ai_response': response_content
                })

            else:
                logging.error("No action content received from the agent")
                await message.channel.send("I'm sorry, I couldn't process those files.")

    except Exception as e:
        error_message = f"An error occurred while analyzing files: {str(e)}"
        await message.channel.send(error_message)
        logging.error(f"Error in file analysis for {user_name} (ID: {user_id}): {str(e)}")

async def send_long_message(channel, message, max_length=1800):
    """
    Splits and sends a long message into smaller chunks to Discord, preserving original formatting.
    
    Args:
        channel: The Discord channel to send the message to
        message: The full message text to be sent
        max_length: Maximum length for each chunk (default 1800 to stay under Discord's limit)
    """
    # First split into segments that are either sentences or newlines
    segments = []
    current_text = ""
    
    # Iterate through message character by character to properly handle consecutive newlines
    for char in message:
        if char == '\n':
            if current_text:
                segments.append(('text', current_text))
                current_text = ""
            segments.append(('newline', '\n'))
        else:
            current_text += char
    
    # Add any remaining text
    if current_text:
        segments.append(('text', current_text))
    
    # Now build chunks while preserving formatting
    chunks = []
    current_chunk = ""
    
    for type_, content in segments:
        if type_ == 'newline':
            # Always add newlines if there's room
            if len(current_chunk) + 1 <= max_length:
                current_chunk += content
            else:
                chunks.append(current_chunk)
                current_chunk = content
        else:
            # Split text into sentences
            sentences = sent_tokenize(content)
            for sentence in sentences:
                sentence = sentence.strip()
                # Add proper spacing based on context
                if current_chunk and not current_chunk.endswith('\n'):
                    sentence = ' ' + sentence
                
                # Check if this sentence fits
                if len(current_chunk) + len(sentence) <= max_length:
                    current_chunk += sentence
                else:
                    chunks.append(current_chunk)
                    current_chunk = sentence
    
    # Add the final chunk if not empty
    if current_chunk:
        chunks.append(current_chunk)
    
    # Send each chunk
    for chunk in chunks:
        await channel.send(chunk)

def truncate_middle(text, max_tokens=256):
    """
    Truncates text to a maximum number of tokens while preserving content from both ends.
    
    Args:
        text (str): The input text to truncate
        max_tokens (int, optional): Maximum number of tokens to keep. Defaults to 256.
        
    Returns:
        str: The truncated text with ellipsis (...) in the middle if truncation was needed,
             or the original text if it was already within the token limit.
             
    The function preserves roughly equal amounts of tokens from the start and end of the text,
    placing an ellipsis in the middle to indicate truncation. It uses the cl100k_base tokenizer
    from tiktoken for token counting and manipulation.
    """
    tokenizer = tiktoken.get_encoding("cl100k_base")
    tokens = tokenizer.encode(text)
    
    if len(tokens) <= max_tokens:
        return text
    
    keep_tokens = max_tokens - 3  # Account for the ellipsis (...) in the middle
    side_tokens = keep_tokens // 2
    end_tokens = side_tokens + (keep_tokens % 2)  # Add the remainder to the end if odd
    
    truncated_tokens = tokens[:side_tokens] + [tokenizer.encode('...')[0]] + tokens[-end_tokens:]
    return tokenizer.decode(truncated_tokens)

def setup_bot():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    bot = commands.Bot(command_prefix='!', intents=intents, status=discord.Status.online)  

    # Initialize with specific cache types
    user_memory_index = UserMemoryIndex('user_memory_index')
    repo_index = RepoIndex('repo_index')  # Ensure this is properly defined
    cache_manager = CacheManager('conversation_history')  # Keep existing name for compatibility
    github_repo = GitHubRepo(GITHUB_TOKEN, REPO_NAME)

    # Load prompt formats and system prompts if needed elsewhere
    with open(os.path.join(script_dir, 'prompts', 'prompt_formats.yaml'), 'r') as file:
        prompt_formats = yaml.safe_load(file)

    with open(os.path.join(script_dir, 'prompts', 'system_prompts.yaml'), 'r') as file:
        system_prompts = yaml.safe_load(file)

    # Add this variable to store the current persona intensity
    bot.persona_intensity = DEFAULT_PERSONA_INTENSITY

    # Initialize cache managers for different purposes
    conversation_cache = CacheManager('conversation_history')
    file_cache = CacheManager('file_cache')
    prompt_cache = CacheManager('prompt_cache')

    # Store cache managers on the bot instance for access in commands
    bot.cache_managers = {
        'conversation': conversation_cache,
        'file': file_cache,
        'prompt': prompt_cache
    }

    # Store other necessary objects on the bot instance
    bot.user_memory_index = user_memory_index
    bot.repo_index = repo_index
    bot.cache_manager = cache_manager
    bot.github_repo = github_repo
    bot.prompt_formats = prompt_formats
    bot.system_prompts = system_prompts

    # Initialize the MessageProcessor with the bot instance
    bot.message_processor = MessageProcessor(bot)

    # Initialize message cache for accumulating messages
    bot.message_cache = {}

    @bot.event
    async def on_ready():
        logging.info(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
        logging.info('------')
        log_to_jsonl({
            'event': 'bot_ready',
            'timestamp': datetime.now().isoformat(),
            'bot_name': bot.user.name,
            'bot_id': bot.user.id
        })

        # Now that the bot is ready, set bot_id in MessageProcessor
        bot.message_processor.bot_id = str(bot.user.id)

        # Set up the agent asynchronously
        await bot.message_processor.setup_agent()

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return

        # Check if the message is a command
        ctx = await bot.get_context(message)
        if ctx.valid:
            await bot.invoke(ctx)
            return

        # Handle direct messages or mentions
        if isinstance(message.channel, discord.DMChannel) or bot.user in message.mentions:
            if message.attachments:
                attachment = message.attachments[0]
                if attachment.size <= 1000000:  # 1MB limit
                    try:
                        await process_files(
                            message=message,
                            memory_index=bot.user_memory_index,
                            cache_manager=bot.cache_manager,
                            bot=bot,
                            user_message=message.content
                        )
                    except Exception as e:
                        await message.channel.send(f"Error processing file: {str(e)}")
                else:
                    await message.channel.send("File is too large. Please upload a file smaller than 1 MB.")
            else:
                await process_message(
                    message=message,
                    memory_index=bot.user_memory_index,
                    cache_manager=bot.cache_manager,
                    bot=bot
                )
        else:
            # Accumulate messages from other channels
            channel_id = message.channel.id
            if not hasattr(bot, 'message_cache'):
                bot.message_cache = {}

            if channel_id not in bot.message_cache:
                bot.message_cache[channel_id] = []

            bot.message_cache[channel_id].append({
                "content": message.content,
                "author_id": str(message.author.id),
                "author_name": message.author.name,
                "timestamp": message.created_at.isoformat()
            })

            # Keep the cache size limited per channel
            if len(bot.message_cache[channel_id]) > 20:
                bot.message_cache[channel_id].pop(0)

            # If the number of messages accumulated reaches a threshold, process them
            if len(bot.message_cache[channel_id]) >= 10:
                # Process the messages through the agent
                channel_info = {
                    "id": str(message.channel.id),
                    "name": message.channel.name
                }

                # Process the messages using the MessageProcessor
                results = await bot.message_processor.process_messages(channel_info, bot.message_cache[channel_id], message_type="auto")

                action_result = results.get('action')

                if action_result and action_result.get('content'):
                    decision = action_result['content'].get('decision', 'hold')
                    response_content = action_result['content']['action']['content']
                    
                    if decision.lower() == 'post':
                        await message.channel.send(response_content)
                        logging.info(f"Sent response based on accumulated messages in channel {channel_info['name']}")
                    else:
                        logging.info(f"Holding response for channel {channel_info['name']} based on decision: {decision}")
                else:
                    logging.error("Message processing failed")

                # Clear the message cache for this channel
                bot.message_cache[channel_id] = []

    @bot.command(name='persona')
    async def set_persona_intensity(ctx, intensity: int = None):
        """Set or get the AI's persona intensity (0-100). The intensity can be steered through in context prompts and it also adjusts the temperature of the API calls."""
        if intensity is None:
            await ctx.send(f"Current persona intensity is {bot.persona_intensity}%.")
            logging.info(f"Persona intensity queried by user {ctx.author.name} (ID: {ctx.author.id})")
        elif 0 <= intensity <= 100:
            bot.persona_intensity = intensity
            update_temperature(intensity)  # Update the temperature
            await ctx.send(f"Persona intensity set to {intensity}%.")
            logging.info(f"Persona intensity set to {intensity}% by user {ctx.author.name} (ID: {ctx.author.id})")
        else:
            await ctx.send("Please provide a valid intensity between 0 and 100.")

    @bot.command(name='add_memory')
    async def add_memory(ctx, *, memory_text):
        """Add a new memory to the AI."""
        bot.user_memory_index.add_memory(str(ctx.author.id), memory_text)
        await ctx.send("Memory added successfully.")
        log_to_jsonl({
            'event': 'add_memory',
            'timestamp': datetime.now().isoformat(),
            'user_id': str(ctx.author.id),
            'user_name': ctx.author.name,
            'memory_text': memory_text
        })

    @bot.command(name='clear_memories')
    async def clear_memories(ctx):
        """Clear all memories of the invoking user."""
        user_id = str(ctx.author.id)
        bot.user_memory_index.clear_user_memories(user_id)
        await ctx.send("Your memories have been cleared.")
        log_to_jsonl({
            'event': 'clear_user_memories',
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'user_name': ctx.author.name
        })

    @bot.command(name='analyze_file')
    async def analyze_file(ctx):
        """Analyze an uploaded file."""
        if not ctx.message.attachments:
            await ctx.send("Please upload a file to analyze.")
            return

        attachment = ctx.message.attachments[0]
        
        if attachment.size > 1000000:  # 1 MB limit
            await ctx.send("File is too large. Please upload a file smaller than 1 MB.")
            return

        try:
            await process_files(
                message=ctx.message,
                memory_index=bot.user_memory_index,
                cache_manager=bot.cache_manager,
                bot=bot,
                user_message=ctx.message.content
            )
        except Exception as e:
            await ctx.send(f"Error processing file: {str(e)}")

    # Other commands remain unchanged, but you may need to adjust them similarly to use the agent.

    return bot

if __name__ == "__main__":
    #parser = argparse.ArgumentParser(description='Run the Discord bot with selected API and model')
    #parser.add_argument('--api', choices=['ollama', 'openai', 'anthropic', 'vllm'], default='ollama', help='Choose the API to use (default: ollama)')
    #parser.add_argument('--model', type=str, help='Specify the model to use. If not provided, defaults will be used based on the API.')
    #args = parser.parse_args()

    # Removed initialize_api_client(args) since we are using the agent framework

    bot = setup_bot()
    bot.run(TOKEN)
