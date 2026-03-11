import {
  fetchIntentTrace,
  type IntentTracePayload,
} from "@/lib/drift-backend";

import IntentDebuggerClient from "./intent-debugger-client";

type IntentPageProps = {
  params: Promise<{ playerId: string }>;
};

export default async function IntentPage({ params }: IntentPageProps) {
  const { playerId } = await params;
  const result = await fetchIntentTrace(playerId);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-6 py-8">
      <header className="rounded-xl border border-black/10 p-5 dark:border-white/20">
        <h1 className="text-2xl font-semibold">Intent Debugger</h1>
        <p className="mt-2 text-sm opacity-80">
          route: /intent/{playerId}
        </p>
        <p className="text-sm opacity-80">
          解释链路：Player Input → Intent → Semantic → Narrative → Scene → World。
        </p>
      </header>

      <IntentDebuggerClient
        playerId={playerId}
        payload={result.data as IntentTracePayload | null}
        ok={result.ok}
        error={result.error}
      />
    </main>
  );
}