import yaml
from pathlib import Path

def load_config(config_path='config.yml'):
    config_file = Path(config_path)
    if not config_file.is_file():
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")
    
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    return config

config = load_config()