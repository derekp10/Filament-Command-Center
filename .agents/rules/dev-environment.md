---
trigger: always_on
---

Architecture & Environment:
Dev: Runs in a local Docker instance. Always provide terminal and execution commands in a Docker context (e.g., docker exec, docker-compose).
Prod: Hosted on a TrueNAS server. Keep deployment, storage, and networking suggestions strictly compatible with TrueNAS architecture.
