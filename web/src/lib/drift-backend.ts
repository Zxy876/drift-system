export const DEFAULT_DRIFT_BACKEND_URL = "http://127.0.0.1:8000";

function toAbsoluteBaseUrl(value: unknown): string | null {
  const raw = String(value || "").trim();
  if (!raw) {
    return null;
  }

  const withProtocol = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  return withProtocol.replace(/\/+$/, "");
}

const BASE_URL =
  toAbsoluteBaseUrl(process.env.NEXT_PUBLIC_DRIFT_BACKEND_URL) ??
  DEFAULT_DRIFT_BACKEND_URL;

export function getDriftBackendBaseUrl(): string {
  return BASE_URL;
}

export type WorldStatePayload = Record<string, unknown>;
export type NarrativeGraphPayload = Record<string, unknown>;
export type ScenesLibraryPayload = Record<string, unknown>;
export type GenerationPolicyPayload = {
  scene_cooldown: number;
  spawn_probability: number;
  max_scenes_per_hour: number;
  spawn_distance: number;
  require_player_movement: boolean;
  require_new_location: boolean;
};
export type IntentTracePayload = {
  world_state: WorldStatePayload | null;
  debug_tasks: Record<string, unknown> | null;
  debug_tasks_status: number | null;
  debug_tasks_error: string | null;
};

export type RegistryResourceItem = {
  resource_id: string;
  resource_type: string;
  namespace: string;
  source: string;
  semantic_tags: string[];
  label?: string | null;
};

export type PlayerTagItem = {
  id: number;
  player_id: string;
  tag: string;
  resource_id: string;
  resource_type: string;
  namespace: string;
  source: string | null;
  created_at: number;
  updated_at: number;
};

function normalizeBaseUrl(baseUrlOverride?: string): string {
  const override = toAbsoluteBaseUrl(baseUrlOverride);
  if (override) {
    return override;
  }
  return getDriftBackendBaseUrl();
}

function asGenerationPolicy(value: unknown): GenerationPolicyPayload | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const row = value as Record<string, unknown>;

  const sceneCooldown = Number(row.scene_cooldown);
  const spawnProbability = Number(row.spawn_probability);
  const maxScenesPerHour = Number(row.max_scenes_per_hour);
  const spawnDistance = Number(row.spawn_distance);

  if (!Number.isFinite(sceneCooldown)) {
    return null;
  }
  if (!Number.isFinite(spawnProbability)) {
    return null;
  }
  if (!Number.isFinite(maxScenesPerHour)) {
    return null;
  }
  if (!Number.isFinite(spawnDistance)) {
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

export async function fetchWorldState(playerId: string): Promise<{
  ok: boolean;
  status: number;
  baseUrl: string;
  data: WorldStatePayload | null;
  error: string | null;
}> {
  const normalizedPlayerId = String(playerId || "").trim();
  const baseUrl = getDriftBackendBaseUrl();

  if (!normalizedPlayerId) {
    return {
      ok: false,
      status: 400,
      baseUrl,
      data: null,
      error: "playerId is required",
    };
  }

  const requestUrl = `${baseUrl}/world/state/${encodeURIComponent(normalizedPlayerId)}`;

  try {
    const response = await fetch(requestUrl, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });

    let payload: WorldStatePayload | null = null;
    try {
      payload = (await response.json()) as WorldStatePayload;
    } catch {
      payload = null;
    }

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        baseUrl,
        data: payload,
        error: `backend returned ${response.status}`,
      };
    }

    return {
      ok: true,
      status: response.status,
      baseUrl,
      data: payload,
      error: null,
    };
  } catch (error) {
    return {
      ok: false,
      status: 503,
      baseUrl,
      data: null,
      error: error instanceof Error ? error.message : "network error",
    };
  }
}

export async function fetchNarrativeGraph(): Promise<{
  ok: boolean;
  status: number;
  baseUrl: string;
  data: NarrativeGraphPayload | null;
  error: string | null;
}> {
  const baseUrl = getDriftBackendBaseUrl();
  const requestUrl = `${baseUrl}/narrative/graph`;

  try {
    const response = await fetch(requestUrl, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });

    let payload: NarrativeGraphPayload | null = null;
    try {
      payload = (await response.json()) as NarrativeGraphPayload;
    } catch {
      payload = null;
    }

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        baseUrl,
        data: payload,
        error: `backend returned ${response.status}`,
      };
    }

    return {
      ok: true,
      status: response.status,
      baseUrl,
      data: payload,
      error: null,
    };
  } catch (error) {
    return {
      ok: false,
      status: 503,
      baseUrl,
      data: null,
      error: error instanceof Error ? error.message : "network error",
    };
  }
}

