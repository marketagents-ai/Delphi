import asyncio
import logging
from datetime import datetime
from collections import defaultdict

# Import the ChannelSummarizer from your project
from delphi.tools.discord_summarizer import ChannelSummarizer

# Set up basic logging
logging.basicConfig(level=logging.INFO)

# Dummy classes to simulate Discord structures
class DummyAuthor:
    def __init__(self, id, name):
        self.id = id
        self.name = name

class DummyMessage:
    def __init__(self, content, author, created_at=None, attachments=None, thread=None):
        self.content = content
        self.author = author
        self.created_at = created_at or datetime.utcnow()
        self.attachments = attachments or []
        self.thread = thread

class DummyChannel:
    def __init__(self, id, name, messages=None):
        self.id = id
        self.name = name
        self._messages = messages or []

    async def history(self, limit):
        for msg in self._messages[:limit]:
            yield msg

    def get_thread(self, thread_id):
        return None  # Simplified for testing

class DummyContext:
    def __init__(self, channel, author):
        self.channel = channel
        self.author = author

# Minimal dummy bot with required attributes
class DummyBot:
    def __init__(self):
        self.memory_store = type('DummyMemoryStore', (), {'store_memory': lambda self, mem_obj: None})()
        self.prompt_formats = {}
        self.system_prompts = {}
        self.user = DummyAuthor(id=123456789, name="TestBot")
        self.message_processor = None  # to be assigned later

# Override send_long_message for testing to print the message instead of sending it
async def dummy_send_long_message(channel, message, max_length=1800):
    print("Simulated sending message to channel:", message)

# Dummy MessageProcessor to simulate LLM response
class DummyMessageProcessor:
    async def process_messages(self, channel_info, messages, message_type, user_info):
        # Return a simulated summary response with key_points
        action = {
            "agent_id": "123",
            "action": {
                "sender": user_info["user_id"],
                "content": {
                    "key_points": [
                        "Dummy point 1: Sample summary.",
                        "Dummy point 2: Another insight.",
                        "Dummy point 3: Additional detail."
                    ]
                }
            }
        }

        return {
            "perception": None,
            "action": action,
            "reflection": None
        }

async def main():
    # Create dummy bot and assign a dummy message processor
    dummy_bot = DummyBot()
    dummy_bot.message_processor = DummyMessageProcessor()

    # Set empty dictionaries for prompt formats and system prompts for testing
    dummy_bot.prompt_formats = {}
    dummy_bot.system_prompts = {}

    # Create dummy author, messages, channel, and context
    dummy_author = DummyAuthor(id=987654321, name="TestUser")
    dummy_messages = [
        DummyMessage(content="Hello world!", author=dummy_author),
        DummyMessage(content="Another message", author=dummy_author)
    ]
    dummy_channel = DummyChannel(id=1, name="test-channel", messages=dummy_messages)
    dummy_ctx = DummyContext(channel=dummy_channel, author=dummy_author)

    # Override the global send_long_message used in ChannelSummarizer
    global send_long_message
    send_long_message = dummy_send_long_message

    # Instantiate ChannelSummarizer with the dummy bot and empty prompts
    summarizer = ChannelSummarizer(
        bot=dummy_bot,
        prompt_formats=dummy_bot.prompt_formats,
        system_prompts=dummy_bot.system_prompts,
        max_entries=100
    )

    # Run the summarization
    summary_output = await summarizer.summarize_channel(dummy_ctx)
    print("\n--- Summary Output ---\n", summary_output)

# Execute the test script
if __name__ == "__main__":
    asyncio.run(main())
