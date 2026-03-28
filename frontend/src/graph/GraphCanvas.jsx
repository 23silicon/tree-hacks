import { useMemo, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import SentimentNode from "./SentimentNode";
import { sampleNodes, sampleEdges } from "./sampleGraph";
import { colorsFor } from "./groupColors";
import forceLayout from "./forceLayout";

const nodeTypes = { sentiment: SentimentNode };

const CANVAS_W = 1400;
const CANVAS_H = 800;

function buildFlowData() {
  const positions = forceLayout(sampleNodes, sampleEdges, CANVAS_W, CANVAS_H);

  const nodes = sampleNodes.map((n) => ({
    id: n.id,
    type: "sentiment",
    position: positions[n.id],
    data: n.data,
  }));

  const edges = sampleEdges.map((e) => {
    const sourceNode = sampleNodes.find((n) => n.id === e.source);
    const targetNode = sampleNodes.find((n) => n.id === e.target);
    const c = colorsFor(sourceNode?.data?.category ?? "branch");
    const targetCategory = targetNode?.data?.category;
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      style: { stroke: c.edge, strokeWidth: 2 },
      animated: targetCategory === "prediction",
    };
  });

  return { nodes, edges };
}

export default function GraphCanvas() {
  const initial = useMemo(buildFlowData, []);
  const [nodes, , onNodesChange] = useNodesState(initial.nodes);
  const [edges, , onEdgesChange] = useEdgesState(initial.edges);

  const miniMapColor = useCallback((node) => {
    return colorsFor(node.data?.category).bg;
  }, []);

  return (
    <div style={{ width: "100vw", height: "100vh" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.3}
        maxZoom={2.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1e293b" gap={24} size={1} />
        <Controls
          position="bottom-right"
          style={{ background: "#1e1e2e", borderColor: "#334155" }}
        />
        <MiniMap
          nodeColor={miniMapColor}
          maskColor="rgba(0,0,0,0.7)"
          style={{ background: "#0f172a" }}
        />
      </ReactFlow>
    </div>
  );
}
