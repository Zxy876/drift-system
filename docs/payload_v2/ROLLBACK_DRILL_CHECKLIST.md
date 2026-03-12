# Rollback Drill Checklist (Feature Flag)

## 目标
验证 payload_v2 开关可在故障时安全回退到 v1 体系，且不污染数据。

## 前置条件
- 具备可切换环境变量或配置开关：
  - `DRIFT_ENABLE_PAYLOAD_V2`
  - `DRIFT_USE_V2_MAPPER`
- 保留 v1 主路径可运行。

## 演练步骤
1. 基线运行（v1）
   - 设置：`DRIFT_ENABLE_PAYLOAD_V2=false`
   - 验证：v1 payload 生成与执行正常。

2. 打开 v2（沙盒）
   - 设置：`DRIFT_ENABLE_PAYLOAD_V2=true`
   - 验证：仅沙盒通道接收 v2，记录 hash/replay/拒绝日志。

3. 强制回退
   - 设置：`DRIFT_ENABLE_PAYLOAD_V2=false`
   - 验证：
     - `scene_orchestrator_v1` 可完整运行
     - payload_v1 不受污染
     - replay_v1 可继续工作

4. 回退后对比
   - 对比回退前后 v1 输出一致性（同输入同 hash）。

## 成功标准
- 回退全程无 silent fail。
- 回退时间在目标阈值内（由运维定义）。
- 回退后 v1 回归用例全部通过。

## 失败标准
- 回退后出现 v2 残留行为。
- v1 生成或 replay 异常。
- 错误码不稳定或缺失。

## 证据产物
- 回退操作日志
- 回退前后 hash 对比
- 回归测试报告
