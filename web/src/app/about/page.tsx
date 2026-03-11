export default function AboutPage() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <header className="rounded-xl border border-black/10 p-5 dark:border-white/20">
        <h1 className="text-2xl font-semibold">About Drift</h1>
        <p className="mt-2 text-sm opacity-80">
          Drift 是一个以叙事引擎为核心的 Minecraft 运行时系统，Drift-Web 是它的 Control UI。
        </p>
      </header>

      <section className="rounded-xl border border-black/10 p-5 dark:border-white/20">
        <h2 className="text-lg font-semibold">System Architecture</h2>
        <pre className="mt-3 overflow-auto rounded-lg border border-black/10 p-4 text-sm dark:border-white/20">
{`Player
  ↓
Minecraft
  ↓
Drift Plugin
  ↓
Drift Engine
  ↓
Drift Backend
  ↓
Drift Web`}
        </pre>
      </section>

      <section className="rounded-xl border border-black/10 p-5 text-sm dark:border-white/20">
        <h2 className="text-lg font-semibold">What is Drift</h2>
        <ul className="mt-3 space-y-2">
          <li>- Drift Engine：负责 narrative / scene / semantic / runtime 决策。</li>
          <li>- Drift Backend：把引擎能力暴露为可观测、可调用的 API。</li>
          <li>- Drift Web：面向调试与控制的前端控制台。</li>
        </ul>
      </section>
    </main>
  );
}
