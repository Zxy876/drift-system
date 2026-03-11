from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.world_api import RuleTriggerEvent, story_rule_event, world_engine
from app.core.ai.intent_engine import parse_intent
from app.core.story.story_engine import story_engine


router = APIRouter(prefix="/intent", tags=["Intent"])
logger = logging.getLogger("uvicorn.error")


class IntentParseRequest(BaseModel):
    player_id: str = Field(default="default")
    text: str = Field(..., min_length=1)
    world_state: Dict[str, Any] | None = None


class IntentEventRequest(BaseModel):
    player_id: str = Field(default="default")
    event_type: str | None = Field(default="chat")
    text: str | None = Field(default=None)
    message: str | None = Field(default=None)
    say: str | None = Field(default=None)
    payload: Dict[str, Any] = Field(default_factory=dict)


def _normalize_player_id(value: Any) -> str:
    token = str(value or "").strip()
    return token or "default"


def _coerce_text(payload: Dict[str, Any], *candidates: Any) -> str:
    for value in candidates:
        token = str(value or "").strip()
        if token:
            return token

    for key in ("text", "message", "say", "utterance", "input", "content", "chat", "raw_text"):
        token = str(payload.get(key) or "").strip()
        if token:
            return token

    nested_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    for key in ("text", "message", "say", "utterance", "input", "content", "chat", "raw_text"):
        token = str(nested_payload.get(key) or "").strip()
        if token:
            return token

    return ""


@router.post("/parse")
def intent_parse(payload: IntentParseRequest):
    player_id = _normalize_player_id(payload.player_id)
    text = str(payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    world_state = payload.world_state if isinstance(payload.world_state, dict) else (world_engine.get_state() or {})
    parsed = parse_intent(player_id, text, world_state, story_engine)
    intents = parsed.get("intents") if isinstance(parsed, dict) and isinstance(parsed.get("intents"), list) else []
    first_intent = intents[0] if intents and isinstance(intents[0], dict) else None

    return {
        "status": "ok",
        "player_id": player_id,
        "text": text,
        "intent": first_intent,
        "intents": intents,
    }


@router.post("/event")
def intent_event(payload: IntentEventRequest):
    player_id = _normalize_player_id(payload.player_id)
    body = dict(payload.payload or {})
    text = _coerce_text(body, payload.text, payload.message, payload.say)
    if not text:
        raise HTTPException(status_code=400, detail="text/message/say is required")

    if not any(str(body.get(key) or "").strip() for key in ("text", "message", "say", "utterance", "input", "content", "chat", "raw_text")):
        body["text"] = text

    event_type = str(payload.event_type or body.get("event_type") or "chat").strip() or "chat"

    logger.info(
        "intent_event_received",
        extra={
            "player_id": player_id,
            "event_type": event_type,
            "text": text,
        },
    )

    result = story_rule_event(
        RuleTriggerEvent(
            player_id=player_id,
            event_type=event_type,
            payload=body,
        )
    )

    if isinstance(result, dict):
        result.setdefault(
            "player_input",
            {
                "text": text,
                "event_type": event_type,
            },
        )

    return result
