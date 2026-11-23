# Repository Guidelines

## Project Structure & Module Organization

- `platform-bridge/` contains the FastAPI platform API, device provisioning, and console hosting.
- `xiaozhi-console/` contains the React, TypeScript, and Tailwind frontend; reusable UI lives in `src/components/`.
- `firmware/` contains ESP-IDF C++ firmware, board implementations, and hardware tools.
- `services/`, `gateway/`, and `thingsboard-mcp/` provide AI routing and IoT integrations. `faster-whisper/` and `piper/` contain speech services.
- `tests/` holds platform integration scripts; component-specific tests may live inside their own directories. Documentation and images are in `docs/`.

## Build, Test, and Development Commands

Run commands from the repository root unless stated otherwise:

- For a new machine, copy `.env.example` to `.env` without overwriting an existing file; set `HOST_IP`, `API_KEY`, and `BRIDGE_SECRET`, plus any integration settings. Follow `docs/reproduce-deployment.md` for models, accounts, CPU-only and ThingsBoard setup.
- `docker compose -p iot_assignment up -d --build` starts core services on the network required by `docker compose -f docker-compose.deploy.yml up -d --build`. Use `docker-compose.cpu.yml` as an override on machines without NVIDIA GPU support.
- `cd xiaozhi-console && npm install && npm run dev` starts the frontend development server. Use `npm run build` to type-check and build it.
- `cd firmware && idf.py build` builds firmware using an installed ESP-IDF and the selected target and configuration.
- `python3 tests/test_alpha02_provisioning.py` runs the provisioning integration script against a test bridge at `localhost:8005`; it requires two pre-created test accounts and environment variables listed in the script.

## Coding Style & Naming Conventions

Follow the surrounding module's style: Python uses four-space indentation and `snake_case`; React/TypeScript uses two spaces, `PascalCase` components, and `camelCase` functions; firmware follows existing C++ conventions. Name Python test files `test_*.py`. Keep board-specific hardware settings in the appropriate firmware board directory. The console build runs TypeScript checks; no repository-wide formatter is configured.

## Testing Guidelines

Add focused tests for changed behavior and run the relevant component's tests or integration scripts. Several scripts in `tests/` require running services and may create or modify device records; inspect their prerequisites before running them. Firmware changes should be built for the affected board and, where possible, checked on hardware. There is no documented repository-wide coverage threshold.

## Commit & Pull Request Guidelines

Recent commits use Conventional Commit-style prefixes, such as `feat(mcp): ...` and `docs: ...`. Keep subjects concise and describe the change. Pull requests should explain the problem and solution, list verification performed and service or hardware prerequisites, link related issues when available, and include screenshots for visible console changes.

## Security & Configuration

Keep credentials and device tokens out of commits and logs. Preserve an existing `BRIDGE_SECRET` when moving a deployment, and back up persistent data before migration. The device must reach the bridge at `HOST_IP`; the YOLO UNO firmware has a separate OTA fallback that must be configured and built for the target host because firmware cannot read the host `.env`.

## Coding Behavior

Behavioral guidelines to reduce common LLM coding mistakes.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```text
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
