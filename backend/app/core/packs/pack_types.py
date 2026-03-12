from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class PackMeta:
    pack_id: str
    version: str
    namespace: str
    priority: int
    enabled: bool
    pack_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pack_id": str(self.pack_id),
            "version": str(self.version),
            "namespace": str(self.namespace),
            "priority": int(self.priority),
            "enabled": bool(self.enabled),
            "pack_path": str(self.pack_path),
        }
