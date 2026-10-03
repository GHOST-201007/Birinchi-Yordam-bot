import os
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

async def test_models():
    if not api_key:
        print("API KEY NOT FOUND")
        return
        
    client = genai.Client(api_key=api_key)
    models_to_test = ["gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    
    for model in models_to_test:
        print(f"Testing model: {model}...")
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents="Salom, bu test xabari."
            )
            print(f"✅ {model} SUCCESS: {response.text[:50]}")
        except Exception as e:
            print(f"❌ {model} FAILED: {str(e)}")

asyncio.run(test_models())
