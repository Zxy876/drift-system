# Drift × TRNG 分层接入结构（Phase 3A）

## 接入目标
- 仅引入 Transaction Shell（事务壳）。
- 不替代现有世界层，不改变 payload/executor/schema/rule gate。

## Mermaid（控制分层）

```mermaid
flowchart TD
  U[Input Event]
  TX[TRNG Transaction Shell\nbegin_tx / apply / commit / rollback]
  DRAFT[draftState + draftGraph]
  INV[invariant_check]
  DRY[world_dry_run adapter]
  COMMIT[atomic commit\n(graph + internal state)]
  ENQ[enqueue world execute\nafter commit]

  U --> TX --> DRAFT --> DRY --> INV --> COMMIT --> ENQ

  subgraph IMMUTABLE[Do Not Touch in Phase 3A]
    MAP[v2 mapper]
    REG[projection rule registry]
    PAY[payload schema]
    EXE[executor]
    GATE[gate mechanism]
  end

  DRY -. read-only integration .-> MAP
  DRY -. read-only integration .-> REG
  ENQ -. existing path .-> EXE
```

## Phase 3A 允许改动
- `backend/app/core/trng/transaction.py`
- `backend/app/core/trng/graph_state.py`
- `backend/app/core/trng/invariant_check.py`

## 契约与时序文档
- `docs/payload_v2/TRNG_SHELL_API.md`
- `docs/payload_v2/TRNG_STORY_WORLD_SEQUENCE.md`

## Phase 3A 禁止改动
- projection rules
- rule_version
- payload schema
- executor behavior
- Gate policy

## 事务约束
- 每次输入至少 1 个节点。
- graph/state 同成同败。
- commit 前 draft 不可见。
- world execute 只能在 commit 后排队。
