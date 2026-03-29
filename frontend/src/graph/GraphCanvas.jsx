import { useRef, useCallback, useMemo, useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import SentimentNode from "./SentimentNode";
import CircleIntersectEdge from "./CircleIntersectEdge";
import { sampleNodes, sampleEdges } from "./sampleGraph";
import { colorsFor } from "./groupColors";
import {
  createLayout,
  settleSimulation,
  setLinkPhysics,
  refreshPredictionAnchorForces,
} from "./forceLayout";
import {
  applyResetViewLayout,
  getBranchNodeCount,
  getPredictionArcRadiusPx,
} from "./predictionLayout";

const nodeTypes = { sentiment: SentimentNode };
const edgeTypes = { circleIntersect: CircleIntersectEdge };

const CANVAS_W = 1400;
const CANVAS_H = 800;

const ARC_SLIDER_MAX = 100;
const ARC_SLIDER_STEP = 2;

const ROOT_RETURN_RATE = 0.065;
const ROOT_HOME_EPS = 1.25;

function initSimulationBundle(layoutParamsRef) {
  const bundle = createLayout(
    sampleNodes,
    sampleEdges,
    CANVAS_W,
    CANVAS_H,
    layoutParamsRef
  );
  settleSimulation(bundle.simulation, 500);
  const cx = CANVAS_W / 2;
  const cy = CANVAS_H / 2;
  for (const sn of bundle.simNodes) {
    if (sn.id === "root") {
      sn.x = cx;
      sn.y = cy;
      sn.fx = cx;
      sn.fy = cy;
      sn.vx = 0;
      sn.vy = 0;
    } else {
      sn.fx = null;
      sn.fy = null;
    }
  }
  bundle.simulation.stop();
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

function ResetViewButton({ onResetLayout }) {
  const { fitView } = useReactFlow();
  return (
    <button
      type="button"
      onClick={() => {
        onResetLayout();
        fitView({ padding: 0.18, duration: 450 });
      }}
      style={{
        padding: "10px 16px",
        borderRadius: 8,
        border: "1px solid #334155",
        background: "#1e293b",
        color: "#e2e8f0",
        fontSize: 13,
        fontWeight: 600,
        cursor: "pointer",
        boxShadow: "0 4px 14px rgba(0,0,0,0.35)",
      }}
    >
      Reset view
    </button>
  );
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
  const branchCount = useMemo(() => getBranchNodeCount(sampleNodes), []);
  const layoutParamsRef = useRef({
    arcSlider: 1,
  });
  const [arcSliderPercent, setArcSliderPercent] = useState(ARC_SLIDER_MAX);

  const simBundleRef = useRef(null);
  if (simBundleRef.current === null) {
    simBundleRef.current = initSimulationBundle(layoutParamsRef);
  }
  const { simulation, simNodes, predIdSet } = simBundleRef.current;

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
    const cx = CANVAS_W / 2;
    const cy = CANVAS_H / 2;
    const root = simNodes.find((s) => s.id === "root");

    if (root) {
      if (draggingRef.current === "root") {
        simulation.alpha(Math.max(simulation.alpha(), 0.28));
      } else {
        const rx = root.fx ?? root.x;
        const ry = root.fy ?? root.y;
        const dist = Math.hypot(rx - cx, ry - cy);
        if (dist > ROOT_HOME_EPS) {
          if (root.fx == null || root.fy == null) {
            root.fx = root.x;
            root.fy = root.y;
          }
          root.fx += (cx - root.fx) * ROOT_RETURN_RATE;
          root.fy += (cy - root.fy) * ROOT_RETURN_RATE;
          root.x = root.fx;
          root.y = root.fy;
          root.vx = 0;
          root.vy = 0;
          simulation.alpha(Math.max(simulation.alpha(), 0.14));
        } else {
          root.fx = cx;
          root.fy = cy;
          root.x = cx;
          root.y = cy;
          root.vx = 0;
          root.vy = 0;
        }
      }
    }

    simulation.tick();

    applySimPositions(draggingRef.current);

    const rootReturning =
      root &&
      draggingRef.current !== "root" &&
      Math.hypot((root.fx ?? root.x) - cx, (root.fy ?? root.y) - cy) >
        ROOT_HOME_EPS;

    const keepGoing =
      simulation.alpha() > 0.002 ||
      rootReturning ||
      draggingRef.current === "root";

    if (keepGoing) {
      rafRef.current = requestAnimationFrame(tickLoop);
    } else {
      rafRef.current = null;
      simulation.stop();
    }
  }, [simulation, applySimPositions, simNodes]);

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
        sn.x = node.position.x;
        sn.y = node.position.y;
      }
      setLinkPhysics(simulation, "drag", predIdSet);
      simulation.alpha(Math.max(simulation.alpha(), 0.4));
      if (!rafRef.current) {
        rafRef.current = requestAnimationFrame(tickLoop);
      }
    },
    [simulation, simNodes, predIdSet, tickLoop]
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
      if (sn && node.id !== "root") {
        sn.fx = null;
        sn.fy = null;
      }
      setLinkPhysics(simulation, "rest", predIdSet);
      simulation.alpha(node.id === "root" ? 0.35 : 0.2);
      if (node.id === "root" && sn) {
        sn.fx = sn.x;
        sn.fy = sn.y;
      }
      if (!rafRef.current) {
        rafRef.current = requestAnimationFrame(tickLoop);
      }
    },
    [simulation, simNodes, predIdSet, tickLoop]
  );

  const miniMapColor = useCallback(
    (node) => colorsFor(node.data?.category).bg,
    []
  );

  const handleArcSliderChange = useCallback(
    (value) => {
      const pct = Number(value);
      const t = pct / ARC_SLIDER_MAX;
      layoutParamsRef.current.arcSlider = t;
      setArcSliderPercent(pct);
      refreshPredictionAnchorForces(simulation, simNodes);
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      simulation.alpha(0.55);
      rafRef.current = requestAnimationFrame(tickLoop);
    },
    [simulation, simNodes, tickLoop]
  );

  const displayArcRadiusPx = useMemo(
    () =>
      getPredictionArcRadiusPx(sampleNodes, arcSliderPercent / ARC_SLIDER_MAX),
    [arcSliderPercent]
  );

  const handleResetView = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    draggingRef.current = null;
    applyResetViewLayout(
      simNodes,
      sampleNodes,
      CANVAS_W,
      CANVAS_H,
      getPredictionArcRadiusPx(sampleNodes, layoutParamsRef.current.arcSlider)
    );
    refreshPredictionAnchorForces(simulation, simNodes);
    setLinkPhysics(simulation, "rest", predIdSet);
    simulation.alpha(1);
    settleSimulation(simulation, 500);
    simulation.stop();
    setNodes((prev) =>
      prev.map((n) => {
        const sn = simNodes.find((s) => s.id === n.id);
        if (!sn) return n;
        return { ...n, position: { x: sn.x, y: sn.y } };
      })
    );
  }, [simulation, simNodes, predIdSet, setNodes]);

  return (
    <div style={{ width: "100%", height: "100%" }}>
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
        <Panel position="bottom-left">
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 12,
              padding: 12,
              borderRadius: 10,
              border: "1px solid #334155",
              background: "rgba(15,23,42,0.92)",
              minWidth: 220,
            }}
          >
            <label
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 6,
                color: "#94a3b8",
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              Prediction arc · {branchCount}{" "}
              {branchCount === 1 ? "branch" : "branches"} (~
              {Math.round(displayArcRadiusPx)} px)
              <input
                type="range"
                min={0}
                max={ARC_SLIDER_MAX}
                step={ARC_SLIDER_STEP}
                value={arcSliderPercent}
                onChange={(e) => handleArcSliderChange(e.target.value)}
                style={{ width: "100%", accentColor: "#86efac" }}
              />
            </label>
            <ResetViewButton onResetLayout={handleResetView} />
          </div>
        </Panel>
      </ReactFlow>
    </div>
  );
}
