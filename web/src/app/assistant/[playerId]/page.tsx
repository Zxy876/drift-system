import Link from "next/link";

import { fetchIntentTrace } from "@/lib/drift-backend";

type AssistantPageProps = {
  params: Promise<{ playerId: string }>;
};

type JsonMap = Record<string, unknown>;

function asObject(value: unknown): JsonMap | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as JsonMap;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function pickPlayerInput(debugTasks: JsonMap | null, worldState: JsonMap | null): string {
  const candidates = [
    asString(asObject(debugTasks?.scene_generation)?.last_player_input && asObject(asObject(debugTasks?.scene_generation)?.last_player_input)?.text),
    asString(asObject(debugTasks?.player_input)?.text),
    asString(asObject(asObject(debugTasks?.last_rule_event)?.raw_payload)?.text),
    asString(asObject(asObject(debugTasks?.last_rule_event)?.raw_payload)?.message),
    asString(asObject(asObject(debugTasks?.last_rule_event)?.raw_payload)?.say),
    asString(asObject(worldState?.narrative_decision)?.scene_hint),
  ];

  for (const item of candidates) {
    if (item) {
      return item;
    }
  }
  return "";
}

function pickIntent(debugTasks: JsonMap | null, worldState: JsonMap | null): JsonMap | null {
  return (
    asObject(asObject(debugTasks?.scene_generation)?.last_intent) ??
    asObject(debugTasks?.last_intent) ??
    asObject(asObject(asObject(worldState?.narrative_state)?.last_decision)?.intent) ??
    asObject(asObject(worldState?.last_decision)?.intent) ??
    null
  );
}

function pickRegistryResources(debugTasks: JsonMap | null): { matchTag: string; resources: JsonMap } {
  const sceneGeneration = asObject(debugTasks?.scene_generation);
  const resources =
    asObject(debugTasks?.registry_resources) ??
    asObject(sceneGeneration?.registry_resources) ??
    asObject(asObject(debugTasks?.prediction)?.registry_resources) ??
    {};

  const matchTag =
    asString(debugTasks?.registry_match_tag) ||
    asString(sceneGeneration?.registry_match_tag) ||
    asString(asObject(debugTasks?.prediction)?.registry_match_tag);

  return {
    matchTag,
    resources,
  };
}

function pickWorldPatch(debugTasks: JsonMap | null, worldState: JsonMap | null): JsonMap | null {
  const sceneGeneration = asObject(debugTasks?.scene_generation);
  return (
    asObject(asObject(sceneGeneration?.last_rule_event_result)?.world_patch) ??
    asObject(asObject(asObject(debugTasks?.last_rule_event)?.raw_payload)?.world_patch) ??
    asObject(asObject(debugTasks?.result)?.world_patch) ??
    asObject(debugTasks?.world_patch) ??
    asObject(worldState?.world_patch) ??
    null
  );
}

function actionSummary(worldPatch: JsonMap | null): string {
  const mc = asObject(worldPatch?.mc);
  if (!mc) {
    return "暂无可执行 world_patch";
  }

  const spawn = asObject(mc.spawn);
  if (spawn) {
    return `生成实体：${asString(spawn.type) || "villager"}`;
  }

  const blocks = Array.isArray(mc.blocks) ? mc.blocks : [];
  if (blocks.length > 0) {
    const first = asObject(blocks[0]);
    return `放置方块：${asString(first?.type) || "(unknown)"}`;
  }

  const buildMulti = Array.isArray(mc.build_multi) ? mc.build_multi : [];
  if (buildMulti.length > 0) {
    return `构建动作：${buildMulti.length} 项`;
  }

  if (asString(mc.time)) {
    return `时间控制：${asString(mc.time)}`;
  }

  if (asString(mc.weather)) {
    return `天气控制：${asString(mc.weather)}`;
  }

  return "已生成 patch，但未识别动作摘要";
}

export default async function AssistantPlayerPage({ params }: AssistantPageProps) {
  const { playerId } = await params;
  const trace = await fetchIntentTrace(playerId);

  const payload = asObject(trace.data);
  const debugTasks = asObject(payload?.debug_tasks);
  const worldState = asObject(payload?.world_state);

  const inputText = pickPlayerInput(debugTasks, worldState);
  const intent = pickIntent(debugTasks, worldState);
  const intentType = asString(intent?.type) || "UNKNOWN";
  const confidence = asNumber(intent?.confidence);

  const { matchTag, resources } = pickRegistryResources(debugTasks);
  const firstResource = Object.keys(resources)[0] || "(none)";

  const worldPatch = pickWorldPatch(debugTasks, worldState);
  const gate =
    asObject(debugTasks?.generation_policy_gate) ??
    asObject(worldState?.generation_policy_gate) ??
    {};

  const gateAllowed = typeof gate.allowed === "boolean" ? Boolean(gate.allowed) : null;
  const gateReason = asString(gate.reason);
  const worldResultText = worldPatch
    ? "生成成功"
    : gateAllowed === false
      ? `生成失败：${gateReason || "冷却中或策略拦截"}`
      : "尚未生成（等待新事件）";

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-4 px-6 py-8">
      <header className="rounded-xl border border-black/10 p-5 dark:border-white/20">
        <h1 className="text-2xl font-semibold">Assistant</h1>
        <p className="mt-2 text-sm opacity-80">路由：/assistant/{playerId}</p>
        <p className="text-sm opacity-80">目标：把输入 → 理解 → 动作 → 结果可解释化。</p>
      </header>

      {!trace.ok && (
        <section className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm">
          <h2 className="font-semibold">Backend 请求失败</h2>
          <p className="mt-1">{trace.error || "unknown error"}</p>
        </section>
      )}

      <section className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">玩家输入</h2>
        <p className="mt-2 text-sm">你说：{inputText || "(暂无输入)"}</p>
      </section>

      <section className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">系统理解</h2>
        <div className="mt-2 space-y-1 text-sm">
          <p>意图：{intentType}</p>
          <p>标签：{matchTag || "(none)"}</p>
          <p>资源：{firstResource}</p>
          <p>置信度：{confidence === null ? "(unknown)" : confidence}</p>
        </div>
      </section>

      <section className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">系统动作</h2>
        <p className="mt-2 text-sm">{actionSummary(worldPatch)}</p>
      </section>

      <section className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">世界结果</h2>
        <p className="mt-2 text-sm">{worldResultText}</p>
      </section>

      <section className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">下一步建议</h2>
        <ul className="mt-2 list-disc pl-5 text-sm">
          <li>生成 camp</li>
          <li>生成 temple</li>
          <li>生成 fire</li>
        </ul>
      </section>

      <footer className="text-xs opacity-75">
        <Link className="underline" href={`/intent/${encodeURIComponent(playerId)}`}>
          查看完整调试页（Intent Debugger）
        </Link>
      </footer>
    </main>
  );
}
