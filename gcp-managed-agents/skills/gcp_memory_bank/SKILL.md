---
name: gcp_memory_bank
description: "Persist and recall long-term user facts using Vertex AI Memory Bank."
---
# GCP Memory Bank

Use the code_execution tool to run the client script. It prints one JSON object to
stdout; base your reply only on that JSON.

Hard rules:

Run the exact command shown. Do NOT edit, patch, or modify the script. If it errors,
  report the error JSON verbatim and stop — no workarounds, no local files.

Report success only if the JSON has "status": "success".
Default user_id is user_001 unless the turn specifies another.


## Record a fact
`python3 /workspace/.agent/skills/gcp_memory_bank/gcp_vertex_client.py --action add_memory --user_id <USER_ID> --fact "<FACT>"`

## Recall facts
`python3 /workspace/.agent/skills/gcp_memory_bank/gcp_vertex_client.py --action get_memories --user_id <USER_ID> --query "<SEARCH TEXT>"`
Omit `--query` to list all facts for the user.