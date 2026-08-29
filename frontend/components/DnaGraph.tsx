"use client";

import { useEffect, useMemo, useRef } from "react";
import ReactFlow, { Background, Controls, Edge, Node, Position, ReactFlowProvider, useReactFlow } from "reactflow";
import "reactflow/dist/style.css";
import { GraphEdge, GraphNode, SessionGraph, Verdict } from "@/lib/types";

const VERDICT_COLOR: Record<Verdict, string> = {
  VERIFIED_ORIGIN: "#34d399",
  DERIVED: "#fbbf24",
  NO_RECORD: "#6b7280",
};

const BADGE_ICON: Record<string, string> = {
  whatsapp: "💬",
  android: "📱",
  camera: "📸",
  "ai-generator": "✨",
  "screen-capture": "🖥️",
  "export-tool": "🖼️",
  pdf: "📄",
};

function layout(nodes: GraphNode[], edges: GraphEdge[]) {
  const childrenOf = new Map<string, string[]>();
  const hasParent = new Set<string>();
  for (const e of edges) {
    childrenOf.set(e.source, [...(childrenOf.get(e.source) ?? []), e.target]);
    hasParent.add(e.target);
  }
  const roots = nodes.filter((n) => !hasParent.has(n.id));
  const positions = new Map<string, { x: number; y: number }>();
  const levelWidth = new Map<number, number>();
  const HGAP = 240;
  const VGAP = 140;

  function place(id: string, depth: number) {
    const x = (levelWidth.get(depth) ?? 0) * HGAP;
    levelWidth.set(depth, (levelWidth.get(depth) ?? 0) + 1);
    positions.set(id, { x, y: depth * VGAP });
    for (const child of childrenOf.get(id) ?? []) {
      if (!positions.has(child)) place(child, depth + 1);
    }
  }

  const visited = new Set<string>();
  for (const r of roots.length ? roots : nodes) {
    if (!visited.has(r.id)) {
      place(r.id, 0);
      visited.add(r.id);
    }
  }
  // Any nodes not reached (shouldn't happen, but stay defensive)
  for (const n of nodes) {
    if (!positions.has(n.id)) place(n.id, 0);
  }
  return positions;
}

export default function DnaGraph(props: { graph: SessionGraph; selectedId: string | null; onSelect: (id: string) => void }) {
  if (props.graph.nodes.length === 0) {
    return (
      <div className="flex h-[260px] items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted">
        Upload a file to start the Content DNA Graph.
      </div>
    );
  }
  return (
    <ReactFlowProvider>
      <DnaGraphInner {...props} />
    </ReactFlowProvider>
  );
}

function DnaGraphInner({
  graph,
  selectedId,
  onSelect,
}: {
  graph: SessionGraph;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const { fitView } = useReactFlow();

  const { nodes, edges } = useMemo(() => {
    const positions = layout(graph.nodes, graph.edges);

    const rfNodes: Node[] = graph.nodes.map((n) => {
      const pos = positions.get(n.id) ?? { x: 0, y: 0 };
      const color = VERDICT_COLOR[n.verdict];
      const isSelected = n.id === selectedId;
      return {
        id: n.id,
        position: pos,
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
        data: {
          label: (
            <div className="text-left">
              <div className="flex items-center gap-1 text-[13px]">
                {n.badges.map((b) => (
                  <span key={b}>{BADGE_ICON[b] ?? ""}</span>
                ))}
                <span className="truncate max-w-[140px] font-medium">{n.filename}</span>
              </div>
              <div className="mt-0.5 text-[10px] opacity-70">Trace {n.trace_score}/100</div>
            </div>
          ),
        },
        style: {
          background: "#12161f",
          border: `2px solid ${isSelected ? "#6ea8fe" : color}`,
          borderRadius: 10,
          padding: "8px 12px",
          color: "#e6e9f0",
          width: 190,
          boxShadow: isSelected ? "0 0 0 3px #6ea8fe33" : "none",
        },
      };
    });

    const rfEdges: Edge[] = graph.edges.map((e, i) => ({
      id: `${e.source}-${e.target}-${i}`,
      source: e.source,
      target: e.target,
      label: e.label,
      animated: true,
      style: { stroke: "#3a4256" },
      labelStyle: { fill: "#9fb0d0", fontSize: 10 },
      labelBgStyle: { fill: "#12161f" },
    }));

    return { nodes: rfNodes, edges: rfEdges };
  }, [graph, selectedId]);

  const nodeIds = nodes.map((n) => n.id).join(",");
  const mountedRef = useRef(false);
  useEffect(() => {
    // The `fitView` prop below handles the very first mount correctly —
    // React Flow waits for node dimensions to be measured before fitting.
    // Calling the imperative fitView() that early races that measurement
    // and can compute bounds against unmeasured (zero-size) nodes. So
    // this effect only re-fits on SUBSEQUENT node-set changes (a new
    // upload added to an already-mounted graph).
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    const id = requestAnimationFrame(() => fitView({ padding: 0.2, duration: 300 }));
    return () => cancelAnimationFrame(id);
  }, [nodeIds, fitView]);

  return (
    <div className="h-[420px] overflow-hidden rounded-xl border border-border bg-panel">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={(_, node) => onSelect(node.id)}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
      >
        <Background color="#1c2230" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
