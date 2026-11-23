# Documentation

Use the [project index](../README.md#project-index) to find source code, entry points, and local files. Start with the guides below when operating the project.

## Current guides

| Task | Document |
| --- | --- |
| Set up, verify, or migrate the platform | [Reproduce the local deployment](reproduce-deployment.md) |
| Create console accounts and enroll devices | [Multi-user console and device setup](multi-user-auth.md) |
| Run the apartment demo, simulator, or ThingsBoard RPC workflows | [ThingsBoard RPC contracts and apartment demo](thingsboard-rpc-contract.md) |
| Set up a physical Tasmota device for the documented MQTT deployment | [Tasmota and ThingsBoard setup](tasmota-thingsboard-setup.md) |

## Archived deployment guides

The guides below describe the earlier standalone gateway topology on port 8080. For the current stack, use [Reproduce the local deployment](reproduce-deployment.md).

- [AWS deployment](archive/legacy-aws-deployment.md)
- [Machine B deployment](archive/legacy-machine-b-deployment.md)
- [Gateway technical handoff](archive/legacy-gateway-handoff.md)
- [XiaoZhi gateway configuration](archive/legacy-xiaozhi-gateway-config.md)

## Project records

| Document | Scope |
| --- | --- |
| [Alpha 0.2 provisioning specification](spec-alpha-0.2.md) | Design record for ESP32 device provisioning. |
| [Tasmota MCP session handoff](tasmota-mcp-session-handoff.md) | Work completed and outstanding at the end of that session. |
| [Deployment implementation plan](superpowers/plans/2026-11-18-reproduce-deployment.md) | Planning record for source-based deployment. |

## Documentation conventions

- Use descriptive, lowercase filenames with hyphens between words. Use `README.md` for directory indexes. Update links when moving a guide.
- Move superseded operational guides into `docs/archive/`, identify them as archived, and link to their current replacement.
- Start with one H1 title and a short paragraph explaining who the document is for and when to use it. For a legacy workflow or historical record, identify its scope up front and link to the current guide.
- Use sentence-case H2 and H3 headings. Use numbered lists for ordered steps. In operational guides, group prerequisites, steps, and verification under headings when each applies.
- Use repository-relative links for project files and language-tagged code fences for commands and configuration. Use placeholders for machine-specific values and credentials.
- Update the guide that owns a workflow when its instructions change. Link to that guide from other documents and add new shared guides to this index.