export async function fetchScenesLibrary(): Promise<{
  ok: boolean;
  status: number;
  baseUrl: string;
  data: ScenesLibraryPayload | null;
  error: string | null;
}> {
  const baseUrl = getDriftBackendBaseUrl();
  const requestUrl = `${baseUrl}/scenes/library`;

  try {
    const response = await fetch(requestUrl, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });

    let payload: ScenesLibraryPayload | null = null;
    try {
      payload = (await response.json()) as ScenesLibraryPayload;
    } catch {
      payload = null;
    }

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        baseUrl,
        data: payload,
        error: `backend returned ${response.status}`,
      };
    }

    return {
      ok: true,
      status: response.status,
      baseUrl,
      data: payload,
      error: null,
    };
  } catch (error) {
    return {
      ok: false,
      status: 503,
      baseUrl,
      data: null,
      error: error instanceof Error ? error.message : "network error",
    };
  }
}

export async function fetchGenerationPolicy(baseUrlOverride?: string): Promise<{
  ok: boolean;
  status: number;
  baseUrl: string;
  data: GenerationPolicyPayload | null;
  error: string | null;
}> {
  const baseUrl = normalizeBaseUrl(baseUrlOverride);
  const requestUrl = `${baseUrl}/settings/generation`;

  try {
    const response = await fetch(requestUrl, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });

    let rawPayload: unknown = null;
    try {
      rawPayload = await response.json();
    } catch {
      rawPayload = null;
    }

    const payload = asGenerationPolicy(rawPayload);

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        baseUrl,
        data: payload,
        error: `backend returned ${response.status}`,
      };
    }

    if (!payload) {
      return {
        ok: false,
        status: 502,
        baseUrl,
        data: null,
        error: "invalid generation policy schema",
      };
    }

    return {
      ok: true,
      status: response.status,
      baseUrl,
      data: payload,
      error: null,
    };
  } catch (error) {
    return {
      ok: false,
      status: 503,
      baseUrl,
      data: null,
      error: error instanceof Error ? error.message : "network error",
    };
  }
}

export async function updateGenerationPolicy(
  policy: GenerationPolicyPayload,
  baseUrlOverride?: string,
): Promise<{
  ok: boolean;
  status: number;
  baseUrl: string;
  data: GenerationPolicyPayload | null;
  error: string | null;
}> {
  const baseUrl = normalizeBaseUrl(baseUrlOverride);
  const requestUrl = `${baseUrl}/settings/generation`;

  try {
    const response = await fetch(requestUrl, {
      method: "POST",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(policy),
    });

    let rawPayload: unknown = null;
    try {
      rawPayload = await response.json();
    } catch {
      rawPayload = null;
    }

    const payload = asGenerationPolicy(rawPayload);

    if (!response.ok) {
      const detail =
        rawPayload && typeof rawPayload === "object" && !Array.isArray(rawPayload) && typeof (rawPayload as Record<string, unknown>).detail === "string"
          ? String((rawPayload as Record<string, unknown>).detail)
          : `backend returned ${response.status}`;
      return {
        ok: false,
        status: response.status,
        baseUrl,
        data: payload,
        error: detail,
      };
    }

    if (!payload) {
      return {
        ok: false,
        status: 502,
        baseUrl,
        data: null,
        error: "invalid generation policy schema",
      };
    }

    return {
      ok: true,
      status: response.status,
      baseUrl,
      data: payload,
      error: null,
    };
  } catch (error) {
    return {
      ok: false,
      status: 503,
      baseUrl,
      data: null,
      error: error instanceof Error ? error.message : "network error",
    };
  }
}

export async function fetchIntentTrace(playerId: string): Promise<{
  ok: boolean;
  status: number;
  baseUrl: string;
  data: IntentTracePayload | null;
  error: string | null;
}> {
  const normalizedPlayerId = String(playerId || "").trim();
  const worldResult = await fetchWorldState(normalizedPlayerId);

  if (!normalizedPlayerId) {
    return {
      ok: false,
      status: 400,
      baseUrl: worldResult.baseUrl,
      data: null,
      error: "playerId is required",
    };
  }

  let debugPayload: Record<string, unknown> | null = null;
  let debugStatus: number | null = null;
  let debugError: string | null = null;

  const debugUrl = `${worldResult.baseUrl}/world/story/${encodeURIComponent(normalizedPlayerId)}/debug/tasks`;
  try {
    const debugResponse = await fetch(debugUrl, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });

    debugStatus = debugResponse.status;

    try {
      const parsed = (await debugResponse.json()) as Record<string, unknown>;
      debugPayload = parsed;
    } catch {
      debugPayload = null;
    }

    if (!debugResponse.ok) {
      const detail =
        typeof debugPayload?.detail === "string"
          ? debugPayload.detail
          : `backend returned ${debugResponse.status}`;
      debugError = detail;
    }
  } catch (error) {
    debugStatus = 503;
    debugError = error instanceof Error ? error.message : "network error";
  }

  const payload: IntentTracePayload = {
    world_state: worldResult.data,
    debug_tasks: debugPayload,
    debug_tasks_status: debugStatus,
    debug_tasks_error: debugError,
  };

  if (!worldResult.ok) {
    return {
      ok: false,
      status: worldResult.status,
      baseUrl: worldResult.baseUrl,
      data: payload,
      error: worldResult.error,
    };
  }

  return {
    ok: true,
    status: worldResult.status,
    baseUrl: worldResult.baseUrl,
    data: payload,
    error: null,
  };
}

