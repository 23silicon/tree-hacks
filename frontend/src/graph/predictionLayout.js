export const PREDICTION_SEMICIRCLE = {
  baseRadius: 220,
  radiusPerNode: 18,
  angleEps: 0.06,
  arcCoverage: 0.9,
  gapCenterRad: Math.PI / 2,
};

export const PRED_ARC_BASE_PX = 220;
export const PRED_ARC_PER_EVENT_PX = 20;
export const PRED_ARC_INNER_MULT = 0.84;
export const PRED_ARC_OUTER_MULT = 1.26;
export const PREDICTION_SEMICIRCLE_FORCE_STRENGTH = 0.62;

function buildArcTargets(ids, originX, originY, radiusPx) {
  const { baseRadius, radiusPerNode, angleEps, arcCoverage, gapCenterRad } =
    PREDICTION_SEMICIRCLE;

  const n = ids.length;
  const radius =
    typeof radiusPx === "number" && radiusPx > 0
      ? radiusPx
      : baseRadius + Math.max(0, n - 1) * radiusPerNode;

  const gap = (1 - arcCoverage) * 2 * Math.PI;
  const sweep = arcCoverage * 2 * Math.PI;
  const start = gapCenterRad + gap / 2;
  const end = start + sweep;
  const t0 = start + angleEps;
  const t1 = end - angleEps;

  const map = new Map();
  for (let i = 0; i < n; i += 1) {
    const theta =
      n === 1 ? (t0 + t1) / 2 : t0 + (i / (n - 1)) * (t1 - t0);

    map.set(ids[i], {
      x: originX + radius * Math.cos(theta),
      y: originY + radius * Math.sin(theta),
    });
  }
  return map;
}

function averagePositions(points, fallback) {
  if (!Array.isArray(points) || points.length === 0) {
    return fallback;
  }
  const total = points.reduce(
    (acc, point) => ({
      x: acc.x + point.x,
      y: acc.y + point.y,
    }),
    { x: 0, y: 0 }
  );
  return {
    x: total.x / points.length,
    y: total.y / points.length,
  };
}

export function getPredictionNodeIds(graphNodes) {
  return graphNodes
    .filter((node) => node.data?.category === "prediction")
    .map((node) => node.id);
}

export function getEventNodeIds(graphNodes) {
  return graphNodes
    .filter((node) => node.data?.category === "event")
    .map((node) => node.id);
}

export function getSortedEventIds(graphNodes) {
  return graphNodes
    .filter((node) => node.data?.category === "event")
    .sort(
      (a, b) =>
        new Date(a.data.timestamp).getTime() -
        new Date(b.data.timestamp).getTime()
    )
    .map((node) => node.id);
}

export function getSortedDescendantIds(graphNodes) {
  return getSortedEventIds(graphNodes);
}

export function getEventLaneKeys(graphNodes) {
  const keys = [];
  const seen = new Set();
  for (const node of graphNodes) {
    if (node.data?.category !== "event") continue;
    const key = node.data?.stackKey || "general";
    if (seen.has(key)) continue;
    seen.add(key);
    keys.push(key);
  }
  return keys;
}

export function getBranchRevealWaves(graphNodes) {
  const eventIds = getSortedEventIds(graphNodes);
  return eventIds.length > 0 ? [eventIds] : [];
}

export function getBranchNodeCount(graphNodes) {
  return Math.max(getEventLaneKeys(graphNodes).length, 1);
}

export function getPredictionArcRadiusPx(graphNodes, arcSlider01) {
  const eventCount = Math.max(getEventNodeIds(graphNodes).length, 3);
  const mid = PRED_ARC_BASE_PX + eventCount * PRED_ARC_PER_EVENT_PX;
  const rMin = mid * PRED_ARC_INNER_MULT;
  const rMax = mid * PRED_ARC_OUTER_MULT;
  const t =
    typeof arcSlider01 === "number" && !Number.isNaN(arcSlider01)
      ? Math.min(1, Math.max(0, arcSlider01))
      : 1;
  return rMin + t * (rMax - rMin);
}

export function getPredictionSemicircleTargets(
  graphNodes,
  originX,
  originY,
  radiusPx
) {
  const ids = getPredictionNodeIds(graphNodes);
  return buildArcTargets(ids, originX, originY, radiusPx);
}

export function getEventLaneTargets(graphNodes, width, height, radiusPx) {
  const events = graphNodes
    .filter((node) => node.data?.category === "event")
    .sort(
      (a, b) =>
        new Date(a.data.timestamp).getTime() -
        new Date(b.data.timestamp).getTime()
    );
  const cx = width / 2;
  const cy = height / 2;
  const predictionRadius = getPredictionArcRadiusPx(graphNodes, 1);
  const effectivePredictionRadius =
    typeof radiusPx === "number" && radiusPx > 0
      ? radiusPx
      : predictionRadius;
  const predictionTargets = getPredictionSemicircleTargets(
    graphNodes,
    cx,
    cy,
    effectivePredictionRadius
  );
  const predictionIds = [...predictionTargets.keys()];

  const fallbackBranchKeys = [];
  const fallbackSeen = new Set();
  for (const event of events) {
    const supportIds = Array.isArray(event.data?.supportPredictionIds)
      ? event.data.supportPredictionIds.filter((id) => predictionTargets.has(id))
      : [];
    if (supportIds.length > 0) {
      continue;
    }
    const key = event.data?.stackKey || event.id;
    if (fallbackSeen.has(key)) {
      continue;
    }
    fallbackSeen.add(key);
    fallbackBranchKeys.push(key);
  }
  const fallbackTargets = buildArcTargets(
    fallbackBranchKeys,
    cx,
    cy,
    effectivePredictionRadius * 0.82
  );
  const minRadius = Math.max(92, Math.min(124, effectivePredictionRadius * 0.28));
  const maxRadius = Math.max(
    minRadius + 120,
    effectivePredictionRadius * 0.78
  );
  const radialStep =
    events.length > 1 ? (maxRadius - minRadius) / (events.length - 1) : 0;
  const branchCounts = new Map();

  const targets = new Map();
  events.forEach((event, index) => {
    const supportIds = Array.isArray(event.data?.supportPredictionIds)
      ? event.data.supportPredictionIds.filter((id) => predictionTargets.has(id))
      : [];
    const branchKey =
      supportIds.length > 0
        ? supportIds.join("|")
        : event.data?.stackKey || event.id;
    const branchOffset = branchCounts.get(branchKey) ?? 0;
    branchCounts.set(branchKey, branchOffset + 1);
    const branchTarget =
      supportIds.length > 0
        ? averagePositions(
            supportIds
              .map((id) => predictionTargets.get(id))
              .filter(Boolean),
            { x: cx, y: cy - effectivePredictionRadius * 0.75 }
          )
        : fallbackTargets.get(branchKey) ?? { x: cx, y: cy - effectivePredictionRadius * 0.72 };
    const dx = branchTarget.x - cx;
    const dy = branchTarget.y - cy;
    const magnitude = Math.hypot(dx, dy) || 1;
    const ux = dx / magnitude;
    const uy = dy / magnitude;
    const px = -uy;
    const py = ux;
    const distance = minRadius + index * radialStep;
    const lateralOffset =
      ((branchOffset % 3) - 1) * Math.min(20, 12 + branchOffset * 1.5);

    targets.set(event.id, {
      x: cx + ux * distance + px * lateralOffset,
      y: cy + uy * distance + py * lateralOffset,
    });
  });
  return targets;
}

export function applyPredictionSemiCirclePins(
  simNodes,
  graphNodes,
  width,
  height,
  radiusPx
) {
  const byId = new Map(simNodes.map((node) => [node.id, node]));
  const targets = getPredictionSemicircleTargets(
    graphNodes,
    width / 2,
    height / 2,
    radiusPx
  );

  for (const [id, pos] of targets) {
    const simNode = byId.get(id);
    if (!simNode) continue;
    simNode.x = pos.x;
    simNode.y = pos.y;
    simNode.fx = pos.x;
    simNode.fy = pos.y;
    simNode.vx = 0;
    simNode.vy = 0;
  }
}

export function applyEventLanePins(simNodes, graphNodes, width, height) {
  const byId = new Map(simNodes.map((node) => [node.id, node]));
  const targets = getEventLaneTargets(graphNodes, width, height);

  for (const [id, pos] of targets) {
    const simNode = byId.get(id);
    if (!simNode) continue;
    simNode.x = pos.x;
    simNode.y = pos.y;
    simNode.fx = pos.x;
    simNode.fy = pos.y;
    simNode.vx = 0;
    simNode.vy = 0;
  }
}

export function applyResetViewLayout(
  simNodes,
  graphNodes,
  width,
  height,
  predictionRadiusPx
) {
  applyPredictionSemiCirclePins(
    simNodes,
    graphNodes,
    width,
    height,
    predictionRadiusPx
  );
  applyEventLanePins(simNodes, graphNodes, width, height);

  const cx = width / 2;
  const cy = height / 2;
  for (const simNode of simNodes) {
    if (simNode.id === "root") {
      simNode.x = cx;
      simNode.y = cy;
      simNode.fx = cx;
      simNode.fy = cy;
      simNode.vx = 0;
      simNode.vy = 0;
    } else {
      simNode.fx = null;
      simNode.fy = null;
    }
  }
}
