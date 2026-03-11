import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col justify-center gap-6 px-6">
      <h1 className="text-3xl font-semibold">Drift Web</h1>
      <p className="text-sm opacity-80">
        v1 首屏已就绪：Player Dashboard（读取 `/world/state/{'{player_id}'}`）。
      </p>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Link
          className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          href="/player/demo_player"
        >
          打开示例玩家页
        </Link>
        <Link
          className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          href="/player/railway-smoke"
        >
          打开 railway-smoke
        </Link>
        <Link
          className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          href="/narrative/railway-smoke"
        >
          打开 Narrative Map
        </Link>
        <Link
          className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          href="/intent/railway-smoke"
        >
          打开 Intent Debugger
        </Link>
        <Link
          className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          href="/assistant/railway-smoke"
        >
          打开 Assistant
        </Link>
        <Link
          className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          href="/scenes"
        >
          打开 Scene Explorer
        </Link>
        <Link
          className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          href="/settings/generation"
        >
          打开 Generation Control
        </Link>
        <Link
          className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          href="/registry"
        >
          打开 Resource Registry
        </Link>
        <Link
          className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          href="/poetry"
        >
          打开 Poetry Generator
        </Link>
        <Link
          className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          href="/about"
        >
          About Drift
        </Link>
      </div>
    </main>
  );
}
