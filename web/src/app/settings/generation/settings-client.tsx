"use client";

import { useState, type FormEvent } from "react";

import {
  fetchGenerationPolicy,
  updateGenerationPolicy,
  type GenerationPolicyPayload,
} from "@/lib/drift-backend";

type SettingsClientProps = {
  initialPolicy: GenerationPolicyPayload | null;
  initialOk: boolean;
  initialError: string | null;
  baseUrl: string;
};

type FormState = {
  scene_cooldown: string;
  spawn_probability: string;
  max_scenes_per_hour: string;
  spawn_distance: string;
  require_player_movement: boolean;
  require_new_location: boolean;
};

type FormErrors = Partial<Record<keyof FormState, string>>;

function toFormState(policy: GenerationPolicyPayload): FormState {
  return {
    scene_cooldown: String(policy.scene_cooldown),
    spawn_probability: String(policy.spawn_probability),
    max_scenes_per_hour: String(policy.max_scenes_per_hour),
    spawn_distance: String(policy.spawn_distance),
    require_player_movement: Boolean(policy.require_player_movement),
    require_new_location: Boolean(policy.require_new_location),
  };
}

function validateForm(form: FormState): {
  payload: GenerationPolicyPayload | null;
  errors: FormErrors;
} {
  const errors: FormErrors = {};

  const sceneCooldown = Number(form.scene_cooldown);
  const spawnProbability = Number(form.spawn_probability);
  const maxScenesPerHour = Number(form.max_scenes_per_hour);
  const spawnDistance = Number(form.spawn_distance);

  if (!Number.isFinite(sceneCooldown) || sceneCooldown < 0) {
    errors.scene_cooldown = "scene_cooldown 必须是 ≥ 0 的数字";
  }

  if (!Number.isFinite(spawnProbability) || spawnProbability < 0 || spawnProbability > 1) {
    errors.spawn_probability = "spawn_probability 必须在 0 到 1 之间";
  }

  if (!Number.isFinite(maxScenesPerHour) || maxScenesPerHour < 1 || !Number.isInteger(maxScenesPerHour)) {
    errors.max_scenes_per_hour = "max_scenes_per_hour 必须是 ≥ 1 的整数";
  }

  if (!Number.isFinite(spawnDistance) || spawnDistance < 0) {
    errors.spawn_distance = "spawn_distance 必须是 ≥ 0 的数字";
  }

  if (Object.keys(errors).length > 0) {
    return {
      payload: null,
      errors,
    };
  }

  return {
    payload: {
      scene_cooldown: sceneCooldown,
      spawn_probability: spawnProbability,
      max_scenes_per_hour: maxScenesPerHour,
      spawn_distance: spawnDistance,
      require_player_movement: form.require_player_movement,
      require_new_location: form.require_new_location,
    },
    errors: {},
  };
}

export default function GenerationSettingsClient({
  initialPolicy,
  initialOk,
  initialError,
  baseUrl,
}: SettingsClientProps) {
  const [currentPolicy, setCurrentPolicy] = useState<GenerationPolicyPayload | null>(initialPolicy);
  const [form, setForm] = useState<FormState | null>(initialPolicy ? toFormState(initialPolicy) : null);
  const [errors, setErrors] = useState<FormErrors>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const loadPolicy = async () => {
    setLoading(true);
    setSubmitError(null);
    setInfo(null);

    const result = await fetchGenerationPolicy(baseUrl);
    setLoading(false);

    if (!result.ok || !result.data) {
      setSubmitError(result.error || "加载策略失败");
      return;
    }

    setCurrentPolicy(result.data);
    setForm(toFormState(result.data));
    setErrors({});
    setInfo("已从后端重新加载策略。");
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form) {
      return;
    }

    const validated = validateForm(form);
    setErrors(validated.errors);
    setSubmitError(null);
    setInfo(null);

    if (!validated.payload) {
      return;
    }

    setSaving(true);
    const result = await updateGenerationPolicy(validated.payload, baseUrl);
    setSaving(false);

    if (!result.ok || !result.data) {
      setSubmitError(result.error || "更新策略失败");
      return;
    }

    setCurrentPolicy(result.data);
    setForm(toFormState(result.data));
    setErrors({});
    setInfo("策略已更新并保存到后端。");
  };

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
      <section className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        {!initialOk && (
          <article className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm">
            <h2 className="font-semibold">初始加载失败</h2>
            <p className="mt-2">{initialError || "request failed"}</p>
          </article>
        )}

        {submitError && (
          <article className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm">
            <h2 className="font-semibold">操作失败</h2>
            <p className="mt-2">{submitError}</p>
          </article>
        )}

        {info && (
          <article className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm">
            <p>{info}</p>
          </article>
        )}

        {!form ? (
          <div className="rounded-lg border border-black/10 p-4 text-sm dark:border-white/20">
            <p>当前没有可编辑策略，先从后端拉取最新策略。</p>
            <button
              type="button"
              onClick={loadPolicy}
              disabled={loading}
              className="mt-3 inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 disabled:opacity-60 dark:border-white/20 dark:hover:bg-white/10"
            >
              {loading ? "加载中..." : "加载当前策略"}
            </button>
          </div>
        ) : (
          <form className="space-y-4" onSubmit={onSubmit}>
            <article className="rounded-lg border border-black/10 p-4 dark:border-white/20">
              <label className="text-sm font-semibold" htmlFor="scene_cooldown">
                Scene Cooldown (seconds)
              </label>
              <input
                id="scene_cooldown"
                type="number"
                min={0}
                step="1"
                value={form.scene_cooldown}
                onChange={(event) => setForm({ ...form, scene_cooldown: event.target.value })}
                className="mt-2 w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 text-sm dark:border-white/20"
              />
              {errors.scene_cooldown && <p className="mt-1 text-xs text-red-500">{errors.scene_cooldown}</p>}
            </article>

            <article className="rounded-lg border border-black/10 p-4 dark:border-white/20">
              <label className="text-sm font-semibold" htmlFor="spawn_probability_range">
                Spawn Probability (0–1 slider)
              </label>
              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-[1fr_120px] sm:items-center">
                <input
                  id="spawn_probability_range"
                  type="range"
                  min={0}
                  max={1}
                  step="0.01"
                  value={form.spawn_probability}
                  onChange={(event) => setForm({ ...form, spawn_probability: event.target.value })}
                />
                <input
                  id="spawn_probability"
                  type="number"
                  min={0}
                  max={1}
                  step="0.01"
                  value={form.spawn_probability}
                  onChange={(event) => setForm({ ...form, spawn_probability: event.target.value })}
                  className="w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 text-sm dark:border-white/20"
                />
              </div>
              {errors.spawn_probability && <p className="mt-1 text-xs text-red-500">{errors.spawn_probability}</p>}
            </article>

            <article className="rounded-lg border border-black/10 p-4 dark:border-white/20">
              <label className="text-sm font-semibold" htmlFor="max_scenes_per_hour">
                Max Scenes Per Hour
              </label>
              <input
                id="max_scenes_per_hour"
                type="number"
                min={1}
                step="1"
                value={form.max_scenes_per_hour}
                onChange={(event) => setForm({ ...form, max_scenes_per_hour: event.target.value })}
                className="mt-2 w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 text-sm dark:border-white/20"
              />
              {errors.max_scenes_per_hour && <p className="mt-1 text-xs text-red-500">{errors.max_scenes_per_hour}</p>}
            </article>

            <article className="rounded-lg border border-black/10 p-4 dark:border-white/20">
              <label className="text-sm font-semibold" htmlFor="spawn_distance">
                Spawn Distance (blocks)
              </label>
              <input
                id="spawn_distance"
                type="number"
                min={0}
                step="1"
                value={form.spawn_distance}
                onChange={(event) => setForm({ ...form, spawn_distance: event.target.value })}
                className="mt-2 w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 text-sm dark:border-white/20"
              />
              {errors.spawn_distance && <p className="mt-1 text-xs text-red-500">{errors.spawn_distance}</p>}
            </article>

            <article className="rounded-lg border border-black/10 p-4 dark:border-white/20">
              <div className="flex items-center justify-between gap-3">
                <label className="text-sm font-semibold" htmlFor="require_player_movement">
                  Require Player Movement (toggle)
                </label>
                <input
                  id="require_player_movement"
                  type="checkbox"
                  checked={form.require_player_movement}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      require_player_movement: event.target.checked,
                    })
                  }
                  className="h-4 w-4"
                />
              </div>
            </article>

            <article className="rounded-lg border border-black/10 p-4 dark:border-white/20">
              <div className="flex items-center justify-between gap-3">
                <label className="text-sm font-semibold" htmlFor="require_new_location">
                  Require New Location (toggle)
                </label>
                <input
                  id="require_new_location"
                  type="checkbox"
                  checked={form.require_new_location}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      require_new_location: event.target.checked,
                    })
                  }
                  className="h-4 w-4"
                />
              </div>
            </article>

            <div className="flex flex-wrap gap-3">
              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 disabled:opacity-60 dark:border-white/20 dark:hover:bg-white/10"
              >
                {saving ? "保存中..." : "保存策略"}
              </button>
              <button
                type="button"
                onClick={loadPolicy}
                disabled={loading}
                className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 disabled:opacity-60 dark:border-white/20 dark:hover:bg-white/10"
              >
                {loading ? "加载中..." : "重新拉取后端策略"}
              </button>
            </div>
          </form>
        )}
      </section>

      <aside className="h-fit rounded-xl border border-black/10 p-4 text-sm dark:border-white/20">
        <h2 className="text-base font-semibold">Current Policy</h2>
        {!currentPolicy ? (
          <p className="mt-2 opacity-80">(未加载)</p>
        ) : (
          <pre className="mt-2 max-h-[60vh] overflow-auto rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
            {JSON.stringify(currentPolicy, null, 2)}
          </pre>
        )}
      </aside>
    </div>
  );
}
