import { useRef, useCallback, useMemo, useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
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
  getPredictionNodeIds,
} from "./predictionLayout";

const nodeTypes = { sentiment: SentimentNode };
const edgeTypes = { circleIntersect: CircleIntersectEdge };

const CANVAS_W = 1400;
const CANVAS_H = 800;

const ARC_SLIDER_MAX = 100;
const ARC_SLIDER_STEP = 2;

/** Reset-view: one visibility set — edges show when both ends are visible. */
const REVEAL_CHRONO_STEP_MS_SLOW = 340;

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

const allGraphNodeIds = new Set(sampleNodes.map((n) => n.id));

const nodeById = new Map(sampleNodes.map((n) => [n.id, n]));
const neighborsById = (() => {
  const map = new Map(sampleNodes.map((n) => [n.id, new Set()]));
  for (const e of sampleEdges) {
    map.get(e.source)?.add(e.target);
    map.get(e.target)?.add(e.source);
  }
  return map;
})();

function nodeTimeMs(id) {
  const ts = nodeById.get(id)?.data?.timestamp;
  if (!ts) return Number.POSITIVE_INFINITY;
  const t = new Date(ts).getTime();
  return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
}

function chronologicalRevealIds() {
  return sampleNodes
    .filter((n) => n.id !== "root")
    .sort((a, b) => {
      const dt = nodeTimeMs(a.id) - nodeTimeMs(b.id);
      if (dt !== 0) return dt;
      if (a.data?.category === "prediction" && b.data?.category !== "prediction") {
        return 1;
      }
      if (b.data?.category === "prediction" && a.data?.category !== "prediction") {
        return -1;
      }
      return String(a.id).localeCompare(String(b.id));
    })
    .map((n) => n.id);
}

function hash01FromString(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 4294967295;
}

function spawnOffsetFor(id, targetX, targetY, cx, cy) {
  const ux = targetX - cx;
  const uy = targetY - cy;
  const len = Math.hypot(ux, uy);
  const nx = len > 1e-5 ? ux / len : 1;
  const ny = len > 1e-5 ? uy / len : 0;
  const tx = -ny;
  const ty = nx;

  const hA = hash01FromString(`${id}-a`);
  const hB = hash01FromString(`${id}-b`);
  const radial = 180 + hA * 120;
  const tangent = (hB - 0.5) * 160;

  return {
    x: targetX + nx * radial + tx * tangent,
    y: targetY + ny * radial + ty * tangent,
  };
}

function kickTowardTarget(sn, target, intensity = 1) {
  const dx = target.x - sn.x;
  const dy = target.y - sn.y;
  sn.vx = dx * (0.012 * intensity);
  sn.vy = dy * (0.012 * intensity);
}

function buildFlowNodes(simNodes, revealedIds) {
  const cx = CANVAS_W / 2;
  const cy = CANVAS_H / 2;
  return sampleNodes.map((n) => {
    const sn = simNodes.find((s) => s.id === n.id);
    const revealed = revealedIds.has(n.id);
    const data = { ...n.data, reveal: revealed };
    if (n.data?.category === "prediction") {
      const dx = cx - sn.x;
      const dy = cy - sn.y;
      data.faceTowardCenterDeg =
        Math.hypot(dx, dy) > 1e-6
          ? (Math.atan2(dy, dx) * 180) / Math.PI - 90
          : 0;
    }
    return {
      id: n.id,
      type: "sentiment",
      position: { x: sn.x, y: sn.y },
      // Do not set `style.transform` on nodes — React Flow uses transform for
      // translate(x,y); overriding it stacks every node at the origin.
      data,
      draggable: true,
      style: {
        opacity: revealed ? 1 : 0,
        transition: "opacity 0.42s cubic-bezier(0.33, 1, 0.68, 1)",
        pointerEvents: revealed ? "auto" : "none",
      },
    };
  });
}

