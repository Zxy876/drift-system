"""Quest system is deferred until later development phases."""


def __getattr__(_name: str):  # pragma: no cover - compatibility stub
    raise AttributeError(
        "QuestDirector is unavailable during Stage 2; quest features are locked."
    )
