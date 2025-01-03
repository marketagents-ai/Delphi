#!/usr/bin/env python
from dotenv import load_dotenv
from naptha_sdk.schemas import AgentRunInput
from naptha_sdk.utils import get_logger
from discord_agent.schemas import InputSchema
import asyncio

# Import existing Discord bot functionality
from discord_bot import setup_bot

load_dotenv()
logger = get_logger(__name__)

class DiscordAgent:
    def __init__(self, module_run):
        self.module_run = module_run
        self.bot = None

    async def start_bot(self, input_data):
        """Start the Discord bot using existing setup"""
        try:
            # Get Discord token from inputs
            token = input_data.get("discord_token")
            if not token:
                raise ValueError("Discord token not provided in inputs")

            # Use existing setup_bot function
            self.bot = setup_bot()
            await self.bot.start(token)
            
            # Keep running until stopped
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                await self.stop()
            
            return {
                "status": "success",
                "message": "Discord bot stopped gracefully"
            }
            
        except Exception as e:
            logger.error(f"Error in Discord bot: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def stop(self):
        """Stop the Discord bot"""
        if self.bot:
            await self.bot.close()

def run(module_run):
    """Main entry point for running the Discord agent"""
    agent = DiscordAgent(module_run)
    method = getattr(agent, module_run.inputs.func_name, None)
    return asyncio.run(method(module_run.inputs.func_input_data))

if __name__ == "__main__":
    from naptha_sdk.client.naptha import Naptha
    from naptha_sdk.configs import setup_module_deployment
    import os

    naptha = Naptha()

    # Setup module deployment
    deployment = asyncio.run(setup_module_deployment(
        "agent",
        "discord_agent/configs/agent_deployments.json",
        node_url=os.getenv("NODE_URL")
    ))

    # Prepare input parameters
    input_params = InputSchema(
        func_name="start_bot",
        func_input_data={"discord_token": os.getenv("DISCORD_TOKEN")}
    )
    
    module_run = AgentRunInput(
        inputs=input_params,
        deployment=deployment,
        consumer_id=naptha.user.id,
    )

    response = run(module_run)
    print("Response: ", response)