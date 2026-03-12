# Story → TRNG → World 三层时序图（Phase 3A）

## 说明
- 本图用于冻结接入顺序，不表示已接线。
- 强约束：World execute 必须 after-commit。

```mermaid
sequenceDiagram
  autonumber
  participant S as Story Layer
  participant T as TRNG Shell
  participant W as World Layer

  S->>T: begin_tx(committed_graph, committed_state)
  T-->>S: tx(draft_graph, draft_state)

  S->>T: apply_event(tx, event)
  T->>W: world_dry_run(event, draft_state)
  W-->>T: dry_run_result(world_patch_hash / fail_reason)

  alt dry_run fail
    T->>T: append reject node
  else dry_run pass
    T->>T: append normal/silence node
  end

  S->>T: commit(tx, rule_version)
  T->>T: invariant_check

  alt invariant failed
    T-->>S: InvariantViolation
    S->>T: rollback(tx)
  else invariant pass
    T-->>S: committed(graph + internal_state)
    S->>W: enqueue_execute(after_commit)
  end
```

## 不可触碰边界
- TRNG 不决定 projection。
- TRNG 不直接执行 executor。
- TRNG 不读取世界实时状态。
- TRNG 不修改 payload/schema/rule gate。
