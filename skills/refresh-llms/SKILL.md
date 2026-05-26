---
name: refresh-llms
description: Refresh the local OCI model cache used by the UI model selector.
---
Refresh the local model cache by running the OCI refresh workflow.

Task:
- Execute the cache refresh workflow.
- Return success output on completion.
- Return a fail-fast error when refresh fails.
