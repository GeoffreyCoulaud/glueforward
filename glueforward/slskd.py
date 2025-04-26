import logging
import yaml
from pathlib import Path
from typing import Optional

from errors import GlueforwardError, RetryableGlueforwardError


class SlskdConfigError(RetryableGlueforwardError):
    """Exception raised when slskd config operations fail"""
    def __init__(self, *args: object) -> None:
        super().__init__(*args, message="Failed to update slskd config")


class SlskdConfig:
    """Handles reading and updating slskd.yaml configuration file"""
    
    __config_path: Path
    
    def __init__(self, config_path: str):
        self.__config_path = Path(config_path)
        logging.debug("Initialized SlskdConfig with path: %s", config_path)

    def update_port(self, port: int) -> None:
        """Update the listenPort in slskd.yaml"""
        try:
            # Read existing config
            with open(self.__config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
            
            # Handle both root-level and soulseek.listenPort configurations
            if 'soulseek' in config:
                config['soulseek']['listenPort'] = port
            else:
                config = {'soulseek': {'listenPort': port}}
            
            # Write back to file
            with open(self.__config_path, 'w') as f:
                yaml.dump(config, f)
                
            logging.debug("Updated slskd listenPort to %d", port)
            
        except (yaml.YAMLError, OSError) as e:
            raise SlskdConfigError(f"Failed to update config: {str(e)}") from e
