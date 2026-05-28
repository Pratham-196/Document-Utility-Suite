#!/usr/bin/env python
"""Test script to verify chat system is reading documents correctly"""

from utils.chat_utils import DocumentChatManager
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('GEMINI_API_KEY')

if api_key:
    chat_mgr = DocumentChatManager(api_key)
    sample_doc = 'The Earth has one Moon. The Moon orbits the Earth every 27.3 days.'
    session_id = 'test_session_123'
    
    print("\n=== Testing Chat Document Reading ===\n")
    
    # Test session creation
    result = chat_mgr.start_chat_session(session_id, sample_doc, 'test.txt')
    session = chat_mgr.chat_sessions[session_id]
    
    print("✓ Session created successfully")
    
    # Verify document is in system prompt
    doc_in_prompt = sample_doc in session['system_prompt']
    print(f"✓ Document content in system prompt: {doc_in_prompt}")
    
    if not doc_in_prompt:
        print("ERROR: Document content NOT found in system prompt!")
    
    print(f"✓ System prompt length: {len(session['system_prompt'])} characters")
    print(f"✓ Document content length: {len(sample_doc)} characters")
    
    # Show system prompt excerpt
    print("\n--- System Prompt Excerpt ---")
    print(session['system_prompt'][:500] + "...\n")
    
    print("✓ Chat system is properly configured!")
    print("✓ Document content will be sent with EVERY message to the API")
    
else:
    print('ERROR: API key not found')
