"use client";

import { useMemo, useState } from "react";

import {
  generatePoetryScene,
  listPlayerTags,
  upsertPlayerTag,
  type PoetryGeneratePayload,
} from "@/lib/drift-backend";

function asObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export default function PoetryClient() {
  const [playerId, setPlayerId] = useState("vivn");
  const [poem, setPoem] = useState("月光沿着风声落下，\n雾在水边缠住旧船。\n我在火旁读一页未完成的梦。");
  const [metaphorTag, setMetaphorTag] = useState("moon");
  const [metaphorResource, setMetaphorResource] = useState("minecraft:lantern");
  const [sceneTheme, setSceneTheme] = useState("");
  const [sceneHint, setSceneHint] = useState("");
  const [maxResources, setMaxResources] = useState(12);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [payload, setPayload] = useState<PoetryGeneratePayload | null>(null);
  const [savingMetaphor, setSavingMetaphor] = useState(false);
  const [loadingMetaphors, setLoadingMetaphors] = useState(false);
  const [playerMetaphors, setPlayerMetaphors] = useState<Record<string, string[]>>({});

  const loadMetaphors = async () => {
    const normalizedPlayer = String(playerId || "").trim();
    if (!normalizedPlayer) {
      setError("player_id 不能为空");
      return;
    }

    setLoadingMetaphors(true);
    setError(null);
    setInfo(null);

    const result = await listPlayerTags(normalizedPlayer);
    setLoadingMetaphors(false);

    if (!result.ok) {
      setError(result.error || "读取隐喻备案失败");
      return;
    }

    setPlayerMetaphors(result.tags || {});
    setInfo("已读取玩家隐喻备案");
  };

  const onRegisterMetaphor = async () => {
    const normalizedPlayer = String(playerId || "").trim();
    const normalizedTag = String(metaphorTag || "").trim().toLowerCase();
    const normalizedResource = String(metaphorResource || "").trim().toLowerCase();

    if (!normalizedPlayer || !normalizedTag || !normalizedResource) {
      setError("player_id / metaphor_tag / resource_id 均不能为空");
      return;
    }

    setSavingMetaphor(true);
    setError(null);
    setInfo(null);

    const result = await upsertPlayerTag({
      player: normalizedPlayer,
      tag: normalizedTag,
      resource: normalizedResource,
      source: "poetry_metaphor",
    });

    setSavingMetaphor(false);

    if (!result.ok) {
      setError(result.error || "隐喻备案失败");
      return;
    }

    setInfo("隐喻备案成功");
    await loadMetaphors();
  };

  const onGenerate = async () => {
    const normalizedPlayer = String(playerId || "").trim();
    const normalizedPoem = String(poem || "").trim();

    if (!normalizedPlayer || !normalizedPoem) {
      setError("player_id 与 poem 不能为空");
      return;
    }

    setLoading(true);
    setError(null);
    setInfo(null);

    const result = await generatePoetryScene({
      player_id: normalizedPlayer,
      poem: normalizedPoem,
      scene_theme: String(sceneTheme || "").trim() || undefined,
      scene_hint: String(sceneHint || "").trim() || undefined,
      max_resources: Math.max(1, Math.min(48, Math.floor(Number(maxResources) || 12))),
    });

    setLoading(false);

    if (!result.ok || !result.data) {
      setPayload(result.data);
      setError(result.error || "生成失败");
      return;
    }

    setPayload(result.data);
    setInfo("Poetry scene 生成完成");
  };

  const summary = useMemo(() => {
    const row = asObject(payload);
    return {
      sceneTheme: typeof row?.scene_theme === "string" ? row.scene_theme : "(unknown)",
      selectedRoot: typeof row?.selected_root === "string" ? row.selected_root : "(none)",
      fragmentCount: Number(row?.fragment_count || 0),
      eventCount: Number(row?.event_count || 0),
      concepts: asArray(row?.concepts),
      resourceWeights: asObject(row?.resource_weights) ?? {},
      selectedFragments: asArray(row?.selected_fragments),
      worldPatch: asObject(row?.world_patch),
      playerTagMatches: asArray(row?.player_tag_matches),
    };
  }, [payload]);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.2fr_1.8fr]">
      <section className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">Step 1 · 隐喻备案</h2>

        {error && (
          <article className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm">
            {error}
          </article>
        )}

        {info && (
          <article className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
            {info}
          </article>
        )}

        <div className="mt-3 space-y-3 text-sm">
          <div>
            <label className="mb-1 block font-medium" htmlFor="player-id">player_id</label>
            <input
              id="player-id"
              value={playerId}
              onChange={(event) => setPlayerId(event.target.value)}
              className="w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 dark:border-white/20"
            />
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1 block font-medium" htmlFor="metaphor-tag">metaphor_tag</label>
              <input
                id="metaphor-tag"
                value={metaphorTag}
                onChange={(event) => setMetaphorTag(event.target.value)}
                className="w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 dark:border-white/20"
              />
            </div>

            <div>
              <label className="mb-1 block font-medium" htmlFor="metaphor-resource">resource_id</label>
              <input
                id="metaphor-resource"
                value={metaphorResource}
                onChange={(event) => setMetaphorResource(event.target.value)}
                className="w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 dark:border-white/20"
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onRegisterMetaphor}
              disabled={savingMetaphor}
              className="rounded-lg border border-black/10 px-3 py-2 hover:bg-black/5 disabled:opacity-60 dark:border-white/20 dark:hover:bg-white/10"
            >
              {savingMetaphor ? "备案中..." : "保存隐喻备案"}
            </button>
            <button
              type="button"
              onClick={loadMetaphors}
              disabled={loadingMetaphors}
              className="rounded-lg border border-black/10 px-3 py-2 hover:bg-black/5 disabled:opacity-60 dark:border-white/20 dark:hover:bg-white/10"
            >
              {loadingMetaphors ? "读取中..." : "读取玩家备案"}
            </button>
          </div>

          <pre className="max-h-36 overflow-auto rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
            {JSON.stringify(playerMetaphors, null, 2)}
          </pre>
        </div>

        <h2 className="mt-6 text-base font-semibold">Step 2 · 诗歌输入</h2>

        <div className="mt-3 space-y-3 text-sm">

          <div>
            <label className="mb-1 block font-medium" htmlFor="poem">poem</label>
            <textarea
              id="poem"
              value={poem}
              onChange={(event) => setPoem(event.target.value)}
              rows={7}
              className="w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 dark:border-white/20"
            />
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1 block font-medium" htmlFor="scene-theme">scene_theme (optional)</label>
              <input
                id="scene-theme"
                value={sceneTheme}
                onChange={(event) => setSceneTheme(event.target.value)}
                className="w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 dark:border-white/20"
              />
            </div>

            <div>
              <label className="mb-1 block font-medium" htmlFor="scene-hint">scene_hint (optional)</label>
              <input
                id="scene-hint"
                value={sceneHint}
                onChange={(event) => setSceneHint(event.target.value)}
                className="w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 dark:border-white/20"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block font-medium" htmlFor="max-resources">max_resources</label>
            <input
              id="max-resources"
              type="number"
              min={1}
              max={48}
              value={maxResources}
              onChange={(event) => setMaxResources(Number(event.target.value) || 12)}
              className="w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 dark:border-white/20"
            />
          </div>

          <h2 className="mt-2 text-base font-semibold">Step 3 · 场景生成</h2>

          <button
            type="button"
            onClick={onGenerate}
            disabled={loading}
            className="rounded-lg border border-black/10 px-3 py-2 hover:bg-black/5 disabled:opacity-60 dark:border-white/20 dark:hover:bg-white/10"
          >
            {loading ? "生成中..." : "Generate Poetry Scene"}
          </button>
        </div>
      </section>

      <section className="space-y-4">
        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="text-base font-semibold">Summary</h2>
          <div className="mt-2 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
            <div>
              <div className="opacity-70">scene_theme</div>
              <div className="font-medium">{summary.sceneTheme}</div>
            </div>
            <div>
              <div className="opacity-70">selected_root</div>
              <div className="font-medium">{summary.selectedRoot}</div>
            </div>
            <div>
              <div className="opacity-70">fragments</div>
              <div className="font-medium">{summary.fragmentCount}</div>
            </div>
            <div>
              <div className="opacity-70">events</div>
              <div className="font-medium">{summary.eventCount}</div>
            </div>
          </div>
        </article>

        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="text-base font-semibold">Concepts</h2>
          <pre className="mt-2 max-h-52 overflow-auto rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
            {JSON.stringify(summary.concepts, null, 2)}
          </pre>
        </article>

        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="text-base font-semibold">Resource Weights</h2>
          <pre className="mt-2 max-h-52 overflow-auto rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
            {JSON.stringify(summary.resourceWeights, null, 2)}
          </pre>
        </article>

        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="text-base font-semibold">Selected Fragments</h2>
          <pre className="mt-2 max-h-52 overflow-auto rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
            {JSON.stringify(summary.selectedFragments, null, 2)}
          </pre>
        </article>

        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="text-base font-semibold">Metaphor Matches</h2>
          <pre className="mt-2 max-h-52 overflow-auto rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
            {JSON.stringify(summary.playerTagMatches, null, 2)}
          </pre>
        </article>

        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="text-base font-semibold">World Patch</h2>
          <pre className="mt-2 max-h-64 overflow-auto rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
            {JSON.stringify(summary.worldPatch, null, 2)}
          </pre>
        </article>

        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="text-base font-semibold">Raw Payload</h2>
          <pre className="mt-2 max-h-72 overflow-auto rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
            {JSON.stringify(payload, null, 2)}
          </pre>
        </article>
      </section>
    </div>
  );
}
