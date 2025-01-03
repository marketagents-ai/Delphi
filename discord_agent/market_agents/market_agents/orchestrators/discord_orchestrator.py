from datetime import datetime
import os
import yaml
import logging
import json
from pathlib import Path
from dotenv import load_dotenv
import asyncio

from market_agents.memory.memory import MemoryObject
from market_agents.orchestrators.config import settings
from market_agents.agents.market_agent import MarketAgent
from market_agents.inference.message_models import LLMConfig
from market_agents.agents.personas.persona import Persona
from market_agents.environments.environment import MultiAgentEnvironment
from market_agents.environments.mechanisms.discord import (
    DiscordMechanism,
    DiscordActionSpace,
    DiscordObservationSpace,
    DiscordAutoMessage
)

import discord

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MessageProcessor:
    def __init__(self, bot):
        self.bot = bot
        self.bot_id = None
        self.agent = None
        self.environment = None

    async def initialize_bot_id(self):
        """Initialize bot_id once the bot is ready"""
        if self.bot.user:
            self.bot_id = str(self.bot.user.id)
        else:
            raise ValueError("Bot user is not initialized")

    async def setup_agent(self):
        """Initialize the TARS agent with persona and environment"""
        try:
            # Load the specific persona file for the configured bot
            persona_file = settings.bot.personas_dir / f"{settings.bot.name.lower()}.yaml"
            if not persona_file.exists():
                raise ValueError(f"Persona file for {settings.bot.name} not found at {persona_file}")

            # Load the specific persona
            with open(persona_file, 'r') as file:
                persona_data = yaml.safe_load(file)
                agent_persona = Persona(
                    name=persona_data['name'],
                    role=persona_data['role'],
                    persona=persona_data['persona'],
                    objectives=persona_data['objectives'],
                    trader_type=persona_data['trader_type'],
                    communication_style=persona_data['communication_style'],
                    routines=persona_data['routines'],
                    skills=persona_data['skills']
                )

            # Create Discord environment
            discord_mechanism = DiscordMechanism()
            self.environment = MultiAgentEnvironment(
                name="DiscordEnvironment",
                action_space=DiscordActionSpace(),
                observation_space=DiscordObservationSpace(),
                mechanism=discord_mechanism,
                max_steps=1000
            )

            # Configure LLM using settings
            llm_config = LLMConfig(
                client=settings.llm_config.client,
                model=settings.llm_config.model,
                temperature=settings.llm_config.temperature,
                max_tokens=settings.llm_config.max_tokens
            )

            # Create agent
            self.agent = MarketAgent.create(
                agent_id=self.bot_id,
                use_llm=True,
                llm_config=llm_config,
                environments={'discord': self.environment},
                persona=agent_persona,
                econ_agent=None
            )

            logger.info(f"Agent setup completed successfully for {settings.bot.name}")
            return True

        except Exception as e:
            logger.error(f"Error setting up agent: {str(e)}", exc_info=True)
            return False

    async def process_messages(self, channel_info, messages, message_type=None, user_info=None):
        """Process messages through the agent's cognitive functions"""
        try:
            if not messages:
                logger.warning("No messages to process")
                return

            # Update environment state
            environment_info = {
                "bot_id": self.bot_id,
                "channel_id": channel_info["id"],
                "channel_name": channel_info["name"],
                "messages": messages
            }
            self.environment.mechanism.update_state(environment_info)

            metadata = {
                'channel_id': channel_info["id"],
                'channel_name': channel_info["name"]
            }
            if user_info:
                metadata.update({
                    'user_id': user_info['user_id'],
                    'user_name': user_info['user_name']
                })
            
            # Run cognitive functions
            logger.info("Starting agent cognitive functions")

            # Perception
            perception_result = None
            if message_type and message_type == "auto":
                perception_result = await self.agent.perceive('discord')
                logger.info("Perception completed")
                print("\nPerception Result:")
                print("\033[94m" + json.dumps(perception_result, indent=2) + "\033[0m")
                
                # Store perception in memory
                if perception_result:
                    self.bot.memory_store.store_memory(MemoryObject(
                        agent_id=self.bot_id,
                        cognitive_step="perception",
                        content=json.dumps(perception_result),
                        metadata=metadata
                    ))

            # Action Generation
            action_schema = None
            if message_type and message_type == "auto":
                action_schema = DiscordAutoMessage.model_json_schema()
            action_result = await self.agent.generate_action(
                'discord', 
                perception=perception_result,
                action_schema=action_schema
            )
            if message_type and message_type == "auto":
                action_result = {
                    "agent_id": self.bot_id,
                    "action": action_result
                }
            logger.info("Action generation completed")
            print("\nAction Result:")
            print("\033[92m" + json.dumps(action_result, indent=2) + "\033[0m")

            # Store action in memory
            if action_result:
                self.bot.memory_store.store_memory(MemoryObject(
                    agent_id=self.bot_id,
                    cognitive_step="action",
                    content=json.dumps(action_result),
                    metadata=metadata
                ))

            # Update environment state with action result
            if action_result:
                self.environment.mechanism.update_state({
                    "bot_id": self.bot_id,
                    "channel_id": channel_info["id"],
                    "channel_name": channel_info["name"],
                    "messages": messages,
                    "last_action": action_result
                })

            # Create task for reflection to run in parallel
            reflection_task = asyncio.create_task(self._run_reflection(metadata))

            # Return action result immediately
            response = {
                "perception": perception_result,
                "action": action_result,
                "reflection": None
            }

            # Clear messages from mechanism after processing core functions
            self.environment.mechanism.messages = []
            logger.info("Cleared messages from mechanism")

            return response

        except Exception as e:
            logger.error(f"Error processing messages: {str(e)}", exc_info=True)
            return None

    async def _run_reflection(self, metadata):
        """Run reflection as a separate async task"""
        try:
            # Reflection
            reflection_result = await self.agent.reflect('discord')
            logger.info("Reflection completed")
            print("\nReflection Result:")
            print("\033[93m" + json.dumps(reflection_result, indent=2) + "\033[0m")

            # Store reflection in memory
            if reflection_result:
                self.bot.memory_store.store_memory(MemoryObject(
                    agent_id=self.bot_id,
                    cognitive_step="reflection",
                    content=json.dumps(reflection_result),
                    metadata=metadata
                ))

            return reflection_result

        except Exception as e:
            logger.error(f"Error during reflection: {str(e)}", exc_info=True)
            return None