function asRegistryResourceItem(value: unknown): RegistryResourceItem | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const row = value as Record<string, unknown>;
  const resourceId = String(row.resource_id || "").trim();
  if (!resourceId) {
    return null;
  }

  return {
    resource_id: resourceId,
    resource_type: String(row.resource_type || "item").trim() || "item",
    namespace: String(row.namespace || "minecraft").trim() || "minecraft",
    source: String(row.source || "registry").trim() || "registry",
    semantic_tags: Array.isArray(row.semantic_tags)
      ? row.semantic_tags.map((tag) => String(tag || "").trim()).filter(Boolean)
      : [],
    label: typeof row.label === "string" ? row.label : null,
  };
}

function asPlayerTagItem(value: unknown): PlayerTagItem | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const row = value as Record<string, unknown>;
  const id = Number(row.id);
  if (!Number.isFinite(id)) {
    return null;
  }

  const playerId = String(row.player_id || "").trim();
  const tag = String(row.tag || "").trim();
  const resourceId = String(row.resource_id || "").trim();
  if (!playerId || !tag || !resourceId) {
    return null;
  }

  return {
    id,
    player_id: playerId,
    tag,
    resource_id: resourceId,
    resource_type: String(row.resource_type || "item").trim() || "item",
    namespace: String(row.namespace || "minecraft").trim() || "minecraft",
    source: typeof row.source === "string" ? row.source : null,
    created_at: Number.isFinite(Number(row.created_at)) ? Number(row.created_at) : 0,
    updated_at: Number.isFinite(Number(row.updated_at)) ? Number(row.updated_at) : 0,
  };
}

export async function searchRegistryResources(
  query: string,
  options?: { limit?: number; source?: string; baseUrlOverride?: string },
): Promise<{
  ok: boolean;
  status: number;
  baseUrl: string;
  data: RegistryResourceItem[];
  error: string | null;
}> {
  const baseUrl = normalizeBaseUrl(options?.baseUrlOverride);
  const normalized = String(query || "").trim();

  if (!normalized) {
    return {
      ok: true,
      status: 200,
      baseUrl,
      data: [],
      error: null,
    };
  }

  const params = new URLSearchParams({ q: normalized });
  if (typeof options?.limit === "number" && Number.isFinite(options.limit)) {
    params.set("limit", String(Math.max(1, Math.min(100, Math.floor(options.limit)))));
  }
  if (options?.source) {
    params.set("source", String(options.source));
  }

  const requestUrl = `${baseUrl}/registry/resources/search?${params.toString()}`;
  try {
    const response = await fetch(requestUrl, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });

    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    const rawItems =
      payload && typeof payload === "object" && !Array.isArray(payload)
        ? (payload as Record<string, unknown>).items
        : null;
    const items = Array.isArray(rawItems)
      ? rawItems.map((row) => asRegistryResourceItem(row)).filter((row): row is RegistryResourceItem => row !== null)
      : [];

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        baseUrl,
        data: items,
        error: `backend returned ${response.status}`,
      };
    }

    return { ok: true, status: response.status, baseUrl, data: items, error: null };
  } catch (error) {
    return {
      ok: false,
      status: 503,
      baseUrl,
      data: [],
      error: error instanceof Error ? error.message : "network error",
    };
  }
}

