import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")

if not api_key:
    raise ValueError("ANTHROPIC_API_KEY not found")

# Example usage of the InstrumentedClient:
#
# from interceptor import InstrumentedClient
#
# client = InstrumentedClient(api_key=api_key)
# response = client.messages.create(
#     model="claude-sonnet-4-5-20250929",
#     max_tokens=1024,
#     messages=[{"role": "user", "content": "Hello"}]
# )
# # trajectory.jsonl is automatically created
