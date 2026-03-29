import { useRef, useCallback, useMemo, useEffect } from "react";
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
import CircleIntersectEdge from "./CircleIntersectEdge";
import { sampleNodes, sampleEdges } from "./sampleGraph";
import { colorsFor } from "./groupColors";
import { createLayout, settleSimulation, setLinkPhysics } from "./forceLayout";

const nodeTypes = { sentiment: SentimentNode };
const edgeTypes = { circleIntersect: CircleIntersectEdge };

const CANVAS_W = 1400;
const CANVAS_H = 800;

function initSimulationBundle() {
  const bundle = createLayout(sampleNodes, sampleEdges, CANVAS_W, CANVAS_H);
  settleSimulation(bundle.simulation, 500);
  // release all fx/fy so every node is free after initial layout
  for (const sn of bundle.simNodes) {
    sn.fx = null;
    sn.fy = null;
  }
  return bundle;
}

function buildFlowNodes(simNodes) {
  return sampleNodes.map((n) => {
    const sn = simNodes.find((s) => s.id === n.id);
    return {
      id: n.id,
      type: "sentiment",
      position: { x: sn.x, y: sn.y },
      data: n.data,
      draggable: true,
    };
  });
}

function buildEdges() {
  return sampleEdges.map((e) => {
    const sourceNode = sampleNodes.find((n) => n.id === e.source);
    const targetNode = sampleNodes.find((n) => n.id === e.target);
    const c = colorsFor(sourceNode?.data?.category ?? "branch");
    const targetCategory = targetNode?.data?.category;
    return {
      id: e.id,
      type: "circleIntersect",
      source: e.source,
      target: e.target,
      style: { stroke: c.edge, strokeWidth: 2 },
      animated: targetCategory === "prediction",
    };
  });
}

export default function GraphCanvas() {
  const simBundleRef = useRef(null);
  if (simBundleRef.current === null) {
    simBundleRef.current = initSimulationBundle();
  }
  const { simulation, simNodes } = simBundleRef.current;

  const initialNodes = useMemo(() => buildFlowNodes(simNodes), [simNodes]);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(buildEdges());

  const draggingRef = useRef(null);
  const rafRef = useRef(null);

  const applySimPositions = useCallback(
    (pinnedId) => {
      setNodes((prev) =>
        prev.map((n) => {
          if (n.id === pinnedId) return n;
          const sn = simNodes.find((s) => s.id === n.id);
          if (!sn) return n;
          return { ...n, position: { x: sn.x, y: sn.y } };
        })
      );
    },
    [setNodes, simNodes]
  );

  const tickLoop = useCallback(() => {
    simulation.tick();
    applySimPositions(draggingRef.current);
    if (simulation.alpha() > 0.002) {
      rafRef.current = requestAnimationFrame(tickLoop);
    } else {
      rafRef.current = null;
      simulation.stop();
    }
  }, [simulation, applySimPositions]);

  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const onNodeDragStart = useCallback(
    (_event, node) => {
      draggingRef.current = node.id;
      const sn = simNodes.find((s) => s.id === node.id);
      if (sn) {
        sn.fx = node.position.x;
        sn.fy = node.position.y;
      }
      setLinkPhysics(simulation, "drag");
      simulation.alpha(0.4).restart();
      rafRef.current = requestAnimationFrame(tickLoop);
    },
    [simulation, simNodes, tickLoop]
  );

  const onNodeDrag = useCallback(
    (_event, node) => {
      const sn = simNodes.find((s) => s.id === node.id);
      if (sn) {
        sn.fx = node.position.x;
        sn.fy = node.position.y;
        sn.x = node.position.x;
        sn.y = node.position.y;
      }
      simulation.alpha(Math.max(simulation.alpha(), 0.3));
    },
    [simulation, simNodes]
  );

  const onNodeDragStop = useCallback(
    (_event, node) => {
      draggingRef.current = null;
      const sn = simNodes.find((s) => s.id === node.id);
      if (sn) {
        sn.fx = null;
        sn.fy = null;
      }
      setLinkPhysics(simulation, "rest");
      simulation.alpha(0.2);
      // RAF loop is already running — it will coast down via alphaDecay and stop itself
      if (!rafRef.current) {
        rafRef.current = requestAnimationFrame(tickLoop);
      }
    },
    [simulation, simNodes, tickLoop]
  );

  const miniMapColor = useCallback(
    (node) => colorsFor(node.data?.category).bg,
    []
  );

  return (
    <div style={{ width: "100vw", height: "100vh" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStart={onNodeDragStart}
        onNodeDrag={onNodeDrag}
        onNodeDragStop={onNodeDragStop}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesConnectable={false}
        connectOnClick={false}
        fitView
        minZoom={0.2}
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
