"use client";

import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  type Edge,
  type Node,
} from "reactflow";

type NarrativeMapClientProps = {
  playerId: string;
  graphPayload: Record<string, unknown> | null;
  worldPayload: Record<string, unknown> | null;
  graphOk: boolean;
  graphError: string | null;
  worldOk: boolean;
  worldError: string | null;
};

type ParsedGraphNode = {
  id: string;
  arc: string;
  requires: string[];
  next: string[];
};

type ParsedGraphEdge = {
  from: string;
  to: string;
};

function asObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function parseGraphNodes(graphPayload: Record<string, unknown> | null): ParsedGraphNode[] {
  const rows = asArray(graphPayload?.nodes);
  const parsed: ParsedGraphNode[] = [];

  for (const row of rows) {
    const map = asObject(row);
    const id = asString(map?.id);
    if (!id) {
      continue;
    }

    const requires = asArray(map?.requires)
      .map(asString)
      .filter(Boolean);

    const next = asArray(map?.next)
      .map(asString)
      .filter(Boolean);

    parsed.push({
      id,
      arc: asString(map?.arc) || "main",
      requires,
      next,
    });
  }

  return parsed;
}

function parseGraphEdges(
  graphPayload: Record<string, unknown> | null,
  parsedNodes: ParsedGraphNode[],
): ParsedGraphEdge[] {
  const rows = asArray(graphPayload?.edges);
  const parsed: ParsedGraphEdge[] = [];

  for (const row of rows) {
    const map = asObject(row);
    const from = asString(map?.from);
    const to = asString(map?.to);
    if (!from || !to) {
      continue;
    }
    parsed.push({ from, to });
  }

  if (parsed.length > 0) {
    return parsed;
  }

  for (const node of parsedNodes) {
    for (const target of node.next) {
      parsed.push({ from: node.id, to: target });
    }
  }

  return parsed;
}

function parseNarrativeRuntime(worldPayload: Record<string, unknown> | null): {
  currentNode: string;
  blockedBy: string[];
  candidateByNode: Map<string, { blockedBy: string[]; satisfied: boolean }>;
} {
  const narrativeState = asObject(worldPayload?.narrative_state);

  const currentNode =
    asString(worldPayload?.current_node) ||
    asString(narrativeState?.current_node);

  const blockedBy = asArray(worldPayload?.blocked_by ?? narrativeState?.blocked_by)
    .map(asString)
    .filter(Boolean);

  const transitionCandidates = asArray(
    worldPayload?.transition_candidates ?? narrativeState?.transition_candidates,
  );

  const candidateByNode = new Map<string, { blockedBy: string[]; satisfied: boolean }>();

  for (const row of transitionCandidates) {
    const map = asObject(row);
    const node = asString(map?.node);
    if (!node) {
      continue;
    }

    const rowBlockedBy = asArray(map?.blocked_by)
      .map(asString)
      .filter(Boolean);

    candidateByNode.set(node, {
      blockedBy: rowBlockedBy,
      satisfied: Boolean(map?.satisfied),
    });
  }

  return {
    currentNode,
    blockedBy,
    candidateByNode,
  };
}

export default function NarrativeMapClient({
  playerId,
  graphPayload,
  worldPayload,
  graphOk,
  graphError,
  worldOk,
  worldError,
}: NarrativeMapClientProps) {
  const parsedNodes = parseGraphNodes(graphPayload);
  const parsedEdges = parseGraphEdges(graphPayload, parsedNodes);
  const runtime = parseNarrativeRuntime(worldPayload);

  const flowNodes: Node[] = parsedNodes.map((node, index) => {
    const candidateState = runtime.candidateByNode.get(node.id);
    const isCurrent = runtime.currentNode === node.id;
    const isCandidate = Boolean(candidateState);
    const isBlocked = isCandidate && (candidateState?.blockedBy.length ?? 0) > 0;

    const statusText = isCurrent
      ? "current"
      : isBlocked
        ? "blocked"
        : isCandidate
          ? "candidate"
          : "idle";

    return {
      id: node.id,
      position: { x: 120, y: 80 + index * 140 },
      draggable: false,
      data: {
        label: (
          <div className="min-w-[180px] text-xs leading-5">
            <div className="font-semibold">{node.id}</div>
            <div>arc: {node.arc}</div>
            <div>status: {statusText}</div>
            {node.requires.length > 0 && (
              <div>requires: {node.requires.join(", ")}</div>
            )}
          </div>
        ),
      },
      style: {
        border: "1px solid var(--foreground)",
        borderWidth: isCurrent ? 3 : isCandidate ? 2 : 1,
        borderStyle: isBlocked ? "dashed" : "solid",
        borderRadius: 12,
        background: "var(--background)",
        color: "var(--foreground)",
        opacity: isBlocked ? 0.75 : 1,
        padding: 8,
      },
    };
  });

  const flowEdges: Edge[] = parsedEdges.map((edge) => {
    const targetCandidate = runtime.candidateByNode.get(edge.to);
    const isBlocked = (targetCandidate?.blockedBy.length ?? 0) > 0;

    return {
      id: `${edge.from}->${edge.to}`,
      source: edge.from,
      target: edge.to,
      animated: runtime.currentNode === edge.from,
      style: {
        strokeWidth: 2,
        strokeDasharray: isBlocked ? "5 5" : undefined,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
      },
    };
  });

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
      <section className="rounded-xl border border-black/10 p-4 dark:border-white/20">
        <h2 className="mb-3 text-sm font-semibold">Narrative Graph</h2>
        <div className="h-[62vh] min-h-[460px] rounded-lg border border-black/10 dark:border-white/20">
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            fitView
            nodesConnectable={false}
            nodesDraggable={false}
            elementsSelectable={false}
            panOnDrag
            zoomOnScroll
          >
            <Background />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <article className="rounded-xl border border-black/10 p-4 text-sm dark:border-white/20">
          <h3 className="font-semibold">Runtime Overlay</h3>
          <p className="mt-2">player_id: {playerId}</p>
          <p>current_node: {runtime.currentNode || "(empty)"}</p>
          <p>candidate_count: {runtime.candidateByNode.size}</p>
          <p>blocked_by_count: {runtime.blockedBy.length}</p>
        </article>

        <article className="rounded-xl border border-black/10 p-4 text-sm dark:border-white/20">
          <h3 className="font-semibold">Blocked Requirements</h3>
          {runtime.blockedBy.length === 0 ? (
            <p className="mt-2 opacity-80">(none)</p>
          ) : (
            <ul className="mt-2 space-y-1">
              {runtime.blockedBy.map((token) => (
                <li key={token}>- {token}</li>
              ))}
            </ul>
          )}
        </article>

        {(!graphOk || !worldOk) && (
          <article className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm">
            <h3 className="font-semibold">Backend Warning</h3>
            {!graphOk && <p className="mt-2">graph: {graphError || "request failed"}</p>}
            {!worldOk && <p className="mt-2">world: {worldError || "request failed"}</p>}
          </article>
        )}
      </section>
    </div>
  );
}
