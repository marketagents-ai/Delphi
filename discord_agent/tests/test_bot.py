import asyncio
import discord
from unittest.mock import MagicMock, AsyncMock
from contextlib import asynccontextmanager
from discord_agent.discord_bot import setup_bot, process_message, process_files, send_long_message, truncate_middle, update_temperature

# Add this helper class for mocking async context managers
class AsyncContextManagerMock:
    async def __aenter__(self):
        return None
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None

async def test_process_message():
    """Test message processing functionality"""
    print("\n=== Testing Message Processing ===")
    
    # Create mock message with proper async context manager
    mock_message = AsyncMock()
    mock_message.author.id = "123456789"
    mock_message.author.name = "TestUser"
    mock_message.content = "Hello bot!"
    mock_message.channel.name = "test-channel"
    mock_message.created_at.isoformat.return_value = "2024-01-01T00:00:00"
    # Fix the typing() context manager
    mock_message.channel.typing.return_value = AsyncContextManagerMock()
    
    # Create mock bot and components
    bot = setup_bot()
    memory_index = bot.user_memory_index
    cache_manager = bot.cache_manager
    
    try:
        # Test process_message
        await process_message(mock_message, memory_index, cache_manager, bot)
        print("✓ process_message executed successfully")
    except Exception as e:
        print(f"✗ process_message failed: {str(e)}")

async def test_process_files():
    """Test file processing functionality"""
    print("\n=== Testing File Processing ===")
    
    # Create mock message with proper async context manager
    mock_message = AsyncMock()
    mock_message.author.id = "123456789"
    mock_message.author.name = "TestUser"
    mock_message.content = "Check this file"
    mock_message.channel.name = "test-channel"
    mock_message.created_at.isoformat.return_value = "2024-01-01T00:00:00"
    # Fix the typing() context manager
    mock_message.channel.typing.return_value = AsyncContextManagerMock()
    
    # Mock attachment
    mock_attachment = AsyncMock()
    mock_attachment.filename = "test.txt"
    mock_attachment.url = "http://test.com/test.txt"
    mock_attachment.size = 100
    mock_message.attachments = [mock_attachment]
    
    # Create mock bot and components
    bot = setup_bot()
    memory_index = bot.user_memory_index
    cache_manager = bot.cache_manager
    
    try:
        # Test process_files
        await process_files(mock_message, memory_index, cache_manager, bot)
        print("✓ process_files executed successfully")
    except Exception as e:
        print(f"✗ process_files failed: {str(e)}")

def test_bot_setup():
    """Test bot setup and print key attributes"""
    print("\n=== Testing Bot Setup ===")
    
    # Create bot instance
    bot = setup_bot()
    print(f"Bot created with name: {bot.user if bot.user else 'Not logged in'}")
    
    # Test temperature update
    try:
        update_temperature(50)
        print("✓ Temperature update successful")
    except Exception as e:
        print(f"✗ Temperature update failed: {str(e)}")
    
    # Test send_long_message
    async def test_send():
        mock_channel = AsyncMock()
        await send_long_message(mock_channel, "Test message " * 100)
    try:
        asyncio.run(test_send())
        print("✓ send_long_message executed successfully")
    except Exception as e:
        print(f"✗ send_long_message failed: {str(e)}")
    
    # Test truncate_middle
    try:
        result = truncate_middle("This is a very long message that needs to be truncated" * 10)
        print("✓ truncate_middle executed successfully")
    except Exception as e:
        print(f"✗ truncate_middle failed: {str(e)}")
    
    # Print key attributes
    print(f"\nCommand prefix: {bot.command_prefix}")
    print(f"Message content intent enabled: {bot.intents.message_content}")
    print(f"Members intent enabled: {bot.intents.members}")
    print(f"Default persona intensity: {bot.persona_intensity}")
    
    # Print available caches
    print("\nInitialized caches:")
    for cache_name, cache in bot.cache_managers.items():
        print(f"- {cache_name}")
    
    # Print key components
    print("\nKey components:")
    print(f"- User memory index: {bot.user_memory_index.__class__.__name__}")
    print(f"- Cache manager: {bot.cache_manager.__class__.__name__}")
    print(f"- Message processor: {bot.message_processor.__class__.__name__}")
    
    # Print command list
    print("\nRegistered commands:")
    for command in bot.commands:
        print(f"- !{command.name}: {command.help if command.help else 'No help text'}")

if __name__ == "__main__":
    test_bot_setup()
    asyncio.run(test_process_message())
    asyncio.run(test_process_files())
