from dataclasses import dataclass
import json
import os
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class KeyConfig:
    event_string: str
    key_code: int


@dataclass
class AppConfig:
    trigger_key: KeyConfig
    target_file: str
    config_file: str
    debug_level: int = 0


class ConfigManager:
    """Manages application configuration"""

    @staticmethod
    def load_config(config_path: str) -> AppConfig:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, 'r') as f:
            data = json.load(f)

        trigger_key = KeyConfig(**data['trigger_key'])
        return AppConfig(
            trigger_key=trigger_key,
            target_file=os.path.join(os.path.dirname(
                config_path), "text_field_targets.json"),
            config_file=config_path
        )

    @staticmethod
    def save_config(config: AppConfig, path: str):
        data = {
            'trigger_key': {
                'event_string': config.trigger_key.event_string,
                'key_code': config.trigger_key.key_code
            }
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load_targets(target_file: str) -> list:
        """Load target text fields configuration"""
        if not os.path.exists(target_file):
            logger.warning(f"No targets file found at {target_file}")
            return []

        with open(target_file, 'r') as f:
            return json.load(f)
