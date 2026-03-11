import { fetchWorldState } from "@/lib/drift-backend";

type PlayerDashboardPageProps = {
  params: Promise<{ playerId: string }>;
};

function asObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function asObjectArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => asObject(item))
    .filter((item): item is Record<string, unknown> => Boolean(item));
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter((item) => Boolean(item));
}

function sceneTimelineRows(payload: Record<string, unknown> | null): Record<string, unknown>[] {
  if (!payload) {
    return [];
  }

  const timeline = payload.scene_timeline;
  if (Array.isArray(timeline)) {
    return asObjectArray(timeline);
  }

  const timelineObject = asObject(timeline);
  if (!timelineObject) {
    return [];
  }

  if (Array.isArray(timelineObject.events)) {
    return asObjectArray(timelineObject.events);
  }

  if (typeof timelineObject.type === "string") {
    return [timelineObject];
  }

  return [];
}

function formatEventLabel(eventType: string): string {
  const token = eventType.trim().toLowerCase();
  if (token === "scene_generated") {
    return "Scene Generated";
  }
  if (token === "scene_blocked") {
    return "Scene Blocked";
  }
  return token || "Scene Event";
}

export default async function PlayerDashboardPage({ params }: PlayerDashboardPageProps) {
  const { playerId } = await params;
  const result = await fetchWorldState(playerId);

  const payload = asObject(result.data);
  const storyState = asObject(payload?.story_state);
  const narrativeState = asObject(payload?.narrative_state);
  const questState = asObject(payload?.quest_state) ?? asObject(payload?.quest_runtime);
  const sceneTimeline = sceneTimelineRows(payload).slice(0, 10);
  const assetSelection = asObject(payload?.asset_selection);
  const globalSelectedAssets =
    asStringArray(payload?.selected_assets).length > 0
      ? asStringArray(payload?.selected_assets)
      : asStringArray(assetSelection?.selected_assets);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-6 px-6 py-8">
      <header className="rounded-xl border border-black/10 p-5 dark:border-white/20">
        <h1 className="text-2xl font-semibold">Player Dashboard</h1>
        <p className="mt-2 text-sm opacity-80">player_id: {playerId}</p>
        <p className="text-sm opacity-80">backend: {result.baseUrl}</p>
      </header>

      {!result.ok && (
        <section className="rounded-xl border border-red-500/30 bg-red-500/10 p-5">
          <h2 className="text-lg font-semibold">Backend request failed</h2>
          <p className="mt-2 text-sm">{result.error || "unknown error"}</p>
          <p className="text-sm">status: {result.status}</p>
        </section>
      )}

      <section className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="font-semibold">Recent Scene Events</h2>
        {sceneTimeline.length === 0 ? (
          <p className="mt-2 text-sm opacity-80">No scene timeline events available.</p>
        ) : (
          <div className="mt-3 space-y-3">
            {sceneTimeline.map((event, index) => {
              const rowType = String(event.type ?? "");
              const eventType = String(event.event_type ?? "unknown");
              const generated = Boolean(event.generated);
              const reason = typeof event.reason === "string" ? event.reason : "-";
              const nextAvailable = Number(event.next_available_in);
              const hasCooldown = Number.isFinite(nextAvailable);

              const eventSelectedAssets = asStringArray(event.selected_assets);
              const assets = eventSelectedAssets.length > 0 ? eventSelectedAssets : globalSelectedAssets;

              return (
                <article
                  key={`${String(event.at_ms ?? "event")}-${index}`}
                  className="rounded-lg border border-black/10 p-3 dark:border-white/20"
                >
                  <p className="text-sm font-semibold">{formatEventLabel(rowType)}</p>
                  <p className="mt-1 text-xs opacity-85">event_type: {eventType}</p>
                  <p className="text-xs opacity-85">generated: {String(generated)}</p>
                  <p className="text-xs opacity-85">reason: {reason}</p>
                  <p className="text-xs opacity-85">
                    cooldown: {hasCooldown ? `${Math.max(0, Math.floor(nextAvailable))}s` : "-"}
                  </p>
                  <p className="text-xs opacity-85">
                    assets: {assets.length > 0 ? assets.join(", ") : "-"}
                  </p>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="font-semibold">Story</h2>
          <pre className="mt-2 overflow-auto text-xs opacity-85">{JSON.stringify(storyState ?? {}, null, 2)}</pre>
        </article>

        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="font-semibold">Narrative</h2>
          <pre className="mt-2 overflow-auto text-xs opacity-85">{JSON.stringify(narrativeState ?? {}, null, 2)}</pre>
        </article>

        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="font-semibold">Quest</h2>
          <pre className="mt-2 overflow-auto text-xs opacity-85">{JSON.stringify(questState ?? {}, null, 2)}</pre>
        </article>
      </section>

      <section className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="font-semibold">Raw /world/state payload</h2>
        <pre className="mt-2 max-h-[48vh] overflow-auto text-xs opacity-90">
          {JSON.stringify(result.data ?? {}, null, 2)}
        </pre>
      </section>
    </main>
  );
}
