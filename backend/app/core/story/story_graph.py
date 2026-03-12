# backend/app/core/story/story_graph.py

from collections import Counter, deque
import json
import os
import time
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


class StoryGraph:
    """
    StoryGraph — 关卡图控制器

    目标：
    - 从本地 JSON 关卡构建一个有向图
    - 提供：下一关 BFS 主线推进
    - 后面可扩展为分支、多结局等
    """

    def __init__(self, level_dir: str):
        """
        level_dir: like backend/data/flagship_levels
        """
        self.level_dir = level_dir
        self.levels: Dict[str, dict] = {}
        self.edges: Dict[str, List[str]] = {}   # 邻接表
        self.trajectory: Dict[str, List[Dict[str, Any]]] = {}
        self.level_sources: Dict[str, str] = {}
        self.alias_map: Dict[str, str] = {}
        self.memory_snapshots: Dict[str, List[str]] = {}
        self.reload_levels()

    def reload_levels(self) -> None:
        """Reload flagship and generated levels from disk, preserving runtime state."""

        self.levels.clear()
        self.level_sources.clear()
        self.alias_map.clear()
        self.edges.clear()
        self._load_levels()
        self._build_linear_graph()

    # ================= 加载所有 level_X.json =================
    def _load_levels(self):
        if not self.level_dir or not os.path.isdir(self.level_dir):
            print(f"[StoryGraph] level_dir not found: {self.level_dir}")
            return

        entries: List[Tuple[str, str, str]] = []

        for dirpath, _, filenames in os.walk(self.level_dir):
            rel_dir = os.path.relpath(dirpath, self.level_dir)
            head = rel_dir.split(os.sep)[0] if rel_dir != "." else ""
            source = "generated" if head == "generated" else "flagship"

            for fname in filenames:
                if not fname.endswith(".json"):
                    continue
                entries.append((dirpath, fname, source))

        entries.sort(key=lambda item: (0 if os.path.relpath(item[0], self.level_dir) == "." else 1, item[0], item[1]))

        for directory, fname, source in entries:
            path = os.path.join(directory, fname)

            try:
                with open(path, "r", encoding="utf8") as f:
                    data = json.load(f)
            except Exception as exc:
                print(f"[StoryGraph] Failed to load {fname}: {exc}")
                continue

            key = fname.replace(".json", "")
            if key in self.levels:
                continue

            self.levels[key] = data
            self.level_sources[key] = source
            self._register_alias(key, key)

            level_id = data.get("id")
            if isinstance(level_id, str):
                self._register_alias(level_id, key)

            self._register_numeric_aliases(key)

            if key == "flagship_tutorial":
                for alias in (
                    "tutorial",
                    "tutorial_level",
                    "level_tutorial",
                    "level_01",
                    "level_1",
                    "level01",
                    "level1",
                ):
                    self._register_alias(alias, key)

        print(f"[StoryGraph] Loaded {len(self.levels)} levels from {self.level_dir}")

    def _build_linear_graph(self) -> None:
        """Populate ``self.edges`` using continuity metadata and sensible fallbacks."""

        self.edges = {key: [] for key in self.levels.keys()}

        continuity_links: Dict[str, Set[str]] = {key: set() for key in self.levels.keys()}

        for key, payload in self.levels.items():
            continuity = payload.get("continuity") or {}
            if isinstance(continuity, dict):
                for field in ("next", "next_major_level"):
                    target = continuity.get(field)
                    if not target:
                        continue
                    canonical = self._canonical_level_id(target)
                    if canonical and canonical in self.levels:
                        continuity_links[key].add(canonical)

        # Apply continuity edges first to preserve authored sequencing.
        for key, targets in continuity_links.items():
            if not targets:
                continue
            self.edges[key].extend(sorted(targets))

        # Fallback: ensure a linear traversal ordered by chapter/index.
        ordering: List[Tuple[int, str]] = []
        for key, payload in self.levels.items():
            meta = payload.get("meta") or {}
            chapter = meta.get("chapter")
            order = int(chapter) if isinstance(chapter, int) else 10_000
            ordering.append((order, key))

        sorted_order = sorted(ordering)
        for idx, (_, key) in enumerate(sorted_order):
            if idx + 1 >= len(sorted_order):
                continue
            next_key = sorted_order[idx + 1][1]
            if next_key == key:
                continue
            if next_key not in self.edges[key]:
                self.edges[key].append(next_key)

        # Final fallback: if a node has no outgoing edges, leave list empty.
        print(f"[StoryGraph] Graph edges = {self.edges}")

    # ================= 主线推进：下一关（bfs next） ===============
    def bfs_next(self, current_level: str) -> Optional[str]:
        key = self._canonical_level_id(current_level)
        if not key or key not in self.edges:
            return None
        neighbors = self.edges[key]
        if not neighbors:
            return None
        return neighbors[0]

    # ================= MiniMap：整条主线顺序 =================
    def bfs_order(self, start: str) -> List[str]:
        """
        从某个关卡开始，按照图结构做 BFS，返回遍历顺序。
        MiniMap 会用它来决定「主线大地图」的绘制顺序。
        """
        if start not in self.levels:
            return []

        visited = set()
        order: List[str] = []

        q: deque[str] = deque([start])

        while q:
            lv = q.popleft()
            if lv in visited:
                continue
            visited.add(lv)
            order.append(lv)

            for nb in self.edges.get(lv, []):
                if nb not in visited:
                    q.append(nb)

        return order

    # ================= MiniMap：邻接节点 =================
    def neighbors(self, level_id: str) -> List[str]:
        """
        返回此关卡的相邻关卡（MiniMap 需要）
        """
        key = self._canonical_level_id(level_id)
        if not key:
            return []
        return self.edges.get(key, [])

    # ================= 工具函数: 拿关卡数据、拿全部关卡 ================
    def get_level(self, level_name: str) -> Optional[dict]:
        key = self._canonical_level_id(level_name)
        if not key:
            return None
        return self.levels.get(key)

    def all_levels(self) -> List[str]:
        return list(self.levels.keys())

    def canonicalize_level_id(self, level_id: Optional[str]) -> Optional[str]:
        return self._canonical_level_id(level_id)

    # ================= Phase 5: 记录剧情轨迹 =================
    def update_trajectory(self, player_id: str, level_id: Optional[str], action: str,
                          meta: Optional[Dict[str, Any]] = None) -> None:
        """Append a trajectory entry for a player's storyline."""

        if not player_id:
            return

        entry = {
            "level": level_id,
            "action": action,
            "meta": meta or {},
            "ts": time.time(),
        }
        self.trajectory.setdefault(player_id, []).append(entry)

    def update_memory_flags(
        self,
        player_id: str,
        flags: Iterable[str],
        *,
        level_id: Optional[str] = None,
        source: Optional[str] = None,
        ref: Optional[str] = None,
    ) -> None:
        normalized = []
        for flag in flags:
            if isinstance(flag, str):
                token = flag.strip()
            else:
                token = str(flag).strip()
            if token and token not in normalized:
                normalized.append(token)

        self.memory_snapshots[player_id] = normalized

        meta: Dict[str, Any] = {"flags": list(normalized)}
        if source:
            meta["source"] = source
        if ref:
            meta["ref"] = ref

        self.update_trajectory(player_id, level_id, "memory", meta)

    # ================= Phase 10: 智能推荐下一关 =================
    def recommend_next_levels(
        self,
        player_id: str,
        current_level: Optional[str],
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Recommend next levels with light-weight heuristics."""

        limit = max(0, limit or 0)
        if limit == 0:
            return []

        canonical_current = self._canonical_level_id(current_level)
        history = self.trajectory.get(player_id, []) or []

        normalized_history: List[Dict[str, Any]] = []
        for entry in history:
            raw_level = entry.get("level")
            normalized = self._canonical_level_id(raw_level)
            normalized_history.append({
                "raw": raw_level,
                "canonical": normalized,
                "action": entry.get("action"),
                "meta": entry.get("meta", {}),
                "ts": entry.get("ts"),
            })

        memory_flags: List[str] = []
        if player_id in self.memory_snapshots:
            memory_flags = list(self.memory_snapshots[player_id])
        else:
            for entry in reversed(history):
                if entry.get("action") != "memory":
                    continue
                meta = entry.get("meta") or {}
                raw_flags = meta.get("flags")
                if isinstance(raw_flags, list):
                    memory_flags = [
                        str(flag).strip()
                        for flag in raw_flags
                        if isinstance(flag, (str, int)) and str(flag).strip()
                    ]
                break
            if memory_flags:
                self.memory_snapshots[player_id] = list(memory_flags)

        recent_choices = [item for item in normalized_history if item.get("action") == "choice"]
        preferred_levels: List[str] = []
        choice_level_weights: Dict[str, int] = {}
        choice_tag_counter: Counter[str] = Counter()

        for choice in recent_choices:
            meta = choice.get("meta") or {}
            preferred = meta.get("next_level")
            canonical_pref = self._canonical_level_id(preferred) if preferred else None
            if canonical_pref:
                preferred_levels.append(canonical_pref)
                choice_level_weights[canonical_pref] = choice_level_weights.get(canonical_pref, 0) + 1
            tags = meta.get("tags") or []
            if isinstance(tags, str):
                tags = [token.strip() for token in tags.split(",") if token.strip()]
            for tag in tags:
                if isinstance(tag, str) and tag.strip():
                    choice_tag_counter[tag.strip().lower()] += 1

        completed_levels = {
            item["canonical"]
            for item in normalized_history
            if item["canonical"] and item["action"] == "exit"
        }
        seen_levels = [item["canonical"] for item in normalized_history if item["canonical"]]

        last_exit_level = None
        for item in reversed(normalized_history):
            if item["canonical"] and item["action"] == "exit":
                last_exit_level = item["canonical"]
                break

        tag_counter: Counter[str] = Counter()
        theme_counter: Counter[str] = Counter()
        chapter_values: List[int] = []
        generated_interest: Counter[str] = Counter()
        last_exit_theme: Optional[str] = None
        last_generated_level: Optional[str] = None
        for item in normalized_history:
            canonical = item["canonical"]
            if not canonical or item["action"] != "exit":
                continue
            level_data = self.get_level(canonical) or {}
            level_source = self.level_sources.get(canonical)
            for tag in level_data.get("tags", []) or []:
                if isinstance(tag, str):
                    tag_counter[tag] += 1
                    if level_source == "generated":
                        generated_interest[tag.lower()] += 1
            meta = level_data.get("meta") or {}
            chapter = meta.get("chapter")
            if isinstance(chapter, int):
                chapter_values.append(chapter)
            theme = level_data.get("storyline_theme")
            if isinstance(theme, str) and theme:
                theme_counter[theme] += 1
                last_exit_theme = theme
            if level_source == "generated":
                last_generated_level = canonical

        avg_chapter = sum(chapter_values) / len(chapter_values) if chapter_values else None

        candidate_ids: List[str] = []

        for preferred in preferred_levels:
            if preferred and preferred not in candidate_ids:
                candidate_ids.append(preferred)

        # 1) 当前关卡的邻居优先
        if canonical_current:
            candidate_ids.extend(self.neighbors(canonical_current))
            if canonical_current not in completed_levels:
                candidate_ids.append(canonical_current)

        # 2) 最近退出关卡的主线后继
        reference_level = canonical_current or last_exit_level
        if reference_level:
            next_mainline = self.bfs_next(reference_level)
            if next_mainline:
                candidate_ids.append(next_mainline)

        # 3) 补充未体验过的关卡，直到数量够用
        unvisited = [lv for lv in sorted(self.levels.keys()) if lv not in seen_levels]
        for lv in unvisited:
            if len(candidate_ids) >= max(limit * 2, limit + 1):
                break
            candidate_ids.append(lv)

        # 4) 最后兜底：全部关卡（保持顺序）
        if not candidate_ids:
            candidate_ids.extend(sorted(self.levels.keys()))

        if (
            "flagship_12" in completed_levels
            and "flagship_final" in self.levels
            and "flagship_final" not in candidate_ids
        ):
            candidate_ids.append("flagship_final")

        scored: Dict[str, Dict[str, Any]] = {}
        primary_mainline = None
        if reference_level:
            primary_mainline = self.bfs_next(reference_level)

        tag_total = sum(tag_counter.values())

        for candidate in candidate_ids:
            canonical = self._canonical_level_id(candidate)
            if not canonical:
                continue

            if canonical not in scored:
                scored[canonical] = {
                    "level_id": canonical,
                    "score": 0.0,
                    "reasons": [],
                }

            entry = scored[canonical]
            reasons = entry["reasons"]

            if canonical == primary_mainline:
                entry["score"] += 50.0
                reasons.append("主线推进")

            if canonical not in completed_levels:
                entry["score"] += 25.0
                reasons.append("尚未通关")
            else:
                exit_count = sum(1 for item in normalized_history if item["canonical"] == canonical and item["action"] == "exit")
                entry["score"] -= 10.0 * exit_count
                if exit_count > 0:
                    reasons.append("曾经通关")

            if canonical_current and canonical in self.neighbors(canonical_current):
                entry["score"] += 15.0
                reasons.append("连接当前剧情")

            if canonical == canonical_current:
                entry["score"] += 20.0
                reasons.append("继续当前关卡")

            level_data = self.get_level(canonical) or {}
            tags = [t for t in (level_data.get("tags") or []) if isinstance(t, str)]
            if tags and "tags" not in entry:
                entry["tags"] = list(tags)

            title = level_data.get("title") if isinstance(level_data, dict) else None
            if isinstance(title, str) and title:
                entry.setdefault("title", title)
            else:
                entry.setdefault("title", canonical)
            for tag in tags:
                if tag_total:
                    weight = tag_counter.get(tag, 0) / tag_total
                    if weight > 0:
                        entry["score"] += 20.0 * weight
                        if f"偏好：{tag}" not in reasons:
                            reasons.append(f"偏好：{tag}")

            theme = level_data.get("storyline_theme")
            if isinstance(theme, str) and theme:
                entry.setdefault("storyline_theme", theme)
                if last_exit_theme and theme == last_exit_theme:
                    entry["score"] += 18.0
                    if "延续旗舰叙事主题" not in reasons:
                        reasons.append("延续旗舰叙事主题")
                else:
                    total_theme = sum(theme_counter.values())
                    if total_theme:
                        affinity = theme_counter.get(theme, 0) / total_theme
                        if affinity > 0:
                            entry["score"] += 6.0 * affinity
                            if "契合常见主题" not in reasons:
                                reasons.append("契合常见主题")

            level_source = self.level_sources.get(canonical)
            if generated_interest and tags:
                overlap = sum(generated_interest.get(tag.lower(), 0) for tag in tags)
                if overlap > 0:
                    entry["score"] += 10.0 * overlap
                    cue = "契合玩家自创主题" if level_source == "generated" else "呼应玩家兴趣标签"
                    if cue not in reasons:
                        reasons.append(cue)

            tasks = []
            if isinstance(level_data, dict):
                tasks = [task for task in level_data.get("tasks", []) if isinstance(task, dict)]

            if level_source == "generated":
                entry.setdefault("origin", "generated")
                if canonical not in completed_levels:
                    entry["score"] += 5.0
                    if "新鲜的玩家创作" not in reasons:
                        reasons.append("新鲜的玩家创作")
                if canonical and canonical == last_generated_level:
                    entry["score"] += 12.0
                    if "延续近期玩家创作" not in reasons:
                        reasons.append("延续近期玩家创作")
                if tasks:
                    has_conditions = any(task.get("conditions") for task in tasks)
                    if has_conditions:
                        entry["score"] += 9.0
                        if "玩家创作任务已准备" not in reasons:
                            reasons.append("玩家创作任务已准备")

            if memory_flags:
                affinity_flags = self._collect_memory_list(level_data.get("memory_affinity"))
                overlap = sorted(set(memory_flags).intersection(affinity_flags))
                if overlap:
                    entry["score"] += 12.0 * len(overlap)
                    entry.setdefault("memory_match", [])
                    for flag in overlap:
                        if flag not in entry["memory_match"]:
                            entry["memory_match"].append(flag)
                    summary = "、".join(overlap[:2])
                    reason = f"记忆共鸣：{summary}" if summary else "记忆共鸣"
                    reasons.append(reason)

                recovery_flags = self._collect_memory_list(
                    level_data.get("memory_recovery") or level_data.get("memory_healing")
                )
                if recovery_flags and set(memory_flags).intersection(recovery_flags):
                    entry["score"] += 6.0
                    if "疗愈记忆" not in reasons:
                        reasons.append("疗愈记忆")

            meta = level_data.get("meta") or {}
            chapter = meta.get("chapter")
            if isinstance(chapter, int) and avg_chapter is not None:
                diff = abs(chapter - avg_chapter)
                if diff < 1:
                    entry["score"] += 8.0
                    reasons.append("章节节奏相似")
                elif diff <= 3:
                    entry["score"] += 2.0
                else:
                    entry["score"] -= 2.5
            if isinstance(chapter, int):
                entry.setdefault("chapter", chapter)

            if canonical in seen_levels and canonical not in completed_levels:
                entry["score"] += 5.0
                reasons.append("正在进行中")

            weight = choice_level_weights.get(canonical, 0)
            if weight:
                entry["score"] += 40.0 * weight
                reasons.append("呼应最近的剧情选择")

            if (
                canonical == "flagship_final"
                and "flagship_12" in completed_levels
                and canonical not in completed_levels
            ):
                entry["score"] += 1.0
                if "旗舰终章邀请" not in reasons:
                    reasons.append("旗舰终章邀请")

            if choice_tag_counter and tags:
                overlap = 0
                for tag in tags:
                    key = tag.lower()
                    overlap += choice_tag_counter.get(key, 0)
                if overlap > 0:
                    entry["score"] += 8.0 * overlap
                    reasons.append("契合分支偏好")

        ranked = sorted(
            scored.values(),
            key=lambda item: (-item["score"], item["level_id"]),
        )

        top_ranked = ranked[:limit]

        for item in top_ranked:
            reasons_list = item.get("reasons") or []
            if reasons_list:
                deduped = list(dict.fromkeys(reasons_list))
                item["reasons"] = deduped
                summary = "、".join(deduped[:3])
                if summary:
                    item["reason_summary"] = summary
            if "title" not in item:
                item["title"] = item.get("level_id")

        return top_ranked

    # ================= 内部工具 =================
    @staticmethod
    def _collect_memory_list(raw: Any) -> List[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            tokens = [token.strip() for token in raw.split(",")]
            return [token for token in tokens if token]
        if isinstance(raw, (list, tuple, set)):
            result: List[str] = []
            for item in raw:
                token = str(item).strip()
                if token:
                    result.append(token)
            return result
        if isinstance(raw, dict):
            return [
                str(value).strip()
                for value in raw.values()
                if isinstance(value, (str, int)) and str(value).strip()
            ]
        token = str(raw).strip()
        return [token] if token else []

    def _canonical_level_id(self, level_id: Optional[str]) -> Optional[str]:
        if not level_id:
            return None

        if level_id in self.levels:
            return level_id

        if not isinstance(level_id, str):
            return None

        normalized = level_id.replace(".json", "")
        if normalized in self.levels:
            return normalized

        lookup_key = normalized.lower()
        if lookup_key in self.alias_map:
            return self.alias_map[lookup_key]

        if lookup_key.startswith("level_"):
            suffix = lookup_key.split("_", 1)[1]
            if suffix.isdigit():
                padded = f"{int(suffix):02d}"
                flag = f"flagship_{padded}"
                if flag in self.levels:
                    return flag

        return normalized if normalized in self.levels else None

    # ================= Helpers =================
    def _register_alias(self, alias: Optional[str], canonical: str) -> None:
        if not alias or not canonical:
            return
        key = alias.replace(".json", "").lower()
        if not key:
            return
        self.alias_map.setdefault(key, canonical)

    def _register_numeric_aliases(self, canonical: str) -> None:
        if "_" not in canonical:
            return
        prefix, suffix = canonical.split("_", 1)
        if not suffix:
            return
        numeric = None
        if suffix.isdigit():
            numeric = int(suffix)
        else:
            try:
                numeric = int(suffix.rstrip("abcdefghijklmnopqrstuvwxyz"))
            except ValueError:
                numeric = None
        if numeric is None:
            return

        padded = f"{numeric:02d}"
        variants = {
            f"{prefix}_{suffix}",
            f"{prefix}_{padded}",
            f"flagship_{suffix}",
            f"flagship_{padded}",
            f"flagship_{numeric}",
            f"level_{suffix}",
            f"level_{padded}",
            f"level_{numeric}",
        }
        for variant in variants:
            self._register_alias(variant, canonical)

    def _sorted_flagship_levels(self) -> List[str]:
        flagship_ids = [key for key, src in self.level_sources.items() if src == "flagship"]
        return self._sort_levels(flagship_ids)

    @staticmethod
    def _sort_levels(level_ids: List[str]) -> List[str]:
        def sort_key(level_id: str) -> Tuple[str, int, int, str]:
            prefix, _, suffix = level_id.partition("_")
            if suffix.isdigit():
                return (prefix, 0, int(suffix), level_id)
            return (prefix, 1, 0, level_id)

        return sorted(level_ids, key=sort_key)

    def get_start_level(self) -> Optional[str]:
        continuity_roots: List[str] = []
        for key, payload in self.levels.items():
            continuity = payload.get("continuity") or {}
            previous = continuity.get("previous")
            if previous in (None, "", "null"):
                continuity_roots.append(key)

        if "flagship_tutorial" in continuity_roots:
            return "flagship_tutorial"
        if continuity_roots:
            ordered_roots = self._sort_levels(continuity_roots)
            if ordered_roots:
                return ordered_roots[0]

        flagship = self._sorted_flagship_levels()
        if flagship:
            return flagship[0]
        if self.levels:
            remaining = self._sort_levels(list(self.levels.keys()))
            return remaining[0] if remaining else None
        return None