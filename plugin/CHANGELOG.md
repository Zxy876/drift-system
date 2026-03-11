# Changelog

## v0.2.0 - 2026-03-11

### Added
- Added `CREATE_POETRY_SCENE` to `IntentType2`.
- Added poetry dispatch path in `IntentDispatcher2`: calls `/poetry/generate` and executes returned `world_patch`.

### Changed
- Unified player chat routing to a single language channel: `PlayerChatListener` now routes to `IntentRouter2` only.
- Refactored NPC semantic talk routing to intent pipeline in `NearbyNPCListener` while preserving structured game events in `RuleEventBridge`.
- Simplified `/talk` command to reuse chat entry (`p.chat(msg)`) for single-path processing.
- Updated plugin bootstrap wiring in `DriftPlugin` for the new listener dependencies.
