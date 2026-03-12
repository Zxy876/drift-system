from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import hashlib
import json
import time
from uuid import uuid4
from typing import Any, Callable, Dict, Optional

from ..executor.canonical_v2 import stable_hash_v2
from ..runtime.world_patch import build_world_patch_payload
from .graph_state import GraphState, InternalState, StoryNode
from .invariant_check import assert_tx_invariants


DryRunFn = Callable[[Dict[str, Any], InternalState], Dict[str, Any]]


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _state_hash(state: InternalState) -> str:
    payload = asdict(state)
    payload.pop("last_node_id", None)
    return _stable_hash(payload)


def _phase4_world_patch_payload_hash(state: InternalState) -> str:
    runtime_state = {
        "phase": str(state.phase),
        "silence_count": int(state.silence_count),
        "tension": int(state.tension),
        "memory_flags": deepcopy(state.memory_flags),
        "last_node_id": state.last_node_id,
        "talk_count": 0,
        "collected_resources": {},
        "npc_available": {},
        "triggers": {},
        "inventory": {"resources": []},
    }
    payload = build_world_patch_payload(runtime_state)
    return stable_hash_v2(payload)


def _graph_hash(graph: GraphState) -> str:
    return _stable_hash(asdict(graph))


class CommitReceipt(dict):
    def __iter__(self):
        return iter((self.get("committed_graph"), self.get("committed_state")))


@dataclass
class Transaction:
    tx_id: str
    base_state_hash: str
    root_from_node: Optional[str]
    draft_graph: GraphState
    draft_state: InternalState | None
    draft_patch: Dict[str, Any] | None = None
    draft_patches: list[Dict[str, Any]] = field(default_factory=list)
    draft_state_hash: str | None = None
    world_patch_payload_hash: str | None = None
    audit_trace: list[Dict[str, Any]] = field(default_factory=list)
    nodes: list[StoryNode] = field(default_factory=list)
    phase_change_count: int = 0
    committed: bool = False
    rolled_back: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class TransactionShell:
    def __init__(self, *, dry_run_fn: DryRunFn | None = None) -> None:
        self._dry_run_fn = dry_run_fn

    def begin_tx(self, committed_graph: GraphState, committed_state: InternalState) -> Transaction:
        base_state_hash = _state_hash(committed_state)
        tx = Transaction(
            tx_id=f"tx_{uuid4().hex[:12]}",
            base_state_hash=base_state_hash,
            root_from_node=committed_graph.current_node_id,
            draft_graph=deepcopy(committed_graph),
            draft_state=deepcopy(committed_state),
            draft_state_hash=base_state_hash,
        )
        tx.metadata["tx_status"] = "active"
        self._append_audit_trace(
            tx,
            phase="begin",
            before_hash=base_state_hash,
            after_hash=base_state_hash,
        )
        return tx

    def apply_event(self, tx: Transaction, event: Dict[str, Any]) -> None:
        self._ensure_tx_active(tx, operation="APPLY")
        if tx.draft_state is None:
            raise RuntimeError("TX_DRAFT_STATE_NOT_AVAILABLE")

        before_hash = tx.draft_state_hash or tx.base_state_hash
        event_type = str(event.get("type", "input")).strip().lower() or "input"
        event_text = str(event.get("text", "")).strip()
        event_id = str(event.get("event_id") or f"evt_{len(tx.nodes) + 1}")

        if event_type == "timeout":
            node = StoryNode(
                node_id=self._next_node_id(
                    tx,
                    node_type="silence",
                    event_type=event_type,
                    event_text=event_text or "silence",
                ),
                node_type="silence",
                text=event_text or "silence",
                event_type=event_type,
                state_patch={"silence_count": tx.draft_state.silence_count + 1},
            )
        else:
            node = StoryNode(
                node_id=self._next_node_id(
                    tx,
                    node_type="normal",
                    event_type=event_type,
                    event_text=event_text or "event",
                ),
                node_type="normal",
                text=event_text or "event",
                event_type=event_type,
                state_patch={},
            )

        self._append_node(tx, node)

        dry_run = self._run_world_dry_run(event, tx.draft_state)
        tx.metadata["world_dry_run"] = dry_run
        expected_world_patch_payload_hash = _phase4_world_patch_payload_hash(tx.draft_state)
        resolved_world_patch_payload_hash = self._resolve_world_patch_payload_hash(
            dry_run,
            fallback_hash=expected_world_patch_payload_hash,
        )
        tx.draft_patch = {
            "event": deepcopy(event),
            "dry_run": deepcopy(dry_run),
            "event_id": event_id,
            "world_patch_payload_hash": resolved_world_patch_payload_hash,
        }
        tx.draft_patches.append(deepcopy(tx.draft_patch))

        if dry_run.get("status") != "PASS":
            reject_node = StoryNode(
                node_id=self._next_node_id(
                    tx,
                    node_type="reject",
                    event_type="world_reject",
                    event_text=str(dry_run.get("reason", "world_dry_run_failed")),
                ),
                node_type="reject",
                text=str(dry_run.get("reason", "world_dry_run_failed")),
                event_type="world_reject",
                state_patch={},
            )
            self._append_node(tx, reject_node)

        tx.draft_state_hash = _state_hash(tx.draft_state)
        tx.world_patch_payload_hash = resolved_world_patch_payload_hash
        tx.metadata["expected_world_patch_payload_hash"] = expected_world_patch_payload_hash

        failure_code: str | None = None
        if tx.world_patch_payload_hash != expected_world_patch_payload_hash:
            failure_code = "WORLD_PATCH_PAYLOAD_HASH_BINDING_MISMATCH"
        elif str(dry_run.get("status", "UNKNOWN")).upper() != "PASS":
            failure_code = str(dry_run.get("reason") or "WORLD_DRY_RUN_FAILED")

        self._append_audit_trace(
            tx,
            phase="apply",
            before_hash=before_hash,
            after_hash=tx.draft_state_hash,
            event_id=event_id,
            failure_code=failure_code,
        )
        tx.metadata["audit_trace"] = tx.audit_trace

    def commit(
        self,
        tx: Transaction,
        *,
        committed_graph: GraphState,
        committed_state: InternalState,
        rule_version: str,
    ) -> CommitReceipt:
        if tx.rolled_back:
            raise RuntimeError("TX_ALREADY_ROLLED_BACK")

        if tx.draft_state is None:
            raise RuntimeError("NOTHING_TO_COMMIT")

        prior = tx.metadata.get("commit_receipt")
        if isinstance(prior, CommitReceipt):
            return prior
        if isinstance(prior, dict):
            return CommitReceipt(prior)

        committed_state_hash_before = _state_hash(committed_state)
        computed_draft_state_hash = _state_hash(tx.draft_state)
        expected_world_patch_payload_hash = _phase4_world_patch_payload_hash(tx.draft_state)
        current_world_patch_payload_hash = tx.world_patch_payload_hash or expected_world_patch_payload_hash

        assert_tx_invariants(
            committed_graph=committed_graph,
            committed_state=committed_state,
            draft_graph=tx.draft_graph,
            draft_state=tx.draft_state,
            tx_nodes=tx.nodes,
            phase_change_count=tx.phase_change_count,
            base_state_hash=tx.base_state_hash,
            committed_state_hash_before=committed_state_hash_before,
            root_from_node=tx.root_from_node,
            draft_state_hash=tx.draft_state_hash,
            computed_draft_state_hash=computed_draft_state_hash,
            world_patch_payload_hash=current_world_patch_payload_hash,
            expected_world_patch_payload_hash=expected_world_patch_payload_hash,
            commit_publish_count=int(tx.metadata.get("publish_count") or 0),
        )

        tx.draft_state.rule_version = rule_version
        tx.world_patch_payload_hash = current_world_patch_payload_hash
        tx.draft_state.world_patch_hash = tx.world_patch_payload_hash

        tx.draft_state_hash = _state_hash(tx.draft_state)
        committed_graph_hash = _graph_hash(tx.draft_graph)

        receipt = CommitReceipt(
            {
                "tx_id": tx.tx_id,
                "base_state_hash": tx.base_state_hash,
                "committed_state_hash": tx.draft_state_hash,
                "committed_graph_hash": committed_graph_hash,
                "commit_timestamp": time.time(),
                "rule_version": rule_version,
                "engine_version": str(tx.metadata.get("engine_version") or "engine_v2_1"),
                "gate_compatibility": {"gate5": True, "gate6": True, "gate7": True},
                "committed_graph": tx.draft_graph,
                "committed_state": tx.draft_state,
            }
        )

        tx.committed = True
        tx.metadata["publish_count"] = 1
        tx.metadata["tx_status"] = "committed"
        self._append_audit_trace(
            tx,
            phase="commit",
            before_hash=computed_draft_state_hash,
            after_hash=receipt["committed_state_hash"],
        )
        tx.metadata["audit_trace"] = tx.audit_trace
        tx.metadata["commit_receipt"] = receipt
        return receipt

    def rollback(self, tx: Transaction) -> Dict[str, Any]:
        if tx.committed:
            raise RuntimeError("TX_ALREADY_COMMITTED")

        prior = tx.metadata.get("rollback_receipt")
        if isinstance(prior, dict):
            return prior

        before_hash = tx.draft_state_hash or tx.base_state_hash
        tx.rolled_back = True
        tx.draft_state = None
        tx.draft_patch = None
        tx.draft_patches = []
        tx.draft_state_hash = None
        tx.world_patch_payload_hash = None
        tx.metadata["tx_status"] = "rolled_back"

        receipt: Dict[str, Any] = {
            "tx_id": tx.tx_id,
            "rollback_reason": str(tx.metadata.get("rollback_reason") or "user"),
            "base_state_hash": tx.base_state_hash,
        }
        self._append_audit_trace(
            tx,
            phase="rollback",
            before_hash=before_hash,
            after_hash=tx.base_state_hash,
        )
        tx.metadata["audit_trace"] = tx.audit_trace
        tx.metadata["rollback_receipt"] = receipt
        return receipt

    def _append_node(self, tx: Transaction, node: StoryNode) -> None:
        if tx.draft_state is None:
            raise RuntimeError("TX_DRAFT_STATE_NOT_AVAILABLE")

        tx.nodes.append(node)
        tx.draft_graph.append_node(node)
        tx.draft_state.last_node_id = node.node_id

        patch = node.state_patch or {}
        if "silence_count" in patch:
            tx.draft_state.silence_count = int(patch["silence_count"])
        if "phase" in patch and patch["phase"] != tx.draft_state.phase:
            tx.draft_state.phase = str(patch["phase"])
            tx.phase_change_count += 1
        if "tension" in patch:
            tx.draft_state.tension = int(patch["tension"])

    def _next_node_id(
        self,
        tx: Transaction,
        *,
        node_type: str,
        event_type: str,
        event_text: str,
    ) -> str:
        seq = len(tx.nodes) + 1
        digest = _stable_hash(
            {
                "base_state_hash": tx.base_state_hash,
                "seq": seq,
                "node_type": node_type,
                "event_type": event_type,
                "event_text": event_text,
            }
        )
        return f"node_{digest[:10]}"

    def _ensure_tx_active(self, tx: Transaction, *, operation: str) -> None:
        if tx.committed:
            raise RuntimeError(f"TX_ALREADY_COMMITTED:{operation}")
        if tx.rolled_back:
            raise RuntimeError(f"TX_ALREADY_ROLLED_BACK:{operation}")

    def _run_world_dry_run(self, event: Dict[str, Any], state: InternalState) -> Dict[str, Any]:
        fallback_world_patch_payload_hash = _phase4_world_patch_payload_hash(state)

        if self._dry_run_fn is None:
            return {
                "status": "PASS",
                "world_patch_payload_hash": fallback_world_patch_payload_hash,
                "world_patch_hash": fallback_world_patch_payload_hash,
            }

        payload = self._dry_run_fn(event, state)
        if not isinstance(payload, dict):
            return {"status": "FAIL", "reason": "INVALID_DRY_RUN_PAYLOAD"}

        status = str(payload.get("status", "FAIL")).upper()
        if status not in {"PASS", "FAIL"}:
            return {"status": "FAIL", "reason": "INVALID_DRY_RUN_STATUS"}

        normalized = dict(payload)
        world_patch_payload_hash = self._resolve_world_patch_payload_hash(
            normalized,
            fallback_hash=fallback_world_patch_payload_hash,
        )
        normalized["world_patch_payload_hash"] = world_patch_payload_hash
        normalized["world_patch_hash"] = world_patch_payload_hash
        return normalized

    def _resolve_world_patch_payload_hash(self, dry_run: Dict[str, Any], *, fallback_hash: str) -> str:
        world_patch = dry_run.get("world_patch")
        if isinstance(world_patch, dict):
            payload_hash = world_patch.get("payload_hash")
            if isinstance(payload_hash, str) and payload_hash.strip():
                return payload_hash.strip()
            if "payload" in world_patch:
                return stable_hash_v2(world_patch.get("payload"))

        if "world_patch_payload" in dry_run:
            return stable_hash_v2(dry_run.get("world_patch_payload"))

        payload_hash_value = dry_run.get("world_patch_payload_hash")
        if isinstance(payload_hash_value, str) and payload_hash_value.strip():
            return payload_hash_value.strip()

        return fallback_hash

    def _append_audit_trace(
        self,
        tx: Transaction,
        *,
        phase: str,
        before_hash: str | None,
        after_hash: str | None,
        event_id: str | None = None,
        failure_code: str | None = None,
    ) -> None:
        tx.audit_trace.append(
            {
                "tx_id": tx.tx_id,
                "phase": phase,
                "event_id": event_id,
                "before_hash": before_hash,
                "after_hash": after_hash,
                "failure_code": failure_code,
            }
        )
