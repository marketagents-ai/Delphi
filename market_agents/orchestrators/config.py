from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Optional

class LLMSettings(BaseSettings):
    client: str
    model: str
    temperature: float = 0.8
    max_tokens: int = 2048

class BotSettings(BaseSettings):
    name: str
    personas_dir: Path = Path("./market_agents/agents/personas/generated_personas")

class Settings(BaseSettings):
    llm_config: LLMSettings
    bot: BotSettings
    
    model_config = SettingsConfigDict(
        yaml_file=str(Path(__file__).parent / "orchestrator_config.yaml"),
        env_prefix="LLM_",
        env_nested_delimiter='__',
        extra='ignore',
        env_file='.env',
        env_file_encoding='utf-8'
    )

    @classmethod
    def load_config(cls) -> "Settings":
        try:
            config_path = Path(__file__).parent / "orchestrator_config.yaml"
            if not config_path.exists():
                raise FileNotFoundError(f"Config file not found at {config_path}")
            
            with open(config_path, 'r') as f:
                yaml_data = yaml.safe_load(f)
                return cls(**yaml_data)
        except Exception as e:
            raise ValueError(f"Error loading config: {str(e)}")

# Add yaml import
import yaml

settings = Settings.load_config()