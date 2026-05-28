# API key management — keys can be swapped at runtime without restarting the app

import os
import json
from typing import Optional, Dict
from pathlib import Path
from utils.logger import get_logger

_log = get_logger(__name__)

API_KEYS_FILE = 'config/api_keys.json'

def ensure_config_dir():
    os.makedirs('config', exist_ok=True)

def load_api_keys() -> Dict[str, str]:
    ensure_config_dir()

    if os.path.exists(API_KEYS_FILE):
        try:
            with open(API_KEYS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            _log.error("Error loading API keys: %s", e)
            return {}
    return {}

def save_api_keys(keys: Dict[str, str]) -> bool:
    ensure_config_dir()

    try:
        with open(API_KEYS_FILE, 'w') as f:
            json.dump(keys, f, indent=2)
        # lock down permissions so other users on the system can't read it
        try:
            os.chmod(API_KEYS_FILE, 0o600)
        except Exception:
            pass
        return True
    except Exception as e:
        _log.error("Error saving API keys: %s", e)
        return False

def get_current_api_key() -> Optional[str]:
    # re-read .env each call so a key update takes effect without a restart
    from dotenv import dotenv_values
    env_vals = dotenv_values('.env')
    env_key = env_vals.get('GEMINI_API_KEY') or os.getenv('GEMINI_API_KEY')
    if env_key:
        return env_key

    keys = load_api_keys()
    if 'primary' in keys and keys['primary']:
        return keys['primary']

    for key_name, key_value in keys.items():
        if key_value:
            return key_value

    return None

def set_primary_api_key(api_key: str) -> bool:
    keys = load_api_keys()
    keys['primary'] = api_key
    keys['updated_at'] = str(int(__import__('time').time()))
    return save_api_keys(keys)

def add_api_key(name: str, api_key: str) -> bool:
    keys = load_api_keys()
    keys[name] = api_key
    keys['updated_at'] = str(int(__import__('time').time()))
    return save_api_keys(keys)

def list_api_keys() -> Dict[str, Dict]:
    # only expose partial key so it's safe to show in the UI
    keys = load_api_keys()
    result = {}

    for name, key in keys.items():
        if name == 'updated_at':
            continue

        if key:
            masked_key = f"{key[:10]}...{key[-4:]}" if len(key) > 20 else "***"
            result[name] = {
                'key': masked_key,
                'full_length': len(key)
            }
    
    return result

def remove_api_key(name: str) -> bool:
    keys = load_api_keys()
    if name in keys:
        del keys[name]
        keys['updated_at'] = str(int(__import__('time').time()))
        return save_api_keys(keys)
    return False

def is_api_key_valid(api_key: str) -> bool:
    # Gemini keys are 39+ chars; anything shorter is definitely wrong
    return api_key and len(api_key) >= 30

def test_api_key(api_key: str) -> bool:
    # hits the models list endpoint — cheap way to verify the key works
    try:
        import requests

        url = f'https://generativelanguage.googleapis.com/v1/models?key={api_key}'
        response = requests.get(url, timeout=5)

        return response.status_code == 200
    except Exception as e:
        _log.warning("Error testing API key: %s", e)
        return False
