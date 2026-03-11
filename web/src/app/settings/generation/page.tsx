import {
  fetchGenerationPolicy,
  type GenerationPolicyPayload,
} from "@/lib/drift-backend";

import GenerationSettingsClient from "./settings-client";

export default async function GenerationSettingsPage() {
  const result = await fetchGenerationPolicy();

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-6 px-6 py-8">
      <header className="rounded-xl border border-black/10 p-5 dark:border-white/20">
        <h1 className="text-2xl font-semibold">Generation Control</h1>
        <p className="mt-2 text-sm opacity-80">
          route: /settings/generation
        </p>
        <p className="text-sm opacity-80">
          控制 Scene Generation Policy，避免剧情生成节奏过快或过密。
        </p>
      </header>

      <GenerationSettingsClient
        initialPolicy={result.data as GenerationPolicyPayload | null}
        initialOk={result.ok}
        initialError={result.error}
        baseUrl={result.baseUrl}
      />
    </main>
  );
}
