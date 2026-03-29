import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCollide,
  forceX,
  forceY,
} from "d3-force";
import {
  getEventLaneTargets,
  getPredictionSemicircleTargets,
  PREDICTION_SEMICIRCLE_FORCE_STRENGTH,
  getPredictionArcRadiusPx,
} from "./predictionLayout";

export const LINK_DISTANCE = 140;
export const LINK_DRAG_DISTANCE_FACTOR = 1.12;
export const LINK_REST_STRENGTH = 0.9;
export const LINK_DRAG_STRENGTH = 0.55;
/** Weaker springs on edges touching a prediction — semicircle anchor forces win. */
export const LINK_STRENGTH_PRED_EDGE = 0.22;
export const LINK_DRAG_STRENGTH_PRED_EDGE = 0.14;

function linkStrengthAccessor(predIdSet, mode) {
  return (link) => {
    const s = typeof link.source === "object" ? link.source.id : link.source;
    const t = typeof link.target === "object" ? link.target.id : link.target;
    const touchesPred = predIdSet.has(s) || predIdSet.has(t);
    if (mode === "drag") {
      return touchesPred ? LINK_DRAG_STRENGTH_PRED_EDGE : LINK_DRAG_STRENGTH;
    }
    return touchesPred ? LINK_STRENGTH_PRED_EDGE : LINK_REST_STRENGTH;
  };
}

export function setLinkPhysics(simulation, mode, predIdSet) {
  const link = simulation.force("link");
  if (!link) return;
  if (mode === "drag") {
    link.distance(LINK_DISTANCE * LINK_DRAG_DISTANCE_FACTOR);
  } else {
    link.distance(LINK_DISTANCE);
  }
  if (predIdSet && predIdSet.size > 0) {
    link.strength(linkStrengthAccessor(predIdSet, mode));
  } else {
    link.strength(mode === "drag" ? LINK_DRAG_STRENGTH : LINK_REST_STRENGTH);
  }
}

export function createLayout(
  graphNodes,
  graphEdges,
  width,
  height,
  layoutParamsRef
) {
  const cx = width / 2;
  const cy = height / 2;

  const radiusPx = () =>
    getPredictionArcRadiusPx(
      graphNodes,
      layoutParamsRef?.current?.arcSlider
    );
  const predTargetsInitial = getPredictionSemicircleTargets(
    graphNodes,
    cx,
    cy,
    radiusPx()
  );
  const eventTargetsInitial = getEventLaneTargets(graphNodes, width, height);
  const predIdSet = new Set(predTargetsInitial.keys());

  const simNodes = graphNodes.map((node) => {
    const cat = node.data?.category ?? "event";
    let x;
    let y;

    if (node.id === "root") {
      x = cx;
      y = cy;
    } else if (cat === "event") {
      const target = eventTargetsInitial.get(node.id) ?? { x: cx, y: cy + 120 };
      x = target.x;
      y = target.y;
    } else if (cat === "prediction") {
      const p = predTargetsInitial.get(node.id);
      x = p.x;
      y = p.y;
    } else {
      x = cx;
      y = cy;
    }

    return { id: node.id, category: cat, x, y, vx: 0, vy: 0 };
  });

  const rootSn = simNodes.find((s) => s.id === "root");
  if (rootSn) {
    rootSn.fx = cx;
    rootSn.fy = cy;
    rootSn.x = cx;
    rootSn.y = cy;
  }

  const simLinks = graphEdges.map((e) => ({
    source: e.source,
    target: e.target,
  }));

  let predTargetCache = null;
  let predCacheRadius = null;
  let eventTargetCache = null;
  function predictionTargetXY(d) {
    if (!predIdSet.has(d.id)) return { x: d.x, y: d.y };
    const r = radiusPx();
    if (predCacheRadius !== r || !predTargetCache) {
      predTargetCache = getPredictionSemicircleTargets(
        graphNodes,
        cx,
        cy,
        r
      );
      predCacheRadius = r;
    }
    return predTargetCache.get(d.id) ?? { x: d.x, y: d.y };
  }
  function eventTargetXY(d) {
    if (d.category !== "event") return { x: d.x, y: d.y };
    if (!eventTargetCache) {
      eventTargetCache = getEventLaneTargets(graphNodes, width, height);
    }
    return eventTargetCache.get(d.id) ?? { x: d.x, y: d.y };
  }

  const simulation = forceSimulation(simNodes)
    .force(
      "link",
      forceLink(simLinks)
        .id((d) => d.id)
        .distance(LINK_DISTANCE)
        .strength(linkStrengthAccessor(predIdSet, "rest"))
    )
    .force("charge", forceManyBody().strength(-500))
    .force("collide", forceCollide((d) => (d.category === "prediction" ? 70 : 56)))
    .force(
      "eventX",
      forceX((d) => eventTargetXY(d).x).strength((d) =>
        d.category === "event" ? 0.3 : 0
      )
    )
    .force(
      "eventY",
      forceY((d) => eventTargetXY(d).y).strength((d) =>
        d.category === "event" ? 0.36 : 0
      )
    )
    .force(
      "predX",
      forceX((d) => predictionTargetXY(d).x).strength((d) =>
        predIdSet.has(d.id) ? PREDICTION_SEMICIRCLE_FORCE_STRENGTH : 0
      )
    )
    .force(
      "predY",
      forceY((d) => predictionTargetXY(d).y).strength((d) =>
        predIdSet.has(d.id) ? PREDICTION_SEMICIRCLE_FORCE_STRENGTH : 0
      )
    )
    .velocityDecay(0.55)
    .alphaDecay(0.022);

  return { simulation, simNodes, predIdSet };
}

/** Re-run after arc slider changes — d3 forceX/Y snapshot targets at initialize(). */
export function refreshPredictionAnchorForces(simulation, simNodes) {
  const predX = simulation.force("predX");
  const predY = simulation.force("predY");
  const eventX = simulation.force("eventX");
  const eventY = simulation.force("eventY");
  if (predX?.initialize) predX.initialize(simNodes);
  if (predY?.initialize) predY.initialize(simNodes);
  if (eventX?.initialize) eventX.initialize(simNodes);
  if (eventY?.initialize) eventY.initialize(simNodes);
}

export function settleSimulation(simulation, maxTicks = 500) {
  let ticks = 0;
  simulation.alpha(1);
  while (simulation.alpha() > 0.001 && ticks < maxTicks) {
    simulation.tick();
    ticks++;
  }
}
