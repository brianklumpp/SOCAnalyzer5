import os
import requests

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY') or '<PASTE_YOUR_KEY_HERE>'
OPENAI_EMBEDDING_URL = 'https://api.openai.com/v1/embeddings'
OPENAI_EMBEDDING_MODEL = 'text-embedding-ada-002'

text = "Test embedding for CUEC pipeline."
headers = {
    'Authorization': f'Bearer {OPENAI_API_KEY}',
    'Content-Type': 'application/json',
}
data = {
    'input': text,
    'model': OPENAI_EMBEDDING_MODEL,
}

try:
    resp = requests.post(OPENAI_EMBEDDING_URL, headers=headers, json=data)
    print(f"Status code: {resp.status_code}")
    print(f"Response: {resp.text}")
    resp.raise_for_status()
    embedding = resp.json()['data'][0]['embedding']
    print("Embedding received:", embedding[:10], "...")
except Exception as e:
    print("Error during embedding call:", e)
