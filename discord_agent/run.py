#!/usr/bin/env python
from dotenv import load_dotenv
from naptha_sdk.schemas import AgentRunInput, OrchestratorRunInput, EnvironmentRunInput
from naptha_sdk.utils import get_logger
from discord_agent.schemas import InputSchema
from typing import Union

load_dotenv()

logger = get_logger(__name__)

# You can create your module as a class or function
class BasicModule:
    def __init__(self, module_run: Union[AgentRunInput, OrchestratorRunInput, EnvironmentRunInput]):
        self.module_run = module_run

    def func(self, input_data):
        logger.info(f"Running module function")
        return input_data

# Default entrypoint when the module is executed
def run(module_run: Union[AgentRunInput, OrchestratorRunInput, EnvironmentRunInput]):
    basic_module = BasicModule(module_run)
    method = getattr(basic_module, module_run.inputs.func_name, None)
    return method(module_run.inputs.func_input_data)

if __name__ == "__main__":
    # For testing locally
    from naptha_sdk.client.naptha import Naptha
    from naptha_sdk.configs import load_agent_deployments, load_environment_deployments, load_orchestrator_deployments

    naptha = Naptha()

    input_params = InputSchema(func_name="func", func_input_data="gm...")

    # Load Configs
    agent_deployments = load_agent_deployments("module_template/configs/agent_deployments.json", load_persona_data=False, load_persona_schema=False)
    # orchestrator_deployments = load_orchestrator_deployments("module_template/configs/orchestrator_deployments.json")
    # environment_deployments = load_environment_deployments("module_template/configs/environment_deployments.json")

    agent_run = AgentRunInput(
        inputs=input_params,
        agent_deployment=agent_deployments[0],
        consumer_id=naptha.user.id,
    )

    # orchestrator_run = OrchestratorRunInput(
    #     inputs=input_params,
    #     agent_deployments=agent_deployments,
    #     orchestrator_deployment=orchestrator_deployments[0],
    #     environment_deployments=environment_deployments,
    #     consumer_id=naptha.user.id,
    # )

    # environment_run = EnvironmentRunInput(
    #     inputs=input_params,
    #     environment_deployment=environment_deployments[0],
    #     consumer_id=naptha.user.id,
    # )

    response = run(agent_run)

    print("Response: ", response)