"use client";

import { useState, useTransition } from "react";

import { useRouter } from "next/navigation";

import {
  updateGenerationPolicy,
  type GenerationPolicyPayload,
} from "@/lib/drift-backend";

type JsonMap = Record<string, unknown>;

type IntentDebuggerClientProps = {
  playerId: string;
  payload: JsonMap | null;
  ok: boolean;
  error: string | null;
};

type SemanticScoreRow = {
  tag: string;
  score: number;
};

type SceneTimelineRow = {
  atMs: number;
  type: string;
  reason: string;
  generated: boolean;
  nextAvailableIn: number | null;
  intervalSincePrevGeneratedS: number | null;
};

function asObject(value: unknown): JsonMap | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as JsonMap;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
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

function getPath(root: unknown, path: Array<string | number>): unknown {
  let cursor: unknown = root;
  for (const token of path) {
    if (typeof token === "number") {
      if (!Array.isArray(cursor) || token < 0 || token >= cursor.length) {
        return undefined;
      }
      cursor = cursor[token];
      continue;
    }

    if (!cursor || typeof cursor !== "object" || Array.isArray(cursor)) {
      return undefined;
    }
    cursor = (cursor as JsonMap)[token];
  }
  return cursor;
}

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const rows: string[] = [];
  const seen = new Set<string>();

  for (const item of value) {
    const token = asString(item);
    if (!token || seen.has(token)) {
      continue;
    }
    seen.add(token);
    rows.push(token);
  }

  return rows;
}

function normalizeCommandList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const rows: string[] = [];
  const seen = new Set<string>();

  for (const item of value) {
    let text = "";
    if (typeof item === "string") {
      text = item.trim();
    } else if (item && typeof item === "object") {
      text = JSON.stringify(item);
    }

    if (!text || seen.has(text)) {
      continue;
    }

    seen.add(text);
    rows.push(text);
  }

  return rows;
}

function normalizeStatus(value: unknown, fallback = "UNKNOWN"): string {
  const token = asString(value);
  if (!token) {
    return fallback;
  }
  return token.toUpperCase();
}

function formatTimeMs(value: number | null): string {
  if (value === null || !Number.isFinite(value) || value <= 0) {
    return "(unknown)";
  }
  try {
    return new Date(value).toLocaleTimeString("zh-CN", { hour12: false });
  } catch {
    return String(value);
  }
}

function normalizeSceneTimelineRows(value: unknown): SceneTimelineRow[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const rows: SceneTimelineRow[] = [];
  for (const item of value) {
    const row = asObject(item);
    if (!row) {
      continue;
    }

    const atMs = asNumber(row.at_ms);
    if (atMs === null || atMs <= 0) {
      continue;
    }

    rows.push({
      atMs,
      type: asString(row.type) || "scene_unknown",
      reason: asString(row.reason) || "unknown",
      generated: Boolean(row.generated),
      nextAvailableIn: asNumber(row.next_available_in),
      intervalSincePrevGeneratedS: asNumber(row.interval_since_prev_generated_s),
    });
  }

  return rows;
}

function normalizeGenerationPolicy(value: unknown): GenerationPolicyPayload | null {
  const row = asObject(value);
  if (!row) {
    return null;
  }

  const sceneCooldown = asNumber(row.scene_cooldown);
  const spawnProbability = asNumber(row.spawn_probability);
  const maxScenesPerHour = asNumber(row.max_scenes_per_hour);
  const spawnDistance = asNumber(row.spawn_distance);

  if (sceneCooldown === null || sceneCooldown < 0) {
    return null;
  }
  if (spawnProbability === null || spawnProbability < 0 || spawnProbability > 1) {
    return null;
  }
  if (maxScenesPerHour === null || maxScenesPerHour < 1 || !Number.isInteger(maxScenesPerHour)) {
    return null;
  }
  if (spawnDistance === null || spawnDistance < 0) {
    return null;
  }

  return {
    scene_cooldown: sceneCooldown,
    spawn_probability: spawnProbability,
    max_scenes_per_hour: maxScenesPerHour,
    spawn_distance: spawnDistance,
    require_player_movement: Boolean(row.require_player_movement),
    require_new_location: Boolean(row.require_new_location),
  };
}

function applySuggestedPolicyPatch(
  basePolicy: GenerationPolicyPayload | null,
  patch: JsonMap | null,
): GenerationPolicyPayload | null {
  if (!basePolicy || !patch) {
    return null;
  }

  const nextPolicy: GenerationPolicyPayload = { ...basePolicy };
  let changed = false;

  const sceneCooldown = asNumber(patch.scene_cooldown);
  if (sceneCooldown !== null && sceneCooldown >= 0 && sceneCooldown !== nextPolicy.scene_cooldown) {
    nextPolicy.scene_cooldown = sceneCooldown;
    changed = true;
  }

  const spawnProbability = asNumber(patch.spawn_probability);
  if (spawnProbability !== null && spawnProbability >= 0 && spawnProbability <= 1 && spawnProbability !== nextPolicy.spawn_probability) {
    nextPolicy.spawn_probability = spawnProbability;
    changed = true;
  }

  const maxScenesPerHour = asNumber(patch.max_scenes_per_hour);
  if (
    maxScenesPerHour !== null &&
    maxScenesPerHour >= 1 &&
    Number.isInteger(maxScenesPerHour) &&
    maxScenesPerHour !== nextPolicy.max_scenes_per_hour
  ) {
    nextPolicy.max_scenes_per_hour = maxScenesPerHour;
    changed = true;
  }

  const spawnDistance = asNumber(patch.spawn_distance);
  if (spawnDistance !== null && spawnDistance >= 0 && spawnDistance !== nextPolicy.spawn_distance) {
    nextPolicy.spawn_distance = spawnDistance;
    changed = true;
  }

  if (typeof patch.require_player_movement === "boolean" && patch.require_player_movement !== nextPolicy.require_player_movement) {
    nextPolicy.require_player_movement = patch.require_player_movement;
    changed = true;
  }

  if (typeof patch.require_new_location === "boolean" && patch.require_new_location !== nextPolicy.require_new_location) {
    nextPolicy.require_new_location = patch.require_new_location;
    changed = true;
  }

  return changed ? nextPolicy : null;
}

function scoreFromReason(reason: string): number | null {
  const match = reason.match(/score=([0-9]+(?:\.[0-9]+)?)/i);
  if (!match) {
    return null;
  }
  return asNumber(match[1]);
}

function deriveEquivalentCommands(worldPatch: JsonMap | null, explicitCommands: string[]): string[] {
  const rows: string[] = [...explicitCommands];
  const seen = new Set(rows);

  const mc = asObject(worldPatch?.mc);
  if (!mc) {
    return rows;
  }

  const timeToken = asString(mc.time);
  if (timeToken) {
    const cmd = `/time set ${timeToken}`;
    if (!seen.has(cmd)) {
      seen.add(cmd);
      rows.push(cmd);
    }
  }

  const weatherToken = asString(mc.weather);
  if (weatherToken) {
    const cmd = `/weather ${weatherToken}`;
    if (!seen.has(cmd)) {
      seen.add(cmd);
      rows.push(cmd);
    }
  }

  const spawn = asObject(mc.spawn);
  if (spawn) {
    const entity = asString(spawn.type) || "villager";
    const offset = asObject(spawn.offset);
    const dx = asNumber(offset?.dx) ?? 0;
    const dy = asNumber(offset?.dy) ?? 0;
    const dz = asNumber(offset?.dz) ?? 0;
    const cmd = `/summon ${entity} ~${dx} ~${dy} ~${dz}`;
    if (!seen.has(cmd)) {
      seen.add(cmd);
      rows.push(cmd);
    }
  }

  const build = mc.build;
  if (build !== undefined) {
    const buildToken = asString((asObject(build) ?? {}).id) || asString(build);
    const cmd = buildToken
      ? `/function drift:build/${buildToken}`
      : `/function drift:build/default`;
    if (!seen.has(cmd)) {
      seen.add(cmd);
      rows.push(cmd);
    }
  }

  return rows;
}

function extractPrimaryInput(worldState: JsonMap | null, debugTasks: JsonMap | null): {
  text: string;
  source: string;
} {
  const candidates: Array<{ source: string; text: string }> = [
    {
      source: "debug.scene_generation.last_player_input.text",
      text: asString(getPath(debugTasks, ["scene_generation", "last_player_input", "text"])),
    },
    {
      source: "debug.player_input.text",
      text: asString(getPath(debugTasks, ["player_input", "text"])),
    },
    {
      source: "debug.last_rule_event.raw_payload.text",
      text: asString(getPath(debugTasks, ["last_rule_event", "raw_payload", "text"])),
    },
    {
      source: "debug.last_rule_event.raw_payload.message",
      text: asString(getPath(debugTasks, ["last_rule_event", "raw_payload", "message"])),
    },
    {
      source: "debug.last_rule_event.raw_payload.say",
      text: asString(getPath(debugTasks, ["last_rule_event", "raw_payload", "say"])),
    },
    {
      source: "debug.scene_generation.scene_hint",
      text: asString(getPath(debugTasks, ["scene_generation", "scene_hint"])),
    },
    {
      source: "world.narrative_decision.input_snapshot.scene_hint",
      text: asString(getPath(worldState, ["narrative_decision", "input_snapshot", "scene_hint"])),
    },
  ];

  for (const row of candidates) {
    if (row.text) {
      return row;
    }
  }

  return {
    text: "",
    source: "(none)",
  };
}

function toPrettyJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

export default function IntentDebuggerClient({ playerId, payload, ok, error }: IntentDebuggerClientProps) {
  const router = useRouter();
  const [isRefreshingTrace, startRefreshTrace] = useTransition();

  const worldState = asObject(payload?.world_state);
  const debugTasks = asObject(payload?.debug_tasks);
  const sceneGeneration = asObject(getPath(debugTasks, ["scene_generation"])) ?? {};
  const debugTasksError = asString(payload?.debug_tasks_error);

  const primaryInput = extractPrimaryInput(worldState, debugTasks);

  const lastIntentSummary =
    asObject(getPath(debugTasks, ["scene_generation", "last_intent"])) ??
    asObject(getPath(debugTasks, ["last_intent"])) ??
    asObject(getPath(worldState, ["narrative_state", "last_decision", "intent"])) ??
    asObject(getPath(worldState, ["last_decision", "intent"])) ??
    null;

  const narrativeDecision =
    asObject(worldState?.narrative_decision) ??
    asObject(worldState?.last_decision) ??
    asObject(getPath(worldState, ["narrative_state", "last_decision"])) ??
    {};

  const intentReason = asString(narrativeDecision.reason);
  const intentType =
    asString(lastIntentSummary?.type) ||
    asString(getPath(debugTasks, ["last_rule_event", "event", "event_type"])) ||
    asString(getPath(debugTasks, ["last_rule_event", "event", "type"])) ||
    asString(getPath(debugTasks, ["last_rule_event", "event", "quest_event"])) ||
    (intentReason ? "NARRATIVE_DECISION" : "UNKNOWN");

  const confidence =
    asNumber(lastIntentSummary?.confidence) ??
    asNumber(getPath(debugTasks, ["prediction", "semantic_score"])) ??
    asNumber(getPath(debugTasks, ["scene_generation", "candidate_scores", 0, "score"])) ??
    scoreFromReason(intentReason);

  const intentParams =
    asObject(getPath(debugTasks, ["last_rule_event", "raw_payload"])) ??
    lastIntentSummary ??
    asObject(narrativeDecision.input_snapshot) ??
    null;

  const sourceA = asObject(getPath(debugTasks, ["scene_generation", "semantic_scores"]));
  const sourceB = asObject(getPath(debugTasks, ["prediction", "semantic_scores"]));
  const sourceC = asObject(getPath(debugTasks, ["prediction", "all_scores"]));
  const mergedSemanticScores: Record<string, number> = {};

  for (const source of [sourceA, sourceB, sourceC]) {
    if (!source) {
      continue;
    }
    for (const [tag, rawScore] of Object.entries(source)) {
      const token = asString(tag);
      const score = asNumber(rawScore);
      if (!token || score === null) {
        continue;
      }
      mergedSemanticScores[token] = Math.max(mergedSemanticScores[token] ?? 0, score);
    }
  }

  const semanticScoreRows: SemanticScoreRow[] = Object.entries(mergedSemanticScores)
    .map(([tag, score]) => ({ tag, score }))
    .sort((a, b) => (b.score === a.score ? a.tag.localeCompare(b.tag) : b.score - a.score));

  const matchedTags = semanticScoreRows.map((row) => row.tag);

  const selectedAssets = normalizeStringList(worldState?.selected_assets);
  const inventoryResources = asObject(getPath(debugTasks, ["inventory_resources"])) ??
    asObject(getPath(debugTasks, ["level_evolution", "signals", "inventory_resources"])) ??
    {};
  const registryResources =
    asObject(getPath(debugTasks, ["registry_resources"])) ??
    asObject(getPath(sceneGeneration, ["registry_resources"])) ??
    asObject(getPath(debugTasks, ["prediction", "registry_resources"])) ??
    {};
  const registryMatchTag =
    asString(getPath(debugTasks, ["registry_match_tag"])) ||
    asString(getPath(sceneGeneration, ["registry_match_tag"])) ||
    asString(getPath(debugTasks, ["prediction", "registry_match_tag"]));
  const registryBindings = asArray(getPath(sceneGeneration, ["registry_bindings"]));

  const resourceMappings: string[] = [];

  resourceMappings.push(...selectedAssets.map((asset) => `selected_asset: ${asset}`));

  if (registryMatchTag) {
    resourceMappings.push(`registry_match_tag: ${registryMatchTag}`);
  }

  if (registryBindings.length > 0) {
    resourceMappings.push(`registry_bindings: ${registryBindings.length}`);
  }

  for (const [key, value] of Object.entries(registryResources)) {
    const amount = asNumber(value);
    if (!key || amount === null) {
      continue;
    }
    resourceMappings.push(`registry: ${key} = ${amount}`);
  }

  for (const [key, value] of Object.entries(inventoryResources)) {
    const amount = asNumber(value);
    if (!key || amount === null) {
      continue;
    }
    resourceMappings.push(`inventory: ${key} = ${amount}`);
  }

  const sources = asArray(worldState?.asset_sources);
  for (const item of sources) {
    if (typeof item === "string") {
      resourceMappings.push(`asset_source: ${item}`);
      continue;
    }

    const row = asObject(item);
    if (!row) {
      continue;
    }

    const id = asString(row.resource_id) || asString(row.id) || asString(row.asset_id);
    const source = asString(row.source) || asString(row.provider) || asString(row.namespace);
    const tag = asString(row.tag) || asString(row.semantic) || asString(row.semantic_tag);

    const segments = [id, source ? `source=${source}` : "", tag ? `tag=${tag}` : ""].filter(Boolean);
    if (segments.length > 0) {
      resourceMappings.push(`asset_source: ${segments.join(" · ")}`);
    }
  }

  const currentNode =
    asString(worldState?.current_node) ||
    asString(getPath(worldState, ["narrative_state", "current_node"]));

  const transitionCandidates =
    asArray(worldState?.transition_candidates).length > 0
      ? asArray(worldState?.transition_candidates)
      : asArray(getPath(worldState, ["narrative_state", "transition_candidates"]));

  const blockedBy =
    normalizeStringList(worldState?.blocked_by).length > 0
      ? normalizeStringList(worldState?.blocked_by)
      : normalizeStringList(getPath(worldState, ["narrative_state", "blocked_by"]));

  const selectedFragment =
    asString(sceneGeneration.selected_root) ||
    asString(getPath(debugTasks, ["prediction", "predicted_root"])) ||
    asString(getPath(worldState, ["theme_filter", "allowed_fragments", 0]));

  const rawGenerationPolicy =
    asObject(getPath(debugTasks, ["generation_policy"])) ??
    asObject(getPath(worldState, ["generation_policy"])) ??
    {};

  const [policyOverride, setPolicyOverride] = useState<GenerationPolicyPayload | null>(null);
  const [previewSuggestion, setPreviewSuggestion] = useState(false);
  const [applyingSuggestion, setApplyingSuggestion] = useState(false);
  const [applySuggestionInfo, setApplySuggestionInfo] = useState<string | null>(null);
  const [applySuggestionError, setApplySuggestionError] = useState<string | null>(null);

  const effectiveGenerationPolicy = policyOverride ?? normalizeGenerationPolicy(rawGenerationPolicy);
  const generationPolicySnapshot = effectiveGenerationPolicy ?? rawGenerationPolicy;

  const generationPolicyGate =
    asObject(getPath(debugTasks, ["generation_policy_gate"])) ??
    asObject(getPath(worldState, ["generation_policy_gate"])) ??
    {};

  const generationAllowed =
    typeof generationPolicyGate.allowed === "boolean" ? Boolean(generationPolicyGate.allowed) : null;
  const generationReason = asString(generationPolicyGate.reason);
  const generationNextAvailableIn = asNumber(generationPolicyGate.next_available_in);
  const scenesGeneratedLastHour =
    asNumber(getPath(debugTasks, ["scenes_generated_last_hour"])) ??
    asNumber(getPath(worldState, ["scenes_generated_last_hour"]));
  const scenesBlockedByPolicy =
    asNumber(getPath(debugTasks, ["scenes_blocked_by_policy"])) ??
    asNumber(getPath(worldState, ["scenes_blocked_by_policy"]));
  const policyBlockRate =
    asNumber(getPath(debugTasks, ["policy_block_rate"])) ??
    asNumber(getPath(worldState, ["policy_block_rate"]));
  const avgSceneInterval =
    asNumber(getPath(debugTasks, ["avg_scene_interval"])) ??
    asNumber(getPath(worldState, ["avg_scene_interval"]));
  const policyCooldownHits =
    asNumber(getPath(debugTasks, ["policy_cooldown_hits"])) ??
    asNumber(getPath(worldState, ["policy_cooldown_hits"]));
  const runtimeHealth =
    asObject(getPath(debugTasks, ["runtime_health"])) ??
    asObject(getPath(worldState, ["runtime_health"])) ??
    {};
  const pacingRecommendation =
    asObject(getPath(debugTasks, ["pacing_recommendation"])) ??
    asObject(getPath(worldState, ["pacing_recommendation"])) ??
    {};
  const sceneTimeline = normalizeSceneTimelineRows(
    asArray(getPath(debugTasks, ["scene_timeline"])).length > 0
      ? asArray(getPath(debugTasks, ["scene_timeline"]))
      : asArray(getPath(worldState, ["scene_timeline"])),
  );

  const sceneRateHealth = asObject(runtimeHealth.scene_rate) ?? {};
  const policyPressureHealth = asObject(runtimeHealth.policy_pressure) ?? {};
  const cooldownStressHealth = asObject(runtimeHealth.cooldown_stress) ?? {};

  const sceneRateStatus = normalizeStatus(sceneRateHealth.status);
  const policyPressureStatus = normalizeStatus(policyPressureHealth.status);
  const cooldownStressStatus = normalizeStatus(cooldownStressHealth.status);

  const recommendationStatus = normalizeStatus(pacingRecommendation.status, "NONE");
  const recommendationSeverity = normalizeStatus(pacingRecommendation.severity, "NONE");
  const recommendationCode = asString(pacingRecommendation.code) || "(none)";
  const recommendationMessage = asString(pacingRecommendation.message);
  const recommendationPatch = asObject(getPath(pacingRecommendation, ["suggested_policy_patch"]));
  const suggestedPolicy = applySuggestedPolicyPatch(effectiveGenerationPolicy, recommendationPatch);
  const suggestedCooldown = suggestedPolicy?.scene_cooldown ?? asNumber(getPath(pacingRecommendation, ["suggested_policy_patch", "scene_cooldown"]));
  const currentCooldown = effectiveGenerationPolicy?.scene_cooldown ?? asNumber(rawGenerationPolicy.scene_cooldown);

  const applySuggestion = async () => {
    if (!suggestedPolicy || applyingSuggestion) {
      return;
    }

    setApplyingSuggestion(true);
    setApplySuggestionInfo(null);
    setApplySuggestionError(null);

    const result = await updateGenerationPolicy(suggestedPolicy);

    setApplyingSuggestion(false);
    if (!result.ok || !result.data) {
      setApplySuggestionError(result.error || "Apply suggestion failed");
      return;
    }

    setPolicyOverride(result.data);
    setPreviewSuggestion(false);
    setApplySuggestionInfo("建议参数已应用到 /settings/generation，正在刷新最新 Intent Trace...");
    startRefreshTrace(() => {
      router.refresh();
    });
  };

  const sceneTheme =
    asString(sceneGeneration.scene_theme) ||
    asString(getPath(worldState, ["theme_filter", "theme"]));

  const fragmentSourceRows: string[] = [];
  const fragmentSources = asArray(worldState?.fragment_source);

  for (const item of fragmentSources) {
    if (typeof item === "string") {
      fragmentSourceRows.push(item);
      continue;
    }

    const row = asObject(item);
    if (!row) {
      continue;
    }

    const fragment = asString(row.fragment) || asString(row.fragment_id) || asString(row.id);
    const pack = asString(row.pack) || asString(row.pack_id) || asString(row.source_pack) || asString(row.source);
    const reason = asString(row.reason);
    const score = asNumber(row.score);

    const segments = [
      fragment ? `fragment=${fragment}` : "",
      pack ? `pack=${pack}` : "",
      reason ? `reason=${reason}` : "",
      score !== null ? `score=${score}` : "",
    ].filter(Boolean);

    if (segments.length > 0) {
      fragmentSourceRows.push(segments.join(" · "));
    }
  }

  const worldPatch =
    asObject(getPath(sceneGeneration, ["last_rule_event_result", "world_patch"])) ??
    asObject(getPath(debugTasks, ["last_rule_event", "raw_payload", "world_patch"])) ??
    asObject(getPath(debugTasks, ["result", "world_patch"])) ??
    asObject(getPath(debugTasks, ["world_patch"])) ??
    asObject(getPath(worldState, ["world_patch"])) ??
    null;

  const explicitCommands = Array.from(
    new Set([
      ...normalizeCommandList(getPath(debugTasks, ["last_rule_event", "raw_payload", "commands"])),
      ...normalizeCommandList(getPath(debugTasks, ["commands"])),
      ...normalizeCommandList(getPath(debugTasks, ["last_rule_event", "commands"])),
      ...normalizeCommandList(getPath(debugTasks, ["scene_diff", "commands"])),
    ]),
  );

  const equivalentCommands = deriveEquivalentCommands(worldPatch, explicitCommands);

  const patchPlan = worldPatch ?? asObject(getPath(debugTasks, ["scene_diff"])) ?? null;

  return (
    <div className="flex flex-col gap-4">
      {!ok && (
        <article className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm">
          <h2 className="font-semibold">Intent Trace 请求失败</h2>
          <p className="mt-2">{error || "request failed"}</p>
        </article>
      )}

      {debugTasksError && (
        <article className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm">
          <h2 className="font-semibold">Debug 增强数据不可用（已降级）</h2>
          <p className="mt-2">{debugTasksError}</p>
        </article>
      )}

      <article className="rounded-xl border border-black/10 p-4 text-sm dark:border-white/20">
        <h2 className="text-base font-semibold">Pipeline</h2>
        <p className="mt-2 opacity-80">
          Player Input → Intent Engine → Semantic Match → Narrative Node → Scene Fragment → World Patch
        </p>
      </article>

      <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">1) Player Input</h2>
        <p className="mt-2 text-sm">{primaryInput.text || "(暂无可见输入；可先在游戏中触发一次 talk/chat 事件)"}</p>
        <p className="mt-1 text-xs opacity-70">source: {primaryInput.source}</p>
      </article>

      <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">2) Intent Result</h2>
        <div className="mt-3 grid grid-cols-1 gap-3 text-sm md:grid-cols-3">
          <div className="rounded-lg border border-black/10 p-3 dark:border-white/20">
            <div className="text-xs opacity-70">intent_type</div>
            <div className="mt-1 font-semibold">{intentType || "UNKNOWN"}</div>
          </div>
          <div className="rounded-lg border border-black/10 p-3 dark:border-white/20">
            <div className="text-xs opacity-70">confidence</div>
            <div className="mt-1 font-semibold">{confidence === null ? "(unknown)" : confidence}</div>
          </div>
          <div className="rounded-lg border border-black/10 p-3 dark:border-white/20">
            <div className="text-xs opacity-70">player_id</div>
            <div className="mt-1 font-semibold">{playerId}</div>
          </div>
        </div>

        <details className="mt-3 rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
          <summary className="cursor-pointer font-medium">intent_params</summary>
          <pre className="mt-2 overflow-auto">{toPrettyJson(intentParams)}</pre>
        </details>
      </article>

      <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">3) Semantic Match</h2>
        <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <div className="rounded-lg border border-black/10 p-3 text-sm dark:border-white/20">
            <div className="text-xs font-semibold opacity-80">matched tags</div>
            {matchedTags.length === 0 ? (
              <p className="mt-2 text-xs opacity-70">(none)</p>
            ) : (
              <ul className="mt-2 space-y-1 text-xs">
                {semanticScoreRows.map((row) => (
                  <li key={row.tag}>
                    {row.tag} · score={row.score}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-lg border border-black/10 p-3 text-sm dark:border-white/20">
            <div className="text-xs font-semibold opacity-80">resource mapping</div>
            {resourceMappings.length === 0 ? (
              <p className="mt-2 text-xs opacity-70">(none)</p>
            ) : (
              <pre className="mt-2 max-h-48 overflow-auto text-xs">{resourceMappings.join("\n")}</pre>
            )}
          </div>
        </div>
      </article>

      <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">4) Narrative Resolution</h2>
        <div className="mt-2 text-sm">current_node: {currentNode || "(empty)"}</div>
        <div className="mt-1 text-sm">blocked_by: {blockedBy.length ? blockedBy.join(", ") : "(none)"}</div>

        <details className="mt-3 rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
          <summary className="cursor-pointer font-medium">
            transition_candidates ({transitionCandidates.length})
          </summary>
          <pre className="mt-2 overflow-auto">{toPrettyJson(transitionCandidates)}</pre>
        </details>
      </article>

      <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">5) Scene Selection</h2>
        <div className="mt-3 grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
          <div className="rounded-lg border border-black/10 p-3 dark:border-white/20">
            <div className="text-xs opacity-70">selected fragment</div>
            <div className="mt-1 font-semibold">{selectedFragment || "(unknown)"}</div>
          </div>
          <div className="rounded-lg border border-black/10 p-3 dark:border-white/20">
            <div className="text-xs opacity-70">theme</div>
            <div className="mt-1 font-semibold">{sceneTheme || "(unknown)"}</div>
          </div>
        </div>

        <div className="mt-3 rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
          <div className="font-semibold opacity-80">semantic tags</div>
          <p className="mt-1">{matchedTags.length ? matchedTags.join(", ") : "(none)"}</p>
        </div>

        <div className="mt-3 rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
          <div className="font-semibold opacity-80">pack source</div>
          {fragmentSourceRows.length === 0 ? (
            <p className="mt-1">(none)</p>
          ) : (
            <pre className="mt-1 max-h-40 overflow-auto">{fragmentSourceRows.join("\n")}</pre>
          )}
        </div>

        <div className="mt-3 rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
          <div className="font-semibold opacity-80">generation policy gate</div>
          <div className="mt-1">allowed: {generationAllowed === null ? "(unknown)" : generationAllowed ? "true" : "false"}</div>
          <div className="mt-1">reason: {generationReason || "(none)"}</div>
          <div className="mt-1">
            next_available_in: {generationNextAvailableIn === null ? "(none)" : `${generationNextAvailableIn}s`}
          </div>
          <div className="mt-2 rounded-md border border-black/10 p-2 dark:border-white/20">
            <div>scenes_generated_last_hour: {scenesGeneratedLastHour === null ? "(none)" : scenesGeneratedLastHour}</div>
            <div>scenes_blocked_by_policy: {scenesBlockedByPolicy === null ? "(none)" : scenesBlockedByPolicy}</div>
            <div>policy_block_rate: {policyBlockRate === null ? "(none)" : policyBlockRate}</div>
            <div>avg_scene_interval: {avgSceneInterval === null ? "(none)" : `${avgSceneInterval}s`}</div>
            <div>policy_cooldown_hits: {policyCooldownHits === null ? "(none)" : policyCooldownHits}</div>
          </div>
          <details className="mt-2 rounded-lg border border-black/10 p-2 dark:border-white/20">
            <summary className="cursor-pointer">policy snapshot</summary>
            <pre className="mt-2 overflow-auto">{toPrettyJson(generationPolicySnapshot)}</pre>
          </details>
        </div>

        <div className="mt-3 rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
          <div className="font-semibold opacity-80">runtime health</div>
          <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-3">
            <div className="rounded-md border border-black/10 p-2 dark:border-white/20">
              <div className="opacity-70">Scene Rate</div>
              <div className="mt-1 font-semibold">{sceneRateStatus}</div>
              <div className="mt-1 opacity-75">{asString(sceneRateHealth.note) || "(none)"}</div>
            </div>
            <div className="rounded-md border border-black/10 p-2 dark:border-white/20">
              <div className="opacity-70">Policy Pressure</div>
              <div className="mt-1 font-semibold">{policyPressureStatus}</div>
              <div className="mt-1 opacity-75">{asString(policyPressureHealth.note) || "(none)"}</div>
            </div>
            <div className="rounded-md border border-black/10 p-2 dark:border-white/20">
              <div className="opacity-70">Cooldown Stress</div>
              <div className="mt-1 font-semibold">{cooldownStressStatus}</div>
              <div className="mt-1 opacity-75">{asString(cooldownStressHealth.note) || "(none)"}</div>
            </div>
          </div>
        </div>

        <div className="mt-3 rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
          <div className="font-semibold opacity-80">pacing recommendation</div>
          <div className="mt-2">status: {recommendationStatus}</div>
          <div className="mt-1">severity: {recommendationSeverity}</div>
          <div className="mt-1">code: {recommendationCode}</div>
          <div className="mt-1">message: {recommendationMessage || "(none)"}</div>
          <div className="mt-1">
            suggested scene_cooldown:{" "}
            {currentCooldown !== null && suggestedCooldown !== null
              ? `${currentCooldown}s → ${suggestedCooldown}s`
              : "(none)"}
          </div>

          {applySuggestionError && (
            <div className="mt-2 rounded-md border border-red-500/30 bg-red-500/10 p-2 text-red-600 dark:text-red-300">
              {applySuggestionError}
            </div>
          )}
          {applySuggestionInfo && (
            <div className="mt-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-2 text-emerald-700 dark:text-emerald-300">
              {applySuggestionInfo}
            </div>
          )}
          {isRefreshingTrace && (
            <div className="mt-2 rounded-md border border-black/10 bg-black/5 p-2 text-black/80 dark:border-white/20 dark:bg-white/10 dark:text-white/80">
              refreshing intent trace...
            </div>
          )}

          {suggestedPolicy ? (
            <div className="mt-2 rounded-md border border-black/10 p-2 dark:border-white/20">
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => setPreviewSuggestion((value) => !value)}
                  className="inline-flex items-center justify-center rounded-md border border-black/10 px-2 py-1 text-xs hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
                >
                  {previewSuggestion ? "Hide Preview" : "Preview Suggestion"}
                </button>
              </div>

              {previewSuggestion && (
                <div className="mt-2 space-y-2">
                  <div>preview: manual apply only (no auto tuning)</div>
                  <div>
                    scene_cooldown change:{" "}
                    {currentCooldown !== null && suggestedPolicy.scene_cooldown !== undefined
                      ? `${currentCooldown}s → ${suggestedPolicy.scene_cooldown}s`
                      : "(none)"}
                  </div>
                  <details className="rounded-lg border border-black/10 p-2 dark:border-white/20">
                    <summary className="cursor-pointer">suggested policy payload</summary>
                    <pre className="mt-2 overflow-auto">{toPrettyJson(suggestedPolicy)}</pre>
                  </details>
                  <button
                    type="button"
                    onClick={applySuggestion}
                    disabled={applyingSuggestion || isRefreshingTrace}
                    className="inline-flex items-center justify-center rounded-md border border-black/10 px-2 py-1 text-xs hover:bg-black/5 disabled:opacity-60 dark:border-white/20 dark:hover:bg-white/10"
                  >
                    {applyingSuggestion ? "Applying..." : isRefreshingTrace ? "Refreshing..." : "Apply Suggestion"}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="mt-2 opacity-70">(no actionable policy patch)</div>
          )}
        </div>

        <div className="mt-3 rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
          <div className="font-semibold opacity-80">scene timeline</div>
          {sceneTimeline.length === 0 ? (
            <p className="mt-2 opacity-70">(none)</p>
          ) : (
            <ul className="mt-2 space-y-1">
              {sceneTimeline.map((row, index) => (
                <li key={`${row.atMs}-${index}`}>
                  <span className="font-medium">{formatTimeMs(row.atMs)}</span>
                  {" · "}
                  {row.generated ? "scene generated" : "scene blocked"}
                  {" · reason="}
                  {row.reason}
                  {row.intervalSincePrevGeneratedS === null ? "" : ` · interval=${row.intervalSincePrevGeneratedS}s`}
                  {!row.generated && row.nextAvailableIn !== null ? ` · next=${row.nextAvailableIn}s` : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      </article>

      <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">6) World Patch</h2>
        <div className="mt-2 text-xs opacity-75">patch plan</div>
        <pre className="mt-2 max-h-56 overflow-auto rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
          {patchPlan ? toPrettyJson(patchPlan) : "(当前接口未暴露可执行 world_patch)"}
        </pre>

        <div className="mt-4 text-xs opacity-75">Equivalent Commands</div>
        <pre className="mt-2 max-h-56 overflow-auto rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
          {equivalentCommands.length
            ? equivalentCommands.join("\n")
            : "(未提取到可执行命令；可先触发一次生成/事件后再观察)"}
        </pre>
      </article>

      <details className="rounded-xl border border-black/10 p-4 text-xs dark:border-white/20">
        <summary className="cursor-pointer font-semibold">Raw Intent Trace Payload</summary>
        <pre className="mt-3 max-h-[50vh] overflow-auto">{toPrettyJson(payload)}</pre>
      </details>
    </div>
  );
}