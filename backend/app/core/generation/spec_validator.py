from __future__ import annotations

from typing import Any, Dict


REQUIRED_FIELDS = (
    "structure_type",
    "width",
    "depth",
    "height",
    "material_preference",
    "roof_type",
)

ALLOWED_FIELDS = set(REQUIRED_FIELDS) | {"orientation", "features"}
FORBIDDEN_EXEC_FIELDS = {"blocks", "build", "mc", "world_patch"}

STRUCTURE_TYPES = {"house", "tower", "wall", "bridge"}
MATERIAL_PREFERENCES = {"wood", "stone", "brick"}
ROOF_TYPES = {"flat", "gable", "none"}
ORIENTATIONS = {"north", "south", "east", "west"}

FEATURE_ALLOWED_FIELDS = {"door", "windows"}
DOOR_ALLOWED_FIELDS = {"enabled", "side"}
WINDOW_ALLOWED_FIELDS = {"enabled", "count"}


def _reject(failure_code: str, message: str) -> Dict[str, Any]:
    return {
        "status": "REJECTED",
        "failure_code": failure_code,
        "message": message,
        "spec": None,
    }


def _normalize_enum(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _normalize_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _normalize_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _validate_features(raw_features: Any) -> tuple[dict | None, dict | None]:
    if raw_features is None:
        return {
            "door": {"enabled": False, "side": "front"},
            "windows": {"enabled": False, "count": 0},
        }, None

    if not isinstance(raw_features, dict):
        return None, _reject("INVALID_NESTED_FIELD", "features must be an object")

    unknown_feature_fields = sorted(k for k in raw_features.keys() if k not in FEATURE_ALLOWED_FIELDS)
    if unknown_feature_fields:
        return None, _reject(
            "INVALID_NESTED_FIELD",
            f"unknown feature fields: {', '.join(unknown_feature_fields)}",
        )

    raw_door = raw_features.get("door")
    if raw_door is None:
        door = {"enabled": False, "side": "front"}
    else:
        if not isinstance(raw_door, dict):
            return None, _reject("INVALID_NESTED_FIELD", "features.door must be an object")
        unknown_door_fields = sorted(k for k in raw_door.keys() if k not in DOOR_ALLOWED_FIELDS)
        if unknown_door_fields:
            return None, _reject(
                "INVALID_NESTED_FIELD",
                f"unknown door fields: {', '.join(unknown_door_fields)}",
            )
        door_enabled = _normalize_bool(raw_door.get("enabled", False))
        if door_enabled is None:
            return None, _reject("INVALID_NESTED_FIELD", "features.door.enabled must be bool")
        door_side = _normalize_enum(raw_door.get("side", "front"))
        if door_side != "front":
            return None, _reject("INVALID_FEATURE_CONFIG", "features.door.side must be 'front'")
        door = {"enabled": door_enabled, "side": door_side}

    raw_windows = raw_features.get("windows")
    if raw_windows is None:
        windows = {"enabled": False, "count": 0}
    else:
        if not isinstance(raw_windows, dict):
            return None, _reject("INVALID_NESTED_FIELD", "features.windows must be an object")
        unknown_window_fields = sorted(k for k in raw_windows.keys() if k not in WINDOW_ALLOWED_FIELDS)
        if unknown_window_fields:
            return None, _reject(
                "INVALID_NESTED_FIELD",
                f"unknown windows fields: {', '.join(unknown_window_fields)}",
            )
        windows_enabled = _normalize_bool(raw_windows.get("enabled", False))
        if windows_enabled is None:
            return None, _reject("INVALID_NESTED_FIELD", "features.windows.enabled must be bool")
        windows_count = _normalize_int(raw_windows.get("count", 0))
        if windows_count is None:
            return None, _reject("INVALID_NESTED_FIELD", "features.windows.count must be int")
        if windows_count < 0 or windows_count > 4:
            return None, _reject("INVALID_FEATURE_CONFIG", "features.windows.count must be in range 0..4")
        windows = {"enabled": windows_enabled, "count": windows_count}

    return {"door": door, "windows": windows}, None


def validate_spec(spec: dict) -> dict:
    if not isinstance(spec, dict):
        return _reject("MISSING_FIELD", "spec must be a dictionary")

    forbidden_fields = sorted(field for field in FORBIDDEN_EXEC_FIELDS if field in spec)
    if forbidden_fields:
        return _reject(
            "FORBIDDEN_EXEC_FIELD",
            f"forbidden execution fields present: {', '.join(forbidden_fields)}",
        )

    unknown_fields = sorted(field for field in spec.keys() if field not in ALLOWED_FIELDS)
    if unknown_fields:
        return _reject("UNKNOWN_FIELD", f"unknown fields: {', '.join(unknown_fields)}")

    for field in REQUIRED_FIELDS:
        if field not in spec:
            return _reject("MISSING_FIELD", f"missing required field: {field}")

    structure_type = _normalize_enum(spec.get("structure_type"))
    if structure_type not in STRUCTURE_TYPES:
        return _reject("INVALID_ENUM", "structure_type must be one of: house|tower|wall|bridge")

    material_preference = _normalize_enum(spec.get("material_preference"))
    if material_preference not in MATERIAL_PREFERENCES:
        return _reject("INVALID_ENUM", "material_preference must be one of: wood|stone|brick")

    roof_type = _normalize_enum(spec.get("roof_type"))
    if roof_type not in ROOF_TYPES:
        return _reject("INVALID_ENUM", "roof_type must be one of: flat|gable|none")

    orientation = _normalize_enum(spec.get("orientation", "south"))
    if orientation not in ORIENTATIONS:
        return _reject("INVALID_ENUM", "orientation must be one of: north|south|east|west")

    width = _normalize_int(spec.get("width"))
    if width is None or width < 3 or width > 64:
        return _reject("OUT_OF_RANGE", "width must be an integer in range 3..64")

    depth = _normalize_int(spec.get("depth"))
    if depth is None or depth < 3 or depth > 64:
        return _reject("OUT_OF_RANGE", "depth must be an integer in range 3..64")

    height = _normalize_int(spec.get("height"))
    if height is None or height < 2 or height > 64:
        return _reject("OUT_OF_RANGE", "height must be an integer in range 2..64")

    features, feature_error = _validate_features(spec.get("features"))
    if feature_error is not None:
        return feature_error

    normalized_spec = {
        "structure_type": structure_type,
        "width": width,
        "depth": depth,
        "height": height,
        "material_preference": material_preference,
        "roof_type": roof_type,
        "orientation": orientation,
        "features": features,
    }

    return {
        "status": "VALID",
        "failure_code": "NONE",
        "message": "spec is valid",
        "spec": normalized_spec,
    }
