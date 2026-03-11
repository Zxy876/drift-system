import {
  fetchNarrativeGraph,
  fetchWorldState,
  type NarrativeGraphPayload,
  type WorldStatePayload,
} from "@/lib/drift-backend";

import NarrativeMapClient from "./narrative-map-client";

type NarrativePageProps = {
  params: Promise<{ playerId: string }>;
};

export default async function NarrativePage({ params }: NarrativePageProps) {
  const { playerId } = await params;

  const [graphResult, worldResult] = await Promise.all([
    fetchNarrativeGraph(),
    fetchWorldState(playerId),
  ]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-6 py-8">
      <header className="rounded-xl border border-black/10 p-5 dark:border-white/20">
        <h1 className="text-2xl font-semibold">Narrative Map</h1>
        <p className="mt-2 text-sm opacity-80">
          route: /narrative/{playerId}
        </p>
      </header>

      <NarrativeMapClient
        playerId={playerId}
        graphPayload={graphResult.data as NarrativeGraphPayload | null}
        worldPayload={worldResult.data as WorldStatePayload | null}
        graphOk={graphResult.ok}
        graphError={graphResult.error}
        worldOk={worldResult.ok}
        worldError={worldResult.error}
      />
    </main>
  );
}
