import asyncio
from asyncio.log import logger
from collections import defaultdict
from datetime import datetime, timezone
import json
import logging
import os

import discord
from market_agents.memory.memory import MemoryObject
from market_agents.orchestrators.discord_orchestrator import MessageProcessor
import yaml

class ChannelSummarizer:
    """
    A class for summarizing Discord channel messages and threads.

    This version:
    - Accepts the full `ctx` for the `summarize_channel` command
    - Passes the real command-invoker's ID/name to _process_chunks
    - Uses real Discord message author_id/author_name for each message
    """

    def __init__(self, bot, prompt_formats, system_prompts, max_entries=50):
        """
        Args:
            bot: The Discord bot instance
            prompt_formats (dict): Dictionary of prompt templates
            system_prompts (dict): Dictionary of system prompt templates
            max_entries (int, optional): Maximum messages to analyze. Defaults to 50.
        """
        self.bot = bot
        self.max_entries = max_entries
        self.prompt_formats = prompt_formats
        self.system_prompts = system_prompts

    async def summarize_channel(self, ctx):
        """Summarize messages from the current channel and its threads."""
        channel = ctx.channel
        if not channel:
            return "Channel not found."

        requester_id = str(ctx.author.id)
        requester_name = ctx.author.name

        # Collect channel + thread messages
        main_messages, thread_map = await self._collect_messages(channel)

        # Build overall summary text
        summary = (
            f"**Summary of #{channel.name}, requested by {requester_name} (ID: {requester_id})**\n\n"
        )
        summary += await self._summarize_messages(
            main_messages,
            context_label="Main Channel",
            channel=channel,
            requester_id=requester_id,
            requester_name=requester_name
        )

        # Summarize each thread
        for thread_id, thread_messages in thread_map.items():
            thread = channel.get_thread(thread_id)
            if thread:
                thread_summary = await self._summarize_messages(
                    thread_messages,
                    context_label=f"Thread: {thread.name}",
                    channel=thread,
                    requester_id=requester_id,
                    requester_name=requester_name
                )
                summary += f"\n{thread_summary}"

        # Store summary in memory_store - FIX: Add await here
        task = asyncio.create_task(self.bot.memory_store.store_memory(MemoryObject(
            agent_id=str(self.bot.user.id),
            cognitive_step="channel_summary",
            content=summary,
            metadata={
                "channel_id": str(channel.id),
                "user_id": requester_id,
                "user_name": requester_name,
            }
        )))

        return summary

    async def _collect_messages(self, channel):
        """
        Helper to collect main channel messages + thread messages.
        Returns (main_messages, thread_map).
        """
        main_messages = []
        thread_map = defaultdict(list)

        async for msg in channel.history(limit=self.max_entries):
            if msg.thread:
                thread_map[msg.thread.id].append(msg)
            else:
                main_messages.append(msg)

        return main_messages, thread_map

    async def _summarize_messages(
        self,
        messages,
        context_label,
        channel,
        requester_id,
        requester_name
    ):
        """
        Generate a summary of a set of Discord messages.

        Args:
            messages (list[discord.Message]): The channel messages to analyze
            context_label (str): e.g., "Main Channel" or "Thread: MyThread"
            channel (discord.TextChannel|discord.Thread): The channel/thread object
            requester_id (str): ID of the user who ran !summarize
            requester_name (str): Name of the user who ran !summarize

        Returns:
            str: A formatted summary of the messages including a content summary.
        """
        user_message_counts = defaultdict(int)
        file_types = defaultdict(int)
        content_chunks = []

        for msg in messages:
            user_message_counts[msg.author.name] += 1
            for attachment in msg.attachments:
                file_type = attachment.filename.split('.')[-1].lower()
                file_types[file_type] += 1
            content_chunks.append(f"{msg.author.name}: {msg.content}")

        # Basic stats
        summary = f"{context_label}\nParticipants:\n"
        for user, count in user_message_counts.items():
            summary += f"- {user}: {count} messages\n"

        if file_types:
            summary += "\nShared Files:\n"
            for ftype, count in file_types.items():
                summary += f"- {ftype}: {count} files\n"

        # Get key points list from LLM
        key_points = await self._process_chunks(
            messages=messages,
            context_label=context_label,
            channel=channel,
            requester_id=requester_id,
            requester_name=requester_name
        )

        print(key_points)

        # Format the key points as bullet points
        if key_points:
            content_summary = "\n".join(f"- {point}" for point in key_points)
        else:
            content_summary = "No summary produced."
        summary += f"\nContent Summary:\n{content_summary}\n"

        return summary

    async def _process_chunks(
        self,
        messages,
        context_label,
        channel,
        requester_id,
        requester_name
    ):
        """
        Process messages via the agent's message_processor and return key_points.

        Args:
            messages (list[discord.Message]): The actual channel messages.
            context_label (str): Label describing the message source.
            channel (discord.TextChannel|discord.Thread): The channel or thread.
            requester_id (str): ID of the user who invoked !summarize.
            requester_name (str): Name of the user who invoked !summarize.

        Returns:
            list[str]: A list of summary bullet points returned by the LLM.
        """
        reversed_msgs = list(reversed(messages))

        # Build the payload with real author data
        messages_payload = []
        for msg in messages:
                messages_payload.append({
                    'content': msg.content,
                    'author_id': str(msg.author.id),
                    'author_name': msg.author.name,
                    'timestamp': msg.created_at.isoformat(),
                    'message_type': 'channel_message'
                })

        # Add the summary command as the current message
        messages_payload.append({
            'content': f'Generate channel summary for {context_label}',
            'author_id': requester_id,
            'author_name': requester_name,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'message_type': 'current_user_message'
        })

        channel_info = {
            "id": str(channel.id),
            "name": getattr(channel, "name", f"Thread-{channel.id}")
        }

        user_info = {
            "user_id": requester_id,
            "user_name": requester_name
        }

        try:
            result = await self.bot.message_processor.process_messages(
                channel_info=channel_info,
                messages=messages_payload,
                message_type="summary",
                user_info=user_info
            )
            
            print(result)

            action_result = result.get("action")
            

            if action_result and action_result.get("action"):
                content = action_result["action"].get("content", {})
                key_points = content.get("key_points", [])
                return key_points
            else:
                logging.error("No action result returned from message_processor")
                return []
        except Exception as e:
            logging.error(f"Error in generating summary: {str(e)}")
            return []