export async function listPlayerTags(
  playerId: string,
  baseUrlOverride?: string,
): Promise<{
  ok: boolean;
  status: number;
  baseUrl: string;
  data: PlayerTagItem[];
  tags: Record<string, string[]>;
  error: string | null;
}> {
  const baseUrl = normalizeBaseUrl(baseUrlOverride);
  const normalizedPlayerId = String(playerId || "").trim();
  if (!normalizedPlayerId) {
    return {
      ok: false,
      status: 400,
      baseUrl,
      data: [],
      tags: {},
      error: "playerId is required",
    };
  }

  const requestUrl = `${baseUrl}/registry/player-tags/${encodeURIComponent(normalizedPlayerId)}`;
  try {
    const response = await fetch(requestUrl, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });

    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    const rawItems =
      payload && typeof payload === "object" && !Array.isArray(payload)
        ? (payload as Record<string, unknown>).items
        : null;
    const items = Array.isArray(rawItems)
      ? rawItems.map((row) => asPlayerTagItem(row)).filter((row): row is PlayerTagItem => row !== null)
      : [];

    const rawTags =
      payload && typeof payload === "object" && !Array.isArray(payload)
        ? (payload as Record<string, unknown>).tags
        : null;
    const tags: Record<string, string[]> = {};
    if (rawTags && typeof rawTags === "object" && !Array.isArray(rawTags)) {
      for (const [key, value] of Object.entries(rawTags as Record<string, unknown>)) {
        const token = String(key || "").trim();
        if (!token) {
          continue;
        }
        tags[token] = Array.isArray(value) ? value.map((row) => String(row || "").trim()).filter(Boolean) : [];
      }
    }

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        baseUrl,
        data: items,
        tags,
        error: `backend returned ${response.status}`,
      };
    }

    return { ok: true, status: response.status, baseUrl, data: items, tags, error: null };
  } catch (error) {
    return {
      ok: false,
      status: 503,
      baseUrl,
      data: [],
      tags: {},
      error: error instanceof Error ? error.message : "network error",
    };
  }
}

export async function upsertPlayerTag(
  payload: {
    player: string;
    tag: string;
    resource: string;
    resource_type?: string;
    namespace?: string;
    source?: string;
  },
  baseUrlOverride?: string,
): Promise<{
  ok: boolean;
  status: number;
  baseUrl: string;
  data: PlayerTagItem | null;
  error: string | null;
}> {
  const baseUrl = normalizeBaseUrl(baseUrlOverride);
  const requestUrl = `${baseUrl}/registry/player-tags`;

  try {
    const response = await fetch(requestUrl, {
      method: "POST",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }

    const item =
      body && typeof body === "object" && !Array.isArray(body)
        ? asPlayerTagItem((body as Record<string, unknown>).item)
        : null;

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        baseUrl,
        data: item,
        error: `backend returned ${response.status}`,
      };
    }

    return { ok: true, status: response.status, baseUrl, data: item, error: null };
  } catch (error) {
    return {
      ok: false,
      status: 503,
      baseUrl,
      data: null,
      error: error instanceof Error ? error.message : "network error",
    };
  }
}

export async function deletePlayerTag(
  payload: { id?: number; player?: string; tag?: string },
  baseUrlOverride?: string,
): Promise<{
  ok: boolean;
  status: number;
  baseUrl: string;
  deleted: boolean;
  error: string | null;
}> {
  const baseUrl = normalizeBaseUrl(baseUrlOverride);
  const requestUrl = `${baseUrl}/registry/player-tags`;

  try {
    const response = await fetch(requestUrl, {
      method: "DELETE",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }

    const deleted =
      body && typeof body === "object" && !Array.isArray(body)
        ? Boolean((body as Record<string, unknown>).deleted)
        : false;

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        baseUrl,
        deleted,
        error: `backend returned ${response.status}`,
      };
    }

    return { ok: true, status: response.status, baseUrl, deleted, error: null };
  } catch (error) {
    return {
      ok: false,
      status: 503,
      baseUrl,
      deleted: false,
      error: error instanceof Error ? error.message : "network error",
    };
  }
}

export type PoetryGenerateRequest = {
  player_id: string;
  poem: string;
  scene_theme?: string;
  scene_hint?: string;
  anchor?: string;
  player_position?: Record<string, unknown>;
  max_resources?: number;
};

export type PoetryGeneratePayload = Record<string, unknown>;

export async function generatePoetryScene(
  payload: PoetryGenerateRequest,
  baseUrlOverride?: string,
): Promise<{
  ok: boolean;
  status: number;
  baseUrl: string;
  data: PoetryGeneratePayload | null;
  error: string | null;
}> {
  const baseUrl = normalizeBaseUrl(baseUrlOverride);
  const requestUrl = `${baseUrl}/poetry/generate`;

  try {
    const response = await fetch(requestUrl, {
      method: "POST",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    let body: PoetryGeneratePayload | null = null;
    try {
      body = (await response.json()) as PoetryGeneratePayload;
    } catch {
      body = null;
    }

    if (!response.ok) {
      const detail =
        body && typeof body === "object" && !Array.isArray(body) && typeof (body as Record<string, unknown>).detail === "string"
          ? String((body as Record<string, unknown>).detail)
          : `backend returned ${response.status}`;
      return {
        ok: false,
        status: response.status,
        baseUrl,
        data: body,
        error: detail,
      };
    }

    return {
      ok: true,
      status: response.status,
      baseUrl,
      data: body,
      error: null,
    };
  } catch (error) {
    return {
      ok: false,
      status: 503,
      baseUrl,
      data: null,
      error: error instanceof Error ? error.message : "network error",
    };
  }
}
