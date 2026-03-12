# Phase 0 → Phase 3 Architecture (Control-Layer View)

## 目标
- 这不是功能图，而是控制层级图。
- 强调 Drift 的核心控制点在 Decision + Rule + Hash + Version Gate。

## Mermaid 架构图

```mermaid
flowchart TD
  NL[User NL Input]
  SCENE[Scene Extraction v1.8\nscene_spec + semantic_effects]
  MAPPER[v2 Decision Engine\nOK / DEGRADED / REJECTED]
  REGISTRY[Projection Rule Registry\nversioned rules]
  STRUCTURE[Structure Merge\n(scene projection + structure spec)]
  VALIDATE[Validator Layer]
  PAYLOAD{Payload Version Gate}

  EXEC_V1[Executor v1\nblock-only]
  EXEC_V2[Executor v2\nblock + entity]
  REPLAY_V1[Replay Engine v1]
  REPLAY_V2[Replay Engine v2]

  HASH[Hash Canonicalization\nfinal_commands_hash]
  TRACE[Decision Trace + Evidence]

  NL --> SCENE --> MAPPER --> REGISTRY --> STRUCTURE --> VALIDATE --> PAYLOAD

  VALIDATE --> HASH
  MAPPER --> TRACE
  REGISTRY --> TRACE
  HASH --> TRACE

  PAYLOAD -->|v1| EXEC_V1 --> REPLAY_V1
  PAYLOAD -->|v2| EXEC_V2 --> REPLAY_V2

  subgraph CORE[Drift Control Core]
    MAPPER
    REGISTRY
    HASH
    PAYLOAD
  end

  subgraph PHASES[Phase Evolution]
    P0[Phase 0\nBlock Engine]
    P1[Phase 1\nDecision Engine]
    P18[Phase 1.8\nSemantic Extraction]
    P2[Phase 2\nDeterministic Projection]
    P21[Phase 2.1\nRule Freeze]
    P22[Phase 2.2\nCompatibility Freeze]
    P3[Phase 3\nExecutor/Replay Upgrade]
  end

  P0 --> P1 --> P18 --> P2 --> P21 --> P22 --> P3

  subgraph GATES[Phase 3 Startup Gates]
    G1[Gate 1\nSchema Freeze]
    G2[Gate 2\nReplay Determinism]
    G3[Gate 3\nHash Consistency]
    G4[Gate 4\nStrict Reject Integrity]
    G5[Gate 5\nCompatibility Rejection]
    G6[Gate 6\nRule Immutability]
    G7[Gate 7\nRollback Safety]
  end

  P22 -. must pass .-> G1
  P22 -. must pass .-> G2
  P22 -. must pass .-> G3
  P22 -. must pass .-> G4
  P22 -. must pass .-> G5
  P22 -. must pass .-> G6
  P22 -. must pass .-> G7
  G1 --> P3
  G2 --> P3
  G3 --> P3
  G4 --> P3
  G5 --> P3
  G6 --> P3
  G7 --> P3
```

## 读图要点
- `Drift Control Core` 是系统内核：`Decision Engine + Projection Registry + Hash Canonicalization + Payload Version Gate`。
- `Executor` 是执行壳，不是控制中枢。
- Phase 3 不是功能推进，而是“门禁通过后的升级执行阶段”。

## 与现有文档关系
- Gate 定义：`PHASE3_GATE_CHECKLIST.md`
- 协议与兼容：`COMPATIBILITY_MATRIX.md`、`PAYLOAD_V2_ENTITY_SCHEMA_DRAFT.md`
- Hash 冻结：`ENTITY_HASH_CANONICALIZATION_RULES.md`
- 回放与执行路径：`REPLAY_UPGRADE_NOTES.md`、`EXECUTOR_UPGRADE_PATH.md`
