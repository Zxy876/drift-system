import RegistryClient from "./registry-client";

export default function RegistryPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-6 px-6 py-8">
      <header className="rounded-xl border border-black/10 p-5 dark:border-white/20">
        <h1 className="text-2xl font-semibold">Player Resource Registry</h1>
        <p className="mt-2 text-sm opacity-80">route: /registry</p>
        <p className="text-sm opacity-80">管理玩家 vocabulary 的 tag → resource 绑定。</p>
      </header>

      <RegistryClient />
    </main>
  );
}
