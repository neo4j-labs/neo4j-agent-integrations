import os
import vertexai
from dotenv import load_dotenv

# Load local GCP project settings
load_dotenv(dotenv_path=".env")

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "your-project-id")
LOCATION = os.environ.get("GCP_LOCATION", "global")

print(f"Connecting to Agent Platform SDK client in project: {PROJECT_ID}...")

# Initialize the official enterprise SDK client
client = vertexai.Client(project=PROJECT_ID, location=LOCATION)

print("Provisioning a new Memory Bank instance...")
# This triggers the backend registration for the long-term context engine
memory_bank = client.agent_engines.create()

# Extract the full declarative resource path name string
resource_name = memory_bank.api_resource.name

print("\n" + "="*60)
print("SUCCESS: Memory Bank instance deployed successfully.")
print(f"Full Resource Path: {resource_name}")
# Splits 'projects/PROJECT_ID/locations/LOCATION/reasoningEngines/ID' to isolate the trailing number
print(f"Isolated MEMORY_BANK_ID to use in .env: {resource_name.split('/')[-1]}")
print("="*60 + "\n")