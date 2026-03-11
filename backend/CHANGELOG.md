# Changelog

## v0.2.0 - 2026-03-11

### Added
- Intent engine now recognizes poetry scene requests and `/poem ...` inputs as `CREATE_POETRY_SCENE`.
- Added backend regression coverage for poetry intent parsing in `test_intent_event_api.py`.
- Added release safety ignore rules for runtime databases and logs in `.gitignore`.

### Changed
- Updated intent normalization/fallback behavior to align plugin `IntentRouter2` dispatch flow.
- Refreshed `docs/intent_engine_audit.md` with architecture convergence status.