function ResetViewButton({ onResetLayout }) {
  return (
    <button
      type="button"
      onClick={() => {
        onResetLayout();
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

function buildFlowEdges(visibleIds) {
  return sampleEdges.map((e) => {
    const sourceNode = sampleNodes.find((n) => n.id === e.source);
    const targetNode = sampleNodes.find((n) => n.id === e.target);
    const c = colorsFor(sourceNode?.data?.category ?? "branch");
    const targetCategory = targetNode?.data?.category;
    const visible =
      visibleIds.has(e.source) && visibleIds.has(e.target);
    return {
      id: e.id,
      type: "circleIntersect",
      source: e.source,
      target: e.target,
      style: {
        stroke: c.edge,
        strokeWidth: 2,
        opacity: visible ? 1 : 0,
        transition: "opacity 0.48s ease",
      },
      animated: visible && targetCategory === "prediction",
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

  const initialNodes = useMemo(
    () => buildFlowNodes(simNodes, allGraphNodeIds),
    [simNodes]
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(
    buildFlowEdges(allGraphNodeIds)
  );

  const draggingRef = useRef(null);
  const rafRef = useRef(null);
  const reactFlowInstanceRef = useRef(null);
  const resetAnimGenRef = useRef(0);

  const applySimPositions = useCallback(
    (pinnedId) => {
      const cx = CANVAS_W / 2;
      const cy = CANVAS_H / 2;
      setNodes((prev) =>
        prev.map((n) => {
          if (n.id === pinnedId) return n;
          const sn = simNodes.find((s) => s.id === n.id);
          if (!sn) return n;
          if (n.data?.category === "prediction") {
            const dx = cx - sn.x;
            const dy = cy - sn.y;
            const deg =
              Math.hypot(dx, dy) > 1e-6
                ? (Math.atan2(dy, dx) * 180) / Math.PI - 90
                : 0;
            return {
              ...n,
              position: { x: sn.x, y: sn.y },
              data: { ...n.data, faceTowardCenterDeg: deg },
            };
          }
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

  const revealEverything = useCallback(() => {
    setNodes(buildFlowNodes(simNodes, allGraphNodeIds));
    setEdges(buildFlowEdges(allGraphNodeIds));
  }, [simNodes, setNodes, setEdges]);

  const onNodeDragStart = useCallback(
    (_event, node) => {
      resetAnimGenRef.current += 1;
      revealEverything();
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
    [simulation, simNodes, predIdSet, tickLoop, revealEverything]
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
    resetAnimGenRef.current += 1;
    const gen = resetAnimGenRef.current;

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

    const rootId = "root";
    const predIds = getPredictionNodeIds(sampleNodes);
    /** Nodes that are visible; any edge is shown iff both endpoints are in this set. */
    const visible = new Set([rootId, ...predIds]);
    const pendingLinkKick = new Set();
    const targetById = new Map(simNodes.map((sn) => [sn.id, { x: sn.x, y: sn.y }]));

    const flush = () => {
      setNodes(buildFlowNodes(simNodes, visible));
      setEdges(buildFlowEdges(visible));
    };

    flush();

    const rf = reactFlowInstanceRef.current;
    requestAnimationFrame(() => {
      rf?.fitView({ padding: 0.18, duration: 480 });
    });

    const wait = (ms) =>
      new Promise((resolve) => {
        setTimeout(resolve, ms);
      });

    const revealIds = chronologicalRevealIds().filter((id) => {
      const cat = nodeById.get(id)?.data?.category;
      return cat !== "prediction";
    });

    (async () => {
      await wait(120);
      if (gen !== resetAnimGenRef.current) return;

      for (const id of revealIds) {
        if (gen !== resetAnimGenRef.current) return;

        const sn = simNodes.find((s) => s.id === id);
        const target = targetById.get(id);
        if (!sn || !target) continue;

        const spawn = spawnOffsetFor(id, target.x, target.y, CANVAS_W / 2, CANVAS_H / 2);
        sn.x = spawn.x;
        sn.y = spawn.y;
        sn.fx = null;
        sn.fy = null;

        visible.add(id);

        const neighbors = neighborsById.get(id) ?? new Set();
        const hasVisibleNeighbor = [...neighbors].some((nid) => visible.has(nid));
        if (hasVisibleNeighbor) {
          kickTowardTarget(sn, target, 1.4);
        } else {
          pendingLinkKick.add(id);
        }

        for (const nid of neighbors) {
          if (!visible.has(nid) || !pendingLinkKick.has(nid)) continue;
          const peer = simNodes.find((s) => s.id === nid);
          const peerTarget = targetById.get(nid);
          if (!peer || !peerTarget) continue;
          kickTowardTarget(peer, peerTarget, 1.25);
          pendingLinkKick.delete(nid);
        }

        flush();
        simulation.alpha(Math.max(simulation.alpha(), 0.44));
        if (!rafRef.current) {
          rafRef.current = requestAnimationFrame(tickLoop);
        }

        await wait(REVEAL_CHRONO_STEP_MS_SLOW);
      }

      requestAnimationFrame(() => {
        if (gen !== resetAnimGenRef.current) return;
        reactFlowInstanceRef.current?.fitView({ padding: 0.18, duration: 520 });
      });
    })();
  }, [simulation, simNodes, predIdSet, setNodes, setEdges, tickLoop]);

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onInit={(instance) => {
          reactFlowInstanceRef.current = instance;
        }}
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