async def run_bot():
    """Run the Discord bot and process messages once connected."""
    # Create a Discord client
    intents = discord.Intents.default()
    intents.messages = True
    intents.guilds = True
    client = discord.Client(intents=intents)

    # Initialize the message processor with the client (bot)
    processor = MessageProcessor(client)
    processing_done = asyncio.Event()

    @client.event
    async def on_ready():
        logger.info(f'Logged in as {client.user.name} (ID: {client.user.id})')

        await processor.initialize_bot_id()
        success = await processor.setup_agent()

        if not success:
            logger.error("Failed to set up agent")
            processing_done.set()
            return

        # Get the channel to test with
        channel = client.get_channel(int(os.getenv('DISCORD_CHANNEL_ID')))

        if channel:
            # Get channel info
            channel_info = {
                "id": str(channel.id),
                "name": channel.name
            }
            
            # Fetch messages
            messages = []
            async for msg in channel.history(limit=10):
                messages.append({
                    "content": msg.content,
                    "author_id": str(msg.author.id),
                    "author_name": msg.author.name,
                    "timestamp": msg.created_at.isoformat()
                })
            
            print(f"Discord messages: {messages}")

            # Process the messages
            results = await processor.process_messages(channel_info, messages, message_type="auto")
            
            if results:
                logger.info("Message processing test completed successfully")
            else:
                logger.error("Message processing test failed")
        else:
            logger.error("Channel not found")

        # Signal that processing is done
        processing_done.set()

    # Get Discord token
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error("Discord token not found in environment variables")
        return

    # Run the bot
    await client.start(token)

    # Wait until processing is done
    await processing_done.wait()

    # Close the bot connection
    await client.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_bot())
