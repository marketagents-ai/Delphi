# discord_mechanism.py

from typing import List, Dict, Any, Union, Type, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from market_agents.environments.environment import (
    Mechanism, LocalAction, GlobalAction, LocalObservation, GlobalObservation,
    EnvironmentStep, ActionSpace, ObservationSpace, LocalEnvironmentStep
)
import logging

logger = logging.getLogger(__name__)

class DiscordInputMessage(BaseModel):
    content: str
    message_type: Literal["user_message", "agent_message"]
    author_id: str
    author_name: str
    channel_id: str
    channel_name: str
    timestamp: str

class DiscordAutoMessage(BaseModel):
    relevance: int = Field(
        description="A score from 0-100 indicating how relevant the messages are based on context and memory. Low scores suggest hold decision."
    )
    decision: Literal["hold", "post"] = Field(
        description="Whether to post or hold the message. Use 'hold' when relevance is low or message lacks appropriate humor/context for TARS bot."
    )
    content: str = Field(
        description="The actual message content to post to Discord if decision is post"
    )

class DiscordMessage(BaseModel):
    type: Literal["markdown", "text"] = Field(
        description="Format to return response in - either as markdown or plain text"
    )
    content: str = Field(
        description="The message content for TARS bot to send to Discord. Include markdown block and formatting if type is markdown."
    )

class DiscordAction(LocalAction):
    action: DiscordMessage

    @classmethod
    def sample(cls, agent_id: str) -> 'DiscordAction':
        # For simplicity, return a sample action
        return cls(
            agent_id=agent_id,
            action=DiscordMessage(
                type="text",
                content="Sample message"
            )
        )

    @classmethod
    def action_schema(cls) -> Dict[str, Any]:
        return cls.model_json_schema()

class DiscordObservation(BaseModel):
    messages: List[DiscordMessage]

class DiscordLocalObservation(LocalObservation):
    agent_id: str
    observation: DiscordObservation

class DiscordGlobalObservation(GlobalObservation):
    observations: Dict[str, DiscordLocalObservation]
    all_messages: List[DiscordInputMessage]

class DiscordActionSpace(ActionSpace):
    allowed_actions: List[Type[LocalAction]] = [DiscordAction]

class DiscordObservationSpace(ObservationSpace):
    allowed_observations: List[Type[LocalObservation]] = [DiscordLocalObservation]

class DiscordMechanism(Mechanism):
    max_rounds: int = Field(default=1000, description="Maximum number of simulation rounds")
    current_round: int = Field(default=0, description="Current round number")
    sequential: bool = Field(default=False, description="Whether the mechanism is sequential")
    messages: List[DiscordInputMessage] = Field(default_factory=list)
    global_state: Dict[str, Any] = Field(default_factory=dict)  # Add global_state field

    def step(self, action: Union[DiscordAction, Dict[str, Any]]) -> Union[LocalEnvironmentStep, EnvironmentStep]:
        """
        Process the agent's action, update the mechanism's state, and return observations.
        """
        logger.debug(f"DiscordMechanism step called with action: {action}")

        if isinstance(action, dict):
            try:
                action = DiscordAction.parse_obj(action)
                logger.debug("Parsed action into DiscordAction.")
            except Exception as e:
                logger.error(f"Failed to parse action into DiscordAction: {e}")
                raise

        if not isinstance(action, DiscordAction):
            logger.error(f"Expected DiscordAction, got {type(action).__name__}")
            raise TypeError(f"Expected DiscordAction, got {type(action).__name__}")

        # Process the action
        self.current_round += 1
        self.messages.append(action.action)
        logger.info(f"Agent {action.agent_id} sent a message: {action.action.content}")

        # Update the global state with the new message
        if "messages" not in self.global_state:
            self.global_state["messages"] = []
        self.global_state["messages"].append(action.action.dict())

        # Create observations for all agents
        observation = self._create_observation(action.agent_id)
        done = self.current_round >= self.max_rounds

        local_step = LocalEnvironmentStep(
            observation=observation,
            reward=0,
            done=done,
            info={
                "current_round": self.current_round,
                "all_messages": [message.dict() for message in self.messages],
            }
        )

        return local_step

    def _create_observation(self, agent_id: str) -> DiscordLocalObservation:
        """
        Create a local observation for the agent, including only their own messages.
        """
        # Filter messages sent by the agent
        agent_messages = [msg for msg in self.messages if msg.author_id == agent_id]

        observation = DiscordObservation(messages=agent_messages)
        local_observation = DiscordLocalObservation(
            agent_id=agent_id,
            observation=observation
        )
        return local_observation

    def update_state(self, environment_info: Dict[str, Any]) -> None:
        """
        Update the mechanism's state with new environment information.
        This method should be called whenever new messages are received from Discord.
        """
        # Update global state
        self.global_state = environment_info

        # Update messages
        messages = environment_info.get("messages", [])
        self.messages = [
            DiscordInputMessage(
                content=msg["content"],
                message_type="user_message" if msg["author_id"] != environment_info["bot_id"] else "agent_message",
                author_id=msg["author_id"],
                author_name=msg["author_name"],
                channel_id=environment_info["channel_id"],
                channel_name=environment_info["channel_name"],
                timestamp=msg["timestamp"]
            )
            for msg in messages
        ]
        logger.info(f"Updated mechanism state with {len(self.messages)} messages")

    def get_global_state(self) -> Dict[str, Any]:
        """
        Return the global state as a dictionary.
        """
        # Create local observations for each agent
        local_observations = {}
        for message in self.messages:
            agent_id = message.author_id
            if agent_id not in local_observations:
                local_observations[agent_id] = DiscordLocalObservation(
                    agent_id=agent_id,
                    observation=DiscordObservation(messages=[])
                )
            local_observations[agent_id].observation.messages.append(message)

        # Create and return global observation
        global_observation = DiscordGlobalObservation(
            observations=local_observations,
            all_messages=self.messages
        )

        return global_observation.dict()

    def reset(self) -> None:
        self.current_round = 0
        self.messages = []
        self.global_state = {}  # Reset global state
        logger.info("DiscordMechanism has been reset.")
