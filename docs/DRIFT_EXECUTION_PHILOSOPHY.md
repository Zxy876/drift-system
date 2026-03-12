# Drift Execution Philosophy

## 1) Determinism over Feature
功能扩展必须服从可重复执行。

- 禁止随机路径影响最终命令。
- 禁止 tick/runtime 漂移影响同输入结果。
- 新能力进入前必须先定义可验证不变量。

## 2) Replay before Runtime
先保证可回放，再讨论运行时体验。

- 升级顺序必须是 replay 能力先行。
- 任何 runtime 新能力都必须可被 replay 等价验证。
- 不能回放的能力不得进入主路径。

## 3) Version over Mutation
通过版本演进，不在原位篡改。

- schema、rule、hash 规则都使用版本化升级。
- 禁止修改历史版本定义来“修复”当前问题。
- 历史关卡必须可在原版本语义下重放。

## 4) Reject over Guess
不支持就拒绝，不做隐式猜测。

- strict 模式失败必须明确返回稳定错误码。
- default 模式降级必须可证明（原因、损失、路径）。
- 不允许 silent fail、不允许幻觉式容错。

## 5) Trace over Trust
所有关键决策必须可审计。

- 记录 rule_version / engine_version / decision trace。
- 记录 hash 闭环（输入、场景、最终命令）。
- 争议场景以 trace 和规则为唯一裁决依据。

## 执行准则（简版）
- 任何新能力进入系统前，先问三件事：
  1. 是否 deterministic？
  2. 是否 replay-safe？
  3. 是否可 trace 复盘？
- 任一答案为否，则该能力不得上线。
