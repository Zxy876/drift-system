from __future__ import annotations

from typing import List

from .graph_state import GraphState, InternalState, StoryNode


class InvariantViolation(Exception):
    pass


def check_tx_invariants(
    *,
    committed_graph: GraphState,
    committed_state: InternalState,
    draft_graph: GraphState,
    draft_state: InternalState,
    tx_nodes: list[StoryNode],
    phase_change_count: int,
    base_state_hash: str | None = None,
    committed_state_hash_before: str | None = None,
    root_from_node: str | None = None,
    draft_state_hash: str | None = None,
    computed_draft_state_hash: str | None = None,
    world_patch_payload_hash: str | None = None,
    expected_world_patch_payload_hash: str | None = None,
    commit_publish_count: int = 0,
) -> List[str]:
    errors: List[str] = []

    if len(tx_nodes) < 1:
        errors.append("TX_MUST_CREATE_AT_LEAST_ONE_NODE")

    if not draft_graph.nodes:
        errors.append("GRAPH_EMPTY_AFTER_TX")

    if draft_graph.current_node_id != (draft_graph.nodes[-1].node_id if draft_graph.nodes else None):
        errors.append("CURRENT_NODE_NOT_AT_GRAPH_TAIL")

    if draft_state.last_node_id != draft_graph.current_node_id:
        errors.append("STATE_LAST_NODE_MISMATCH")

    if phase_change_count > 1:
        errors.append("PHASE_CHANGED_MORE_THAN_ONCE")

    if len(draft_graph.nodes) < len(committed_graph.nodes):
        errors.append("GRAPH_SHRINK_NOT_ALLOWED")

    if len(draft_graph.nodes) == len(committed_graph.nodes):
        errors.append("GRAPH_NOT_ADVANCED")

    if draft_state.silence_count < committed_state.silence_count:
        errors.append("SILENCE_COUNT_DECREASE_NOT_ALLOWED")

    if base_state_hash is not None and committed_state_hash_before is not None:
        if str(base_state_hash) != str(committed_state_hash_before):
            errors.append("ISOLATION_BASE_STATE_HASH_MISMATCH")

    if root_from_node is not None and committed_graph.current_node_id != root_from_node:
        errors.append("ISOLATION_COMMITTED_GRAPH_MOVED")

    if draft_state_hash is not None and computed_draft_state_hash is not None:
        if str(draft_state_hash) != str(computed_draft_state_hash):
            errors.append("DRAFT_STATE_HASH_BINDING_MISMATCH")

    if not world_patch_payload_hash:
        errors.append("WORLD_PATCH_PAYLOAD_HASH_MISSING")

    if expected_world_patch_payload_hash is not None and world_patch_payload_hash is not None:
        if str(expected_world_patch_payload_hash) != str(world_patch_payload_hash):
            errors.append("WORLD_PATCH_PAYLOAD_HASH_BINDING_MISMATCH")

    if int(commit_publish_count) > 0:
        errors.append("ATOMICITY_COMMIT_ALREADY_PUBLISHED")

    return errors


def assert_tx_invariants(**kwargs) -> None:
    errors = check_tx_invariants(**kwargs)
    if errors:
        raise InvariantViolation(";".join(errors))
