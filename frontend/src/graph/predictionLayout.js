export const PREDICTION_SEMICIRCLE = {
  baseRadius: 180,
  radiusPerNode: 40,
  angleEps: 0.1,
};

export const DESCENDANT_SEMICIRCLE = {
  margin: 72,
  radius: 240,
  angleEps: 0.1,
};

export function getPredictionNodeIds(graphNodes) {
  return graphNodes
    .filter((n) => n.data?.category === "prediction")
    .map((n) => n.id);
}

export function getDescendantNodeIds(graphNodes) {
  return graphNodes
    .filter((n) => n.data?.category === "descendant")
    .map((n) => n.id);
}

/** Descendants in chronological order (oldest first) for reset-view reveal. */
export function getSortedDescendantIds(graphNodes) {
  return graphNodes
    .filter((n) => n.data?.category === "descendant")
    .sort(
      (a, b) =>
        new Date(a.data.timestamp).getTime() -
        new Date(b.data.timestamp).getTime()
    )
    .map((n) => n.id);
}

/** Branch + newBranch in chronological order for reset-view reveal (after descendants). */
export function getSortedBranchIds(graphNodes) {
  return graphNodes
    .filter(
      (n) =>
        n.data?.category === "branch" || n.data?.category === "newBranch"
    )
    .sort(
      (a, b) =>
        new Date(a.data.timestamp).getTime() -
        new Date(b.data.timestamp).getTime()
    )
    .map((n) => n.id);
}

export function getBranchNodeCount(graphNodes) {
  return graphNodes.filter(
    (n) =>
      n.data?.category === "branch" || n.data?.category === "newBranch"
  ).length;
}

export const PRED_ARC_BASE_PX = 185;
export const PRED_ARC_PER_BRANCH_PX = 36;
export const PRED_ARC_INNER_MULT = 0.52;
export const PRED_ARC_OUTER_MULT = 1.48;

export function getPredictionArcRadiusPx(graphNodes, arcSlider01) {
  const b = getBranchNodeCount(graphNodes);
  const mid = PRED_ARC_BASE_PX + Math.max(0, b) * PRED_ARC_PER_BRANCH_PX;
  const rMin = mid * PRED_ARC_INNER_MULT;
  const rMax = mid * PRED_ARC_OUTER_MULT;
  const t =
    typeof arcSlider01 === "number" && !Number.isNaN(arcSlider01)
      ? Math.min(1, Math.max(0, arcSlider01))
      : 1;
  return rMin + t * (rMax - rMin);
}

export const PREDICTION_SEMICIRCLE_FORCE_STRENGTH = 0.62;

export function getPredictionSemicircleTargets(
  graphNodes,
  originX,
  originY,
  radiusPx
) {
  const ids = getPredictionNodeIds(graphNodes);
  const { baseRadius, radiusPerNode, angleEps } = PREDICTION_SEMICIRCLE;

  const n = ids.length;
  const radius =
    typeof radiusPx === "number" && radiusPx > 0
      ? radiusPx
      : baseRadius + Math.max(0, n - 1) * radiusPerNode;

  const cx = originX;
  const cy = originY;
  const start = Math.PI + angleEps;
  const end = 2 * Math.PI - angleEps;

  const map = new Map();
  for (let i = 0; i < n; i++) {
    const theta =
      n === 1
        ? (3 * Math.PI) / 2
        : start + (i / (n - 1)) * (end - start);

    map.set(ids[i], {
      x: cx + radius * Math.cos(theta),
      y: cy + radius * Math.sin(theta),
    });
  }
  return map;
}

export function applyPredictionSemiCirclePins(
  simNodes,
  graphNodes,
  width,
  height,
  radiusPx
) {
  const byId = new Map(simNodes.map((s) => [s.id, s]));
  const ox = width / 2;
  const oy = height / 2;
  const targets = getPredictionSemicircleTargets(
    graphNodes,
    ox,
    oy,
    radiusPx
  );

  for (const [id, pos] of targets) {
    const sn = byId.get(id);
    if (!sn) continue;
    sn.x = pos.x;
    sn.y = pos.y;
    sn.fx = pos.x;
    sn.fy = pos.y;
    sn.vx = 0;
    sn.vy = 0;
  }
}

export function applyDescendantSemiCirclePins(simNodes, graphNodes, width, height) {
  const ids = getDescendantNodeIds(graphNodes);
  const byId = new Map(simNodes.map((s) => [s.id, s]));
  const { margin, radius, angleEps } = DESCENDANT_SEMICIRCLE;

  const n = ids.length;
  const cx = width / 2;
  const cy = height - margin - radius;
  const start = angleEps;
  const end = Math.PI - angleEps;

  for (let i = 0; i < n; i++) {
    const sn = byId.get(ids[i]);
    if (!sn) continue;

    const theta =
      n === 1
        ? Math.PI / 2
        : start + (i / (n - 1)) * (end - start);

    const x = cx + radius * Math.cos(theta);
    const y = cy + radius * Math.sin(theta);

    sn.x = x;
    sn.y = y;
    sn.fx = x;
    sn.fy = y;
    sn.vx = 0;
    sn.vy = 0;
  }
}

export function applyRootAndBranchRing(simNodes, graphNodes, width, height) {
  const cx = width / 2;
  const cy = height / 2;
  const root = simNodes.find((s) => s.id === "root");
  if (root) {
    root.x = cx;
    root.y = cy;
    root.vx = 0;
    root.vy = 0;
  }
  const branchIds = graphNodes
    .filter(
      (n) =>
        n.data?.category === "branch" || n.data?.category === "newBranch"
    )
    .map((n) => n.id);
  const count = branchIds.length;
  const r = 160;
  for (let idx = 0; idx < branchIds.length; idx++) {
    const sn = simNodes.find((s) => s.id === branchIds[idx]);
    if (!sn) continue;
    const angle = (idx / Math.max(count, 1)) * 2 * Math.PI;
    sn.x = cx + Math.cos(angle) * r;
    sn.y = cy + Math.sin(angle) * r;
    sn.vx = 0;
    sn.vy = 0;
  }
}

export function applyResetViewLayout(
  simNodes,
  graphNodes,
  width,
  height,
  predictionRadiusPx
) {
  applyRootAndBranchRing(simNodes, graphNodes, width, height);
  applyPredictionSemiCirclePins(
    simNodes,
    graphNodes,
    width,
    height,
    predictionRadiusPx
  );
  applyDescendantSemiCirclePins(simNodes, graphNodes, width, height);
  const cx = width / 2;
  const cy = height / 2;
  for (const sn of simNodes) {
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
}
