import discord
from discord.ext import commands

import logging
import os
import tiktoken
import json
from datetime import datetime
from collections import defaultdict, Counter
import yaml
import nltk

from delphi.tools.discord_summarizer import ChannelSummarizer
nltk.download('punkt', quiet=True)
from nltk.tokenize import sent_tokenize

from delphi.bot_config import *
from market_agents.orchestrators.discord_orchestrator import MessageProcessor
from delphi.knowledge_base.github_kb import GitHubKnowledgeBase

from market_agents.memory.config import load_config_from_yaml
from market_agents.memory.setup_db import DatabaseConnection
from market_agents.memory.embedding import MemoryEmbedder
from market_agents.memory.memory import MarketMemory, MemoryObject
from market_agents.memory.vector_search import MemoryRetriever

script_dir = os.path.dirname(os.path.abspath(__file__))

# Set up logging
log_level = os.getenv('LOGLEVEL', 'INFO')
logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

def log_to_jsonl(data):
    with open('bot_log.jsonl', 'a') as f:
        json.dump(data, f)
        f.write('\n')

def update_temperature(intensity):
    global TEMPERATURE
    TEMPERATURE = intensity / 100.0
    logging.info(f"Updated temperature to {TEMPERATURE}")

async def process_message(message, memory_store, memory_query, bot, is_command=False):
    user_id = str(message.author.id)
    user_name = message.author.name
    agent_id = str(bot.user.id)

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
            channel_info = {
                'id': str(message.channel.id),
                'name': message.channel.name if hasattr(message.channel, 'name') else 'Direct Message'
            }
            user_info = {
                "user_id": user_id,
                "user_name": user_name
            }

            # Retrieve recent conversation from MarketMemory
            recent_interactions = memory_store.get_memories(
                metadata_filters={'user_id': user_id},
                cognitive_step="conversation",
                limit=10
            )
            print("\nMemory Search Result:")
            memory_strings = [f"Memory {i+1}:\n{mem.content}" for i, mem in enumerate(recent_interactions)]
            print("\033[94m" + "\n\n".join(memory_strings) + "\033[0m")

            messages = []
            for interaction in recent_interactions:
                # Parse the JSON content string
                conversation = json.loads(interaction.content)
                
                if 'user_message' in conversation:
                    messages.append({
                        'content': conversation['user_message'],
                        'author_id': user_id,
                        'author_name': user_name,
                        'timestamp': message.created_at.isoformat()
                    })
                if 'ai_response' in conversation:
                    messages.append({
                        'content': conversation['ai_response'],
                        'author_id': str(bot.user.id),
                        'author_name': bot.user.name,
                        'timestamp': message.created_at.isoformat()
                    })

            # Add recent channel messages (context)
            async for msg in message.channel.history(limit=10, oldest_first=True):
                messages.append({
                    'content': msg.content,
                    'author_id': str(msg.author.id),
                    'author_name': msg.author.name,
                    'timestamp': msg.created_at.isoformat()
                })

            # Append the current user message
            messages.append({
                'content': content,
                'author_id': user_id,
                'author_name': user_name,
                'timestamp': message.created_at.isoformat()
            })

            # Call the agent
            result = await bot.message_processor.process_messages(
                channel_info=channel_info,
                messages=messages,
                message_type=None,
                user_info=user_info)
            
            action_result = result.get('action')

            if action_result and action_result.get('content'):
                response_content = action_result['content']['action']['content']
                await send_long_message(message.channel, response_content)
                logging.info(f"Sent response to {user_name} (ID: {user_id}): {response_content[:1000] if response_content else ''}")

                # Store interaction as conversation step
                conversation_record = {
                    "user_message": content,
                    "ai_response": response_content
                }
                memory_store.store_memory(MemoryObject(
                    agent_id=agent_id,
                    cognitive_step="conversation",
                    content=json.dumps(conversation_record),
                    metadata={
                        'user_id': user_id,
                        'user_name': user_name
                    }
                ))

                log_to_jsonl({
                    'event': 'conversation',
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

async def process_files(message, memory_store, memory_query, bot, user_message="", knowledge_base=None, query_mode=False):
    user_id = str(message.author.id)
    user_name = message.author.name
    agent_id = str(bot.user.id)

    logging.info(f"Processing request from {user_name} (ID: {user_id}) in {'query_mode' if query_mode else 'file_mode'}")

    try:
        async with message.channel.typing():
            channel_info = {
                'id': str(message.channel.id),
                'name': message.channel.name if hasattr(message.channel, 'name') else 'Direct Message'
            }

            # Retrieve recent interactions
            recent_interactions = memory_store.get_memories(
                metadata_filters={'user_id': user_id},
                limit=10
            )

            messages = []
            for interaction in recent_interactions:
                conversation_record = json.loads(interaction.content)
                if 'user_message' in conversation_record:
                    messages.append({
                        'content': conversation_record['user_message'],
                        'author_id': user_id,
                        'author_name': user_name,
                        'timestamp': message.created_at.isoformat()
                    })
                if 'ai_response' in conversation_record:
                    messages.append({
                        'content': conversation_record['ai_response'],
                        'author_id': str(bot.user.id),
                        'author_name': bot.user.name,
                        'timestamp': message.created_at.isoformat()
                    })

            if query_mode:
                # Query mode: we assume user_message is a query to the knowledge base
                if not knowledge_base:
                    raise ValueError("No knowledge_base provided for query_mode")

                # NEW: Provide the KB's table_prefix to the memory_query
                kb_results = memory_query.search_knowledge_base(knowledge_base.table_prefix, user_message, top_k=10)
                # Add kb results as context
                for i, res in enumerate(kb_results, 1):
                    chunk_text = f"[Repo Chunk {i} | Sim: {res.similarity:.3f}]\n{res.text}"
                    messages.append({
                        'content': chunk_text,
                        'author_id': str(bot.user.id),
                        'author_name': 'SystemContext',
                        'timestamp': message.created_at.isoformat()
                    })
                
                content = user_message
            else:
                # File mode
                if not message.attachments:
                    raise ValueError("No attachments found in message")

                attachment_descriptions = []
                for attachment in message.attachments:
                    if attachment.size > 1000000:
                        await message.channel.send("File is too large. Please upload a file smaller than 1 MB.")
                        return
                    attachment_descriptions.append(f"{attachment.filename} ({attachment.url})")

                content = f"{message.content}\nAttachments: {', '.join(attachment_descriptions)}"

            # Add the current user message or query
            messages.append({
                'content': content,
                'author_id': user_id,
                'author_name': user_name,
                'timestamp': message.created_at.isoformat()
            })

            # Process with the agent
            result = await bot.message_processor.process_messages(channel_info, messages)
            action_result = result.get('action')

            if action_result and action_result.get('content'):
                response_content = action_result['content']['action']['content']
                await send_long_message(message.channel, response_content)
                logging.info(f"Sent response to {user_name} (ID: {user_id}): {response_content[:1000]}...")

                # Store interaction
                conversation_record = {
                    "user_message": content,
                    "ai_response": response_content
                }
                memory_store.store_memory(MemoryObject(
                    agent_id=agent_id,
                    cognitive_step="conversation" if query_mode else "file_analysis",
                    content=json.dumps(conversation_record),
                    metadata={
                        'user_id': user_id,
                        'user_name': user_name
                    }
                ))

                log_event = 'repo_query' if query_mode else 'file_analysis'
                log_to_jsonl({
                    'event': log_event,
                    'timestamp': datetime.now().isoformat(),
                    'user_id': user_id,
                    'user_name': user_name,
                    'channel': message.channel.name if hasattr(message.channel, 'name') else 'DM',
                    'user_message': content,
                    'ai_response': response_content
                })
            else:
                logging.error("No action content received from the agent")
                await message.channel.send("I'm sorry, I couldn't process that request.")

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        await message.channel.send(error_message)
        logging.error(f"Error in processing for {user_name} (ID: {user_id}): {str(e)}")


async def send_long_message(channel, message, max_length=1800):
    segments = []
    current_text = ""

    for char in message:
        if char == '\n':
            if current_text:
                segments.append(('text', current_text))
                current_text = ""
            segments.append(('newline', '\n'))
        else:
            current_text += char

    if current_text:
        segments.append(('text', current_text))

    chunks = []
    current_chunk = ""

    for type_, content in segments:
        if type_ == 'newline':
            if len(current_chunk) + 1 <= max_length:
                current_chunk += content
            else:
                chunks.append(current_chunk)
                current_chunk = content
        else:
            sentences = sent_tokenize(content)
            for sentence in sentences:
                sentence = sentence.strip()
                if current_chunk and not current_chunk.endswith('\n'):
                    sentence = ' ' + sentence

                if len(current_chunk) + len(sentence) <= max_length:
                    current_chunk += sentence
                else:
                    chunks.append(current_chunk)
                    current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    for chunk in chunks:
        await channel.send(chunk)

def truncate_middle(text, max_tokens=256):
    tokenizer = tiktoken.get_encoding("cl100k_base")
    tokens = tokenizer.encode(text)

    if len(tokens) <= max_tokens:
        return text

    keep_tokens = max_tokens - 3
    side_tokens = keep_tokens // 2
    end_tokens = side_tokens + (keep_tokens % 2)

    truncated_tokens = tokens[:side_tokens] + [tokenizer.encode('...')[0]] + tokens[-end_tokens:]
    return tokenizer.decode(truncated_tokens)

def setup_bot(persona=None, llm_config=None):
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    bot = commands.Bot(command_prefix='!', intents=intents, status=discord.Status.online)

    # Initialize MarketMemory & Query
    config_path = os.path.join("market_agents/market_agents/memory", "memory_config.yaml")

    config = load_config_from_yaml(config_path)
    db_conn = DatabaseConnection(config)
    db_conn.connect()
    embedding_service = MemoryEmbedder(config)
    
    bot.memory_store = MarketMemory(config, db_conn, embedding_service, agent_id="discord_agent")
    bot.memory_query = MemoryRetriever(config, db_conn, embedding_service)

    prompt_formats_path = os.path.join(script_dir, 'prompts', 'prompt_formats.yaml')
    system_prompts_path = os.path.join(script_dir, 'prompts', 'system_prompts.yaml')

    with open(prompt_formats_path, 'r') as file:
        prompt_formats = yaml.safe_load(file)

    with open(system_prompts_path, 'r') as file:
        system_prompts = yaml.safe_load(file)

    bot.persona = persona
    bot.llm_config = llm_config
    bot.persona_intensity = DEFAULT_PERSONA_INTENSITY
    bot.config = config
    bot.db_conn = db_conn
    bot.prompt_formats = prompt_formats
    bot.system_prompts = system_prompts
    bot.message_processor = MessageProcessor(bot)
    bot.message_cache = {}

    @bot.event
    async def on_ready():
        logging.info(f'Logged in as {bot.user.name} (ID: {bot.user.id})')

        # Re-initialize MarketMemory now that we actually know the bot.user.id
        bot.memory_store = MarketMemory(config, db_conn, embedding_service, agent_id=str(bot.user.id))

        kb_name = "market_agents_github"

        bot.github_kb = GitHubKnowledgeBase(config, db_conn, embedding_service, table_prefix=kb_name)

        # Check if repo is already indexed
        bot.db_conn.cursor.execute(f"""
            SELECT COUNT(*) FROM {kb_name}_knowledge_objects
            WHERE metadata->>'source' = 'github'
        """)
        count = bot.db_conn.cursor.fetchone()[0]

        if count == 0:
            logging.info("No GitHub repository indexed. Starting initial indexing...")
            try:
                await bot.github_kb.ingest_from_github_repo(
                    token=GITHUB_TOKEN,
                    repo_name=REPO_NAME,
                    max_depth=2,
                    branch='main'
                )
                logging.info("Repository indexed successfully!")
            except Exception as e:
                logging.error(f"Error indexing repository: {str(e)}")
        else:
            logging.info(f"Found {count} existing GitHub documents in knowledge base")

        logging.info('------')
        log_to_jsonl({
            'event': 'bot_ready',
            'timestamp': datetime.now().isoformat(),
            'bot_name': bot.user.name,
            'bot_id': bot.user.id
        })
        bot.message_processor.bot_id = str(bot.user.id)
        await bot.message_processor.setup_agent(bot.persona, bot.llm_config)

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return
        
        bot.db_conn.ensure_connection()

        ctx = await bot.get_context(message)
        if ctx.valid:
            await bot.invoke(ctx)
            return

        # If the bot is directly mentioned or in DMs, we process the message
        if isinstance(message.channel, discord.DMChannel) or bot.user in message.mentions:
            if message.attachments:
                attachment = message.attachments[0]
                if attachment.size <= 1000000:
                    try:
                        await process_files(
                            message=message,
                            memory_store=bot.memory_store,
                            memory_query=bot.memory_query,
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
                    memory_store=bot.memory_store,
                    memory_query=bot.memory_query,
                    bot=bot
                )
        else:
            # Auto message accumulation can remain if desired, or removed if not needed
            channel_id = message.channel.id
            if channel_id not in bot.message_cache:
                bot.message_cache[channel_id] = []

            bot.message_cache[channel_id].append({
                "content": message.content,
                "author_id": str(message.author.id),
                "author_name": message.author.name,
                "timestamp": message.created_at.isoformat()
            })

            if len(bot.message_cache[channel_id]) > 20:
                bot.message_cache[channel_id].pop(0)

            if len(bot.message_cache[channel_id]) >= 10:
                channel_info = {
                    "id": str(message.channel.id),
                    "name": message.channel.name
                }
                # This is optional. If we want to store these auto messages as well, we could do similar steps.
                results = await bot.message_processor.process_messages(channel_info, bot.message_cache[channel_id], message_type="auto")
                action_result = results.get('action')
                if action_result and action_result.get('content'):
                    decision = action_result['content'].get('decision', 'hold')
                    response_content = action_result['content'].get('message', '')
                    if decision.lower() == 'post':
                        await message.channel.send(response_content)
                        logging.info(f"Sent response based on accumulated messages in channel {channel_info['name']}")
                    else:
                        logging.info(f"Holding response for channel {channel_info['name']} based on decision: {decision}")
                else:
                    logging.error("Message processing failed")

                bot.message_cache[channel_id] = []

    @bot.command(name='persona')
    async def set_persona_intensity(ctx, intensity: int = None):
        if intensity is None:
            await ctx.send(f"Current persona intensity is {bot.persona_intensity}%.")
            logging.info(f"Persona intensity queried by user {ctx.author.name} (ID: {ctx.author.id})")
        elif 0 <= intensity <= 100:
            bot.persona_intensity = intensity
            update_temperature(intensity)
            await ctx.send(f"Persona intensity set to {intensity}%.")
            logging.info(f"Persona intensity set to {intensity}% by user {ctx.author.name} (ID: {ctx.author.id})")
        else:
            await ctx.send("Please provide a valid intensity between 0 and 100.")

    @bot.command(name='add_memory')
    async def add_memory(ctx, *, memory_text):
        user_id = str(ctx.author.id)
        agent_id = str(bot.user.id)
        
        bot.memory_store.store_memory(MemoryObject(
            agent_id=agent_id,
            cognitive_step="remember",
            content=memory_text,
            metadata={
                'user_id': user_id,
                'user_name': ctx.author.name
            }
        ))
        await ctx.send("Memory added successfully.")
        log_to_jsonl({
            'event': 'add_memory',
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'user_name': ctx.author.name,
            'memory_text': memory_text
        })

    @bot.command(name='clear_memories')
    async def clear_memories(ctx):
        user_id = str(ctx.author.id)
        deleted_count = bot.memory_store.delete_memories(
            metadata_filters={'user_id': user_id}
        )
        await ctx.send(f"Cleared {deleted_count} memories.")
        log_to_jsonl({
            'event': 'clear_user_memories', 
            'timestamp': datetime.now().isoformat(),
            'user_id': user_id,
            'user_name': ctx.author.name,
            'memories_deleted': deleted_count
        })

    @bot.command(name='analyze_file')
    async def analyze_file(ctx):
        if not ctx.message.attachments:
            await ctx.send("Please upload a file to analyze.")
            return

        attachment = ctx.message.attachments[0]

        if attachment.size > 1000000:
            await ctx.send("File is too large. Please upload a file smaller than 1 MB.")
            return

        try:
            await process_files(
                message=ctx.message,
                memory_store=bot.memory_store,
                memory_query=bot.memory_query,
                bot=bot,
                user_message=ctx.message.content
            )
        except Exception as e:
            await ctx.send(f"Error processing file: {str(e)}")

    @bot.command(name='ask_repo')
    async def ask_repo(ctx, *, query: str):
        try:
            await process_files(
                message=ctx.message,
                memory_store=bot.memory_store,
                memory_query=bot.memory_query,
                bot=bot,
                user_message=query,
                knowledge_base=bot.github_kb,
                query_mode=True
            )
        except Exception as e:
            await ctx.send(f"Error processing repo query: {str(e)}")

    @bot.command(name='summarize')
    async def summarize_channel(ctx):
        """
        Summarize the messages in the current channel.
        Usage: !summarize
        """
        try:
            summarizer = ChannelSummarizer(
                bot=bot,
                prompt_formats=bot.prompt_formats,
                system_prompts=bot.system_prompts,
                max_entries=100
            )

            summary_text = await summarizer.summarize_channel(ctx)
            
            await send_long_message(ctx.channel, summary_text)

        except Exception as e:
            await ctx.send(f"Error summarizing channel: {str(e)}")



    return bot

if __name__ == "__main__":
    bot = setup_bot()
    bot.run(TOKEN)
