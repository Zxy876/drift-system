"use client";

import { useMemo, useState } from "react";

import {
  deletePlayerTag,
  listPlayerTags,
  searchRegistryResources,
  upsertPlayerTag,
  type PlayerTagItem,
  type RegistryResourceItem,
} from "@/lib/drift-backend";

export default function RegistryClient() {
  const [playerId, setPlayerId] = useState("vivn");
  const [tag, setTag] = useState("shrine");
  const [resource, setResource] = useState("minecraft:lantern");
  const [searchQuery, setSearchQuery] = useState("temple");

  const [loadingTags, setLoadingTags] = useState(false);
  const [savingTag, setSavingTag] = useState(false);
  const [searching, setSearching] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const [items, setItems] = useState<PlayerTagItem[]>([]);
  const [groupedTags, setGroupedTags] = useState<Record<string, string[]>>({});
  const [searchItems, setSearchItems] = useState<RegistryResourceItem[]>([]);

  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const sortedItems = useMemo(
    () => [...items].sort((a, b) => b.updated_at - a.updated_at || b.id - a.id),
    [items],
  );

  const loadTags = async () => {
    const normalizedPlayer = String(playerId || "").trim();
    if (!normalizedPlayer) {
      setError("player_id 不能为空");
      return;
    }

    setLoadingTags(true);
    setError(null);
    setInfo(null);

    const result = await listPlayerTags(normalizedPlayer);
    setLoadingTags(false);

    if (!result.ok) {
      setError(result.error || "加载玩家词典失败");
      return;
    }

    setItems(result.data);
    setGroupedTags(result.tags);
    setInfo(`已加载 ${normalizedPlayer} 的 registry 数据`);
  };

  const onSearch = async () => {
    const normalized = String(searchQuery || "").trim();
    if (!normalized) {
      setSearchItems([]);
      return;
    }

    setSearching(true);
    setError(null);
    setInfo(null);

    const result = await searchRegistryResources(normalized, { limit: 20, source: "all" });
    setSearching(false);

    if (!result.ok) {
      setError(result.error || "搜索资源失败");
      return;
    }

    setSearchItems(result.data);
    setInfo(`搜索完成：${result.data.length} 条候选资源`);
  };

  const onAdd = async () => {
    const normalizedPlayer = String(playerId || "").trim();
    const normalizedTag = String(tag || "").trim();
    const normalizedResource = String(resource || "").trim();

    if (!normalizedPlayer || !normalizedTag || !normalizedResource) {
      setError("player/tag/resource 均不能为空");
      return;
    }

    setSavingTag(true);
    setError(null);
    setInfo(null);

    const result = await upsertPlayerTag({
      player: normalizedPlayer,
      tag: normalizedTag,
      resource: normalizedResource,
    });

    setSavingTag(false);

    if (!result.ok) {
      setError(result.error || "保存绑定失败");
      return;
    }

    setInfo("绑定已保存");
    await loadTags();
  };

  const onDelete = async (item: PlayerTagItem) => {
    setDeletingId(item.id);
    setError(null);
    setInfo(null);

    const result = await deletePlayerTag({ id: item.id });
    setDeletingId(null);

    if (!result.ok || !result.deleted) {
      setError(result.error || "删除失败");
      return;
    }

    setInfo(`已删除 tag 绑定 #${item.id}`);
    await loadTags();
  };

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.2fr_1.8fr]">
      <section className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="text-base font-semibold">Registry Actions</h2>

        {error && (
          <article className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm">
            {error}
          </article>
        )}

        {info && (
          <article className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm">
            {info}
          </article>
        )}

        <div className="mt-3 space-y-3 text-sm">
          <div>
            <label className="mb-1 block font-medium" htmlFor="player-id">player_id</label>
            <input
              id="player-id"
              value={playerId}
              onChange={(event) => setPlayerId(event.target.value)}
              className="w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 dark:border-white/20"
            />
          </div>

          <div>
            <label className="mb-1 block font-medium" htmlFor="search-q">Resource Search</label>
            <div className="flex gap-2">
              <input
                id="search-q"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                className="w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 dark:border-white/20"
              />
              <button
                type="button"
                onClick={onSearch}
                disabled={searching}
                className="rounded-lg border border-black/10 px-3 py-2 hover:bg-black/5 disabled:opacity-60 dark:border-white/20 dark:hover:bg-white/10"
              >
                {searching ? "搜索中..." : "Search"}
              </button>
            </div>
          </div>

          <div>
            <label className="mb-1 block font-medium" htmlFor="tag">tag</label>
            <input
              id="tag"
              value={tag}
              onChange={(event) => setTag(event.target.value)}
              className="w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 dark:border-white/20"
            />
          </div>

          <div>
            <label className="mb-1 block font-medium" htmlFor="resource">resource</label>
            <input
              id="resource"
              value={resource}
              onChange={(event) => setResource(event.target.value)}
              className="w-full rounded-lg border border-black/10 bg-transparent px-3 py-2 dark:border-white/20"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onAdd}
              disabled={savingTag}
              className="rounded-lg border border-black/10 px-3 py-2 hover:bg-black/5 disabled:opacity-60 dark:border-white/20 dark:hover:bg-white/10"
            >
              {savingTag ? "保存中..." : "Add / Update"}
            </button>
            <button
              type="button"
              onClick={loadTags}
              disabled={loadingTags}
              className="rounded-lg border border-black/10 px-3 py-2 hover:bg-black/5 disabled:opacity-60 dark:border-white/20 dark:hover:bg-white/10"
            >
              {loadingTags ? "加载中..." : "Load Player Tags"}
            </button>
          </div>
        </div>

        <details className="mt-4 rounded-lg border border-black/10 p-3 text-xs dark:border-white/20">
          <summary className="cursor-pointer font-medium">Grouped Tags View</summary>
          <pre className="mt-2 overflow-auto">{JSON.stringify(groupedTags, null, 2)}</pre>
        </details>
      </section>

      <section className="space-y-4">
        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="text-base font-semibold">Search Results</h2>
          {searchItems.length === 0 ? (
            <p className="mt-2 text-sm opacity-70">(none)</p>
          ) : (
            <ul className="mt-2 space-y-1 text-sm">
              {searchItems.map((row) => (
                <li key={`${row.resource_id}-${row.source}`} className="rounded-md border border-black/10 p-2 dark:border-white/20">
                  <div className="font-medium">{row.resource_id}</div>
                  <div className="text-xs opacity-70">
                    type={row.resource_type} · namespace={row.namespace} · source={row.source}
                  </div>
                  <button
                    type="button"
                    onClick={() => setResource(row.resource_id)}
                    className="mt-2 rounded border border-black/10 px-2 py-1 text-xs hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
                  >
                    Use this resource
                  </button>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="text-base font-semibold">Player Tag Bindings</h2>
          {sortedItems.length === 0 ? (
            <p className="mt-2 text-sm opacity-70">(none)</p>
          ) : (
            <ul className="mt-2 space-y-1 text-sm">
              {sortedItems.map((item) => (
                <li key={item.id} className="flex items-center justify-between gap-3 rounded-md border border-black/10 p-2 dark:border-white/20">
                  <div>
                    <div className="font-medium">{item.tag} → {item.resource_id}</div>
                    <div className="text-xs opacity-70">id={item.id} · player={item.player_id}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onDelete(item)}
                    disabled={deletingId === item.id}
                    className="rounded border border-black/10 px-2 py-1 text-xs hover:bg-black/5 disabled:opacity-60 dark:border-white/20 dark:hover:bg-white/10"
                  >
                    {deletingId === item.id ? "Deleting..." : "Delete"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </article>
      </section>
    </div>
  );
}
