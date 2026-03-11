import {
  fetchScenesLibrary,
  type ScenesLibraryPayload,
} from "@/lib/drift-backend";

import ScenesExplorerClient from "./scenes-explorer-client";

export default async function ScenesPage() {
  const result = await fetchScenesLibrary();

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-6 py-8">
      <header className="rounded-xl border border-black/10 p-5 dark:border-white/20">
        <h1 className="text-2xl font-semibold">Scene Explorer</h1>
        <p className="mt-2 text-sm opacity-80">
          只读浏览 Drift Scene Library：fragment graph、theme registry、semantic tags。
        </p>
      </header>

      <ScenesExplorerClient
        payload={result.data as ScenesLibraryPayload | null}
        ok={result.ok}
        error={result.error}
      />
    </main>
  );
}
