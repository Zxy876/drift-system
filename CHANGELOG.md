# Changelog

## v0.2.0 - 2026-03-11

### System
- Consolidated language processing into the Intent2 pipeline for player chat and `/talk` command path.
- Kept game-structured events (`near`/`interact`/`trigger`) on `RuleEventBridge` to preserve event semantics.
- Added release safety housekeeping for runtime artifacts (`*.db`, logs, build outputs) through repository ignore rules.

### Backend
- Added poetry scene intent recognition (`CREATE_POETRY_SCENE`) in `app/core/ai/intent_engine.py`.
- Added regression test coverage for poetry intent parse in `test_intent_event_api.py`.
- Added architecture audit document: `docs/intent_engine_audit.md`.

### Plugin
- Added `CREATE_POETRY_SCENE` in `IntentType2` and dispatch flow in `IntentDispatcher2` via `/poetry/generate`.
- Updated `PlayerChatListener` and `TalkCommand` to use single language-entry path.
- Refactored `NearbyNPCListener` so NPC talk semantics route through `IntentRouter2 + IntentDispatcher2`.

### Web
- Synced `drift-web` into monorepo as `web/` for unified `drift-system` layout.

### Deployment
- Backend deployed to Railway production (`drift-backend` service) and healthchecks passed.
