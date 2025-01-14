from datetime import datetime
import os
import yaml
import logging
import json
import asyncio

from pathlib import Path
from dotenv import load_dotenv

from market_agents.agents.market_agent import MarketAgent
from market_agents.agents.personas.persona import Persona
from market_agents.inference.message_models import LLMConfig
from market_agents.environments.environment import MultiAgentEnvironment
from market_agents.environments.mechanisms.discord import (
    DiscordMechanism,
    DiscordActionSpace,
    DiscordObservationSpace,
    DiscordAutoMessage,
    ChannelSummary
)

from market_agents.orchestrators.config import settings

logger = logging.getLogger(__name__)

class MessageProcessor:
    def __init__(self, bot):
        self.bot = bot
        self.bot_id = None
        self.agent = None
        self.environment = None

    async def initialize_bot_id(self):
        """Initialize bot_id once the bot is ready."""
        if self.bot.user:
            self.bot_id = str(self.bot.user.id)
        else:
            raise ValueError("Bot user is not initialized")

    async def setup_agent(self, persona=None, llm_config=None):
        """
        Initialize the TARS agent with persona and environment.
        Must include memory_config & db_conn to MarketAgent.create.
        """
        try:
            if persona:
                if isinstance(persona, dict):
                    agent_persona = Persona(
                        name=persona.get('name'),
                        role=persona.get('role'),
                        persona=persona.get('persona', '')
                    )
                else:
                    agent_persona = persona
            else:
                # Load the specific persona file for the configured bot
                persona_file = settings.bot.personas_dir / f"{settings.bot.name.lower()}.yaml"
                if not persona_file.exists():
                    raise ValueError(f"Persona file for {settings.bot.name} not found at {persona_file}")

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

            # Create a Discord environment
            discord_mechanism = DiscordMechanism()
            self.environment = MultiAgentEnvironment(
                name="DiscordEnvironment",
                action_space=DiscordActionSpace(),
                observation_space=DiscordObservationSpace(),
                mechanism=discord_mechanism,
                max_steps=1000
            )

            # LLMConfig
            if llm_config:
                llm_config = LLMConfig(
                    client=llm_config.client.value,
                    model=llm_config.model,
                    temperature=llm_config.temperature,
                    max_tokens=llm_config.max_tokens
                )
                print(f"Setupbot llm config:\n{llm_config.model_dump_json()}")
            else:
                # Use defaults from your settings
                llm_config = LLMConfig(
                    client=settings.llm_config.client,
                    model=settings.llm_config.model,
                    temperature=settings.llm_config.temperature,
                    max_tokens=settings.llm_config.max_tokens
                )

            # Create the MarketAgent
            self.agent = MarketAgent.create(
                memory_config=self.bot.config,
                db_conn=self.bot.db_conn,
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
        try:
            if not messages:
                logger.warning("No messages to process")
                return

            # Find the current message
            current_message = next(
                (msg for msg in messages if msg['message_type'] == 'current_user_message'),
                messages[-1]
            )

            # Set the current message as the agent's task
            self.agent.task = current_message['content']
            logger.info(f"Set agent task to: {self.agent.task}")

            # Update environment state
            environment_info = {
                "bot_id": self.bot_id,
                "channel_id": channel_info["id"],
                "channel_name": channel_info["name"],
                "messages": messages,
                "current_message": current_message
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

            # Process through cognitive pipeline
            perception_result = await self.agent.perceive('discord')
            logger.info("Perception completed")
            print("\nPerception Result:")
            print("\033[94m" + json.dumps(perception_result, indent=2) + "\033[0m")

            # Generate action
            action_schema = None
            if message_type == "auto":
                action_schema = DiscordAutoMessage.model_json_schema()
            elif message_type == "summary":
                action_schema = ChannelSummary.model_json_schema()

            action_result = await self.agent.generate_action(
                environment_name='discord',
                perception=perception_result,
                return_prompt=False,
                structured_tool=False,
                action_schema=action_schema
            )
            
            # Clear the task after processing
            self.agent.task = None

            # Reflection runs in parallel
            reflection_task = asyncio.create_task(self._run_reflection())

            response = {
                "perception": perception_result,
                "action": action_result,
                "reflection": None
            }

            self.environment.mechanism.messages = []
            logger.info("Cleared messages from mechanism")

            return response

        except Exception as e:
            logger.error(f"Error processing messages: {str(e)}", exc_info=True)
            return None

    async def _run_reflection(self):
        """Runs reflection as a separate async step. The agent automatically stores memory."""
        try:
            reflection_result = await self.agent.reflect('discord')
            logger.info("Reflection completed")
            print("\nReflection Result:")
            print("\033[93m" + json.dumps(reflection_result, indent=2) + "\033[0m")
            return reflection_result
        except Exception as e:
            logger.error(f"Error during reflection: {str(e)}", exc_info=True)
            return None
