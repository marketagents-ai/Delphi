#!/usr/bin/env python
import os
from dotenv import load_dotenv
from naptha_sdk.schemas import AgentRunInput, OrchestratorRunInput, EnvironmentRunInput
from naptha_sdk.utils import get_logger
from discord_agent.schemas import InputSchema
from typing import Union
import asyncio

# Import existing Discord bot functionality
from discord_bot import setup_bot

load_dotenv()
logger = get_logger(__name__)

class DiscordAgent:
    def __init__(self, module_run: Union[AgentRunInput, OrchestratorRunInput, EnvironmentRunInput]):
        self.module_run = module_run
        self.bot = None

    async def start(self):
        """Start the Discord bot using existing setup"""
        try:
            # Get Discord token from inputs or env
            token = self.module_run.inputs.get("discord_token")
            if not token:
                raise ValueError("Discord token not provided in inputs")

            # Use existing setup_bot function
            self.bot = setup_bot()
            await self.bot.start(token)
            
            return {
                "status": "success",
                "message": "Discord bot started successfully"
            }
            
        except Exception as e:
            logger.error(f"Error starting Discord bot: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def stop(self):
        """Stop the Discord bot"""
        if self.bot:
            await self.bot.close()

async def run(module_run: Union[AgentRunInput, OrchestratorRunInput, EnvironmentRunInput]):
    """Main entry point for running the Discord agent"""
    try:
        agent = DiscordAgent(module_run)
        result = await agent.start()
        
        if result.get("status") == "error":
            return result
            
        # Keep running until stopped
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            await agent.stop()
            
        return {
            "status": "success",
            "message": "Discord bot stopped gracefully"
        }
        
    except Exception as e:
        logger.error(f"Error in Discord agent: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

if __name__ == "__main__":
    from naptha_sdk.client.naptha import Naptha
    from naptha_sdk.configs import load_agent_deployments

    naptha = Naptha()

    # Load Configs
    agent_deployments = load_agent_deployments(
        "discord_agent/configs/agent_deployments.json", 
        load_persona_data=False, 
        load_persona_schema=False
    )

    input_params = {
        "discord_token": os.getenv("DISCORD_TOKEN")
    }
    
    agent_run = AgentRunInput(
        inputs=input_params,
        agent_deployment=agent_deployments[0],
        consumer_id=naptha.user.id,
    )

    asyncio.run(run(agent_run))