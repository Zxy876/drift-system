"use client";

import { useMemo, useState } from "react";

type JsonMap = Record<string, unknown>;

type ScenesExplorerClientProps = {
  payload: JsonMap | null;
  ok: boolean;
  error: string | null;
};

type TagIndexRow = {
  tag: string;
  resources: string[];
  fragments: string[];
};

function asObject(value: unknown): JsonMap | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as JsonMap;
}

function normalizeToken(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  return value.trim();
}

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const seen = new Set<string>();
  const rows: string[] = [];
  for (const item of value) {
    const token = normalizeToken(item);
    if (!token || seen.has(token)) {
      continue;
    }
    seen.add(token);
    rows.push(token);
  }
  return rows;
}

function toRecordOfObjects(value: unknown): Record<string, JsonMap> {
  const source = asObject(value);
  if (!source) {
    return {};
  }

  const target: Record<string, JsonMap> = {};
  for (const [key, row] of Object.entries(source)) {
    const rowMap = asObject(row);
    if (rowMap) {
      target[key] = rowMap;
    }
  }
  return target;
}

function fragmentThemeKeywords(fragment: JsonMap | undefined): string[] {
  return normalizeStringList(fragment?.theme_keywords);
}

function fragmentSemanticTags(fragment: JsonMap | undefined): string[] {
  return normalizeStringList(fragment?.tags);
}

function FragmentButton({
  fragmentId,
  themes,
  tags,
  selected,
  onSelect,
}: {
  fragmentId: string;
  themes: string[];
  tags: string[];
  selected: boolean;
  onSelect: (fragmentId: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(fragmentId)}
      className={`w-full rounded-lg border px-3 py-2 text-left text-xs transition ${
        selected
          ? "border-black dark:border-white"
          : "border-black/10 hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
      }`}
    >
      <div className="font-semibold">{fragmentId}</div>
      <div className="mt-1 opacity-80">theme: {themes.length ? themes.join(", ") : "(none)"}</div>
      <div className="opacity-80">tags: {tags.length ? tags.join(", ") : "(none)"}</div>
    </button>
  );
}

export default function ScenesExplorerClient({ payload, ok, error }: ScenesExplorerClientProps) {
  const meta = asObject(payload?.meta) ?? {};
  const fragmentGraph = toRecordOfObjects(payload?.fragment_graph);
  const fragments = toRecordOfObjects(payload?.fragments);
  const themes = toRecordOfObjects(payload?.themes);
  const semanticTagsMap = useMemo(() => asObject(payload?.semantic_tags) ?? {}, [payload]);

  const rootRows = useMemo(() => {
    const rows = Object.entries(fragmentGraph).map(([rootId, row]) => ({
      rootId,
      children: normalizeStringList(row.children),
    }));
    rows.sort((a, b) => a.rootId.localeCompare(b.rootId));
    return rows;
  }, [fragmentGraph]);

  const themesByFragment = useMemo(() => {
    const mapping = new Map<string, string[]>();

    for (const [themeId, row] of Object.entries(themes)) {
      const allowed = normalizeStringList(row.allowed_fragments);
      for (const fragmentId of allowed) {
        const existing = mapping.get(fragmentId) ?? [];
        if (!existing.includes(themeId)) {
          existing.push(themeId);
          existing.sort();
          mapping.set(fragmentId, existing);
        }
      }
    }

    return mapping;
  }, [themes]);

  const tagIndex = useMemo((): TagIndexRow[] => {
    const mapping = new Map<string, { resources: Set<string>; fragments: Set<string> }>();

    for (const [resourceId, rawTags] of Object.entries(semanticTagsMap)) {
      for (const tag of normalizeStringList(rawTags)) {
        const row = mapping.get(tag) ?? { resources: new Set<string>(), fragments: new Set<string>() };
        row.resources.add(resourceId);
        mapping.set(tag, row);
      }
    }

    for (const [fragmentId, fragment] of Object.entries(fragments)) {
      for (const tag of fragmentSemanticTags(fragment)) {
        const row = mapping.get(tag) ?? { resources: new Set<string>(), fragments: new Set<string>() };
        row.fragments.add(fragmentId);
        mapping.set(tag, row);
      }
    }

    return Array.from(mapping.entries())
      .map(([tag, row]) => ({
        tag,
        resources: Array.from(row.resources).sort(),
        fragments: Array.from(row.fragments).sort(),
      }))
      .sort((a, b) => a.tag.localeCompare(b.tag));
  }, [semanticTagsMap, fragments]);

  const defaultFragmentId = rootRows[0]?.rootId || Object.keys(fragments)[0] || "";
  const [selectedFragmentId, setSelectedFragmentId] = useState<string>(defaultFragmentId);

  const selectedFragment = fragments[selectedFragmentId];
  const selectedThemes =
    themesByFragment.get(selectedFragmentId) ?? fragmentThemeKeywords(selectedFragment);
  const selectedSemanticTags = fragmentSemanticTags(selectedFragment);
  const selectedChildren =
    normalizeStringList(fragmentGraph[selectedFragmentId]?.children) || [];
  const parentRoots = rootRows
    .filter((row) => row.children.includes(selectedFragmentId))
    .map((row) => row.rootId);

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[2fr_1fr]">
      <section className="flex flex-col gap-4">
        {!ok && (
          <article className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm">
            <h2 className="font-semibold">Scenes API Warning</h2>
            <p className="mt-2">{error || "request failed"}</p>
          </article>
        )}

        <article className="grid grid-cols-2 gap-3 rounded-xl border border-black/10 p-4 text-sm dark:border-white/20 md:grid-cols-4">
          <div>
            <div className="opacity-70">roots</div>
            <div className="font-semibold">{Number(meta.fragment_graph_root_count ?? rootRows.length)}</div>
          </div>
          <div>
            <div className="opacity-70">fragments</div>
            <div className="font-semibold">{Number(meta.fragment_count ?? Object.keys(fragments).length)}</div>
          </div>
          <div>
            <div className="opacity-70">themes</div>
            <div className="font-semibold">{Number(meta.theme_count ?? Object.keys(themes).length)}</div>
          </div>
          <div>
            <div className="opacity-70">semantic tags</div>
            <div className="font-semibold">{tagIndex.length}</div>
          </div>
        </article>

        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="text-base font-semibold">Fragment Graph</h2>
          <p className="mt-1 text-xs opacity-75">展示 roots / children，点击 fragment 查看详情。</p>

          <div className="mt-3 space-y-2">
            {rootRows.map((row) => {
              const rootFragment = fragments[row.rootId];
              const rootThemes = themesByFragment.get(row.rootId) ?? fragmentThemeKeywords(rootFragment);
              const rootTags = fragmentSemanticTags(rootFragment);

              return (
                <details key={row.rootId} className="rounded-lg border border-black/10 p-3 dark:border-white/20">
                  <summary className="cursor-pointer text-sm font-medium">
                    {row.rootId} · children {row.children.length}
                  </summary>

                  <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
                    <div className="space-y-2">
                      <div className="text-xs font-semibold opacity-80">Root Fragment</div>
                      <FragmentButton
                        fragmentId={row.rootId}
                        themes={rootThemes}
                        tags={rootTags}
                        selected={selectedFragmentId === row.rootId}
                        onSelect={setSelectedFragmentId}
                      />
                    </div>

                    <div className="space-y-2">
                      <div className="text-xs font-semibold opacity-80">Children</div>
                      {row.children.length === 0 ? (
                        <div className="rounded-lg border border-dashed border-black/10 px-3 py-2 text-xs opacity-70 dark:border-white/20">
                          (none)
                        </div>
                      ) : (
                        row.children.map((childId) => {
                          const childFragment = fragments[childId];
                          const childThemes = themesByFragment.get(childId) ?? fragmentThemeKeywords(childFragment);
                          const childTags = fragmentSemanticTags(childFragment);

                          return (
                            <FragmentButton
                              key={`${row.rootId}:${childId}`}
                              fragmentId={childId}
                              themes={childThemes}
                              tags={childTags}
                              selected={selectedFragmentId === childId}
                              onSelect={setSelectedFragmentId}
                            />
                          );
                        })
                      )}
                    </div>
                  </div>
                </details>
              );
            })}
          </div>
        </article>

        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="text-base font-semibold">Theme Registry</h2>
          <p className="mt-1 text-xs opacity-75">每个 theme 对应允许 fragments。</p>

          <div className="mt-3 space-y-2">
            {Object.entries(themes)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([themeId, row]) => {
                const allowed = normalizeStringList(row.allowed_fragments);
                const keywords = normalizeStringList(row.keywords);

                return (
                  <details key={themeId} className="rounded-lg border border-black/10 p-3 dark:border-white/20">
                    <summary className="cursor-pointer text-sm font-medium">
                      {themeId} · allowed {allowed.length}
                    </summary>

                    <div className="mt-3 space-y-2">
                      <div className="text-xs opacity-80">keywords: {keywords.length ? keywords.join(", ") : "(none)"}</div>
                      <div className="flex flex-wrap gap-2">
                        {allowed.length === 0 ? (
                          <span className="text-xs opacity-70">(none)</span>
                        ) : (
                          allowed.map((fragmentId) => (
                            <button
                              key={`${themeId}:${fragmentId}`}
                              type="button"
                              onClick={() => setSelectedFragmentId(fragmentId)}
                              className={`rounded-md border px-2 py-1 text-xs ${
                                selectedFragmentId === fragmentId
                                  ? "border-black dark:border-white"
                                  : "border-black/10 hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
                              }`}
                            >
                              {fragmentId}
                            </button>
                          ))
                        )}
                      </div>
                    </div>
                  </details>
                );
              })}
          </div>
        </article>

        <article className="rounded-xl border border-black/10 p-4 dark:border-white/20">
          <h2 className="text-base font-semibold">Semantic Tags</h2>
          <p className="mt-1 text-xs opacity-75">tag → resource / fragment 映射。</p>

          <div className="mt-3 space-y-2">
            {tagIndex.map((row) => (
              <details key={row.tag} className="rounded-lg border border-black/10 p-3 dark:border-white/20">
                <summary className="cursor-pointer text-sm font-medium">
                  {row.tag} · resources {row.resources.length} · fragments {row.fragments.length}
                </summary>

                <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
                  <div>
                    <div className="text-xs font-semibold opacity-80">Resources</div>
                    <div className="mt-2 max-h-36 overflow-auto rounded-md border border-black/10 p-2 text-xs dark:border-white/20">
                      {row.resources.length === 0 ? "(none)" : row.resources.join("\n")}
                    </div>
                  </div>

                  <div>
                    <div className="text-xs font-semibold opacity-80">Fragments</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {row.fragments.length === 0 ? (
                        <span className="text-xs opacity-70">(none)</span>
                      ) : (
                        row.fragments.map((fragmentId) => (
                          <button
                            key={`${row.tag}:${fragmentId}`}
                            type="button"
                            onClick={() => setSelectedFragmentId(fragmentId)}
                            className={`rounded-md border px-2 py-1 text-xs ${
                              selectedFragmentId === fragmentId
                                ? "border-black dark:border-white"
                                : "border-black/10 hover:bg-black/5 dark:border-white/20 dark:hover:bg-white/10"
                            }`}
                          >
                            {fragmentId}
                          </button>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              </details>
            ))}
          </div>
        </article>
      </section>

      <aside className="h-fit rounded-xl border border-black/10 p-4 dark:border-white/20 xl:sticky xl:top-6">
        <h2 className="text-base font-semibold">Fragment Detail</h2>
        <p className="mt-1 text-xs opacity-75">点击任意 fragment 可在这里查看结构信息。</p>

        {!selectedFragmentId ? (
          <p className="mt-3 text-sm opacity-75">(no fragment selected)</p>
        ) : (
          <div className="mt-3 space-y-3 text-xs">
            <div>
              <div className="opacity-70">id</div>
              <div className="font-semibold">{selectedFragmentId}</div>
            </div>

            <div>
              <div className="opacity-70">theme</div>
              <div>{selectedThemes.length ? selectedThemes.join(", ") : "(none)"}</div>
            </div>

            <div>
              <div className="opacity-70">semantic tags</div>
              <div>{selectedSemanticTags.length ? selectedSemanticTags.join(", ") : "(none)"}</div>
            </div>

            <div>
              <div className="opacity-70">children fragments</div>
              <div>{selectedChildren.length ? selectedChildren.join(", ") : "(none)"}</div>
            </div>

            <div>
              <div className="opacity-70">pack source</div>
              <div>
                {normalizeToken(selectedFragment?.source_pack) || "(unknown)"}
                {normalizeToken(selectedFragment?.source)
                  ? ` / ${normalizeToken(selectedFragment?.source)}`
                  : ""}
              </div>
            </div>

            <div>
              <div className="opacity-70">parent roots</div>
              <div>{parentRoots.length ? parentRoots.join(", ") : "(none)"}</div>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}
