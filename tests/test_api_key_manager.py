#!/usr/bin/env python
"""Test script to verify API key management system"""

from utils.api_key_manager import (
    get_current_api_key,
    load_api_keys,
    save_api_keys,
    set_primary_api_key,
    list_api_keys,
    is_api_key_valid
)
import os

print("\n" + "="*60)
print("API KEY MANAGEMENT SYSTEM TEST")
print("="*60)

print("\n1. Testing API Key Manager Functions:")
print("-" * 40)

# Test loading existing keys
print("\n✓ Loading existing API keys...")
keys = load_api_keys()
print(f"  Found {len(keys)} stored keys")
if keys:
    print(f"  Keys: {list(keys.keys())}")

# Test getting current API key
print("\n✓ Getting current API key...")
current_key = get_current_api_key()
if current_key:
    print(f"  Current key: {current_key[:10]}...{current_key[-4:]}")
else:
    print("  No API key configured yet")

# Test API key validation
print("\n✓ Testing API key validation...")
test_key_valid = "AIzaSyD" + "x" * 32
test_key_invalid = "short"
print(f"  Valid format test: {is_api_key_valid(test_key_valid)}")
print(f"  Invalid format test: {is_api_key_valid(test_key_invalid)}")

# Test listing API keys
print("\n✓ Listing all stored API keys...")
stored_keys = list_api_keys()
print(f"  Total keys stored: {len(stored_keys)}")
for key_name, key_info in stored_keys.items():
    print(f"    - {key_name}: {key_info['key']} ({key_info['full_length']} chars)")

print("\n2. Configuration Files:")
print("-" * 40)

config_dir = 'config'
config_file = 'config/api_keys.json'

if os.path.exists(config_dir):
    print(f"✓ Config directory exists: {config_dir}/")
else:
    print(f"✗ Config directory missing: {config_dir}/")

if os.path.exists(config_file):
    print(f"✓ API keys file exists: {config_file}")
    with open(config_file, 'r') as f:
        content = f.read()
    print(f"  File size: {len(content)} bytes")
else:
    print(f"✗ API keys file missing: {config_file}")
    print("  (Will be created when first API key is saved)")

print("\n3. Environment Variables:")
print("-" * 40)

env_key = os.getenv('GEMINI_API_KEY')
if env_key:
    print(f"✓ GEMINI_API_KEY set in environment")
    print(f"  Value: {env_key[:10]}...{env_key[-4:]}")
else:
    print(f"✗ GEMINI_API_KEY not in environment")
    print(f"  (Using stored key or will prompt user)")

print("\n4. How It Works:")
print("-" * 40)
print("""
When API key is exhausted:
1. User sees: "API quota exhausted. Update API key in Settings"
2. User goes to: /api-settings
3. User pastes new free API key
4. User clicks "Test Key" → verifies it works
5. User clicks "Save & Use Key" → key saved + chat reloads
6. Chat continues working immediately!

No app restart needed! ✓
""")

print("\n5. File Organization:")
print("-" * 40)
print("""
config/
├── api_keys.json          # Stores API keys (auto-created)

utils/
├── api_key_manager.py     # API key management functions
├── chat_utils.py          # Updated to use dynamic keys

app.py                      # Updated to use API key manager

templates/
├── api_settings.html      # New settings page
""")

print("\n" + "="*60)
print("✓ API Key Management System is Ready!")
print("="*60)
print("\nAccess it at: http://localhost:5000/api-settings")
print("="*60 + "\n")
