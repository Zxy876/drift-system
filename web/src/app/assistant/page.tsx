import Link from "next/link";

export default function AssistantIndexPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-5 px-6 py-10">
      <h1 className="text-2xl font-semibold">Assistant</h1>
      <p className="text-sm opacity-80">请使用带玩家ID的路由查看解释页。</p>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Link
          className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          href="/assistant/railway-smoke"
        >
          打开 /assistant/railway-smoke
        </Link>
        <Link
          className="inline-flex items-center justify-center rounded-lg border border-black/10 px-4 py-2 text-sm hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
          href="/assistant/demo_player"
        >
          打开 /assistant/demo_player
        </Link>
      </div>
    </main>
  );
}
