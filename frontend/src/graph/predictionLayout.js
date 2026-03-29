export const PREDICTION_SEMICIRCLE = {
  baseRadius: 180,
  radiusPerNode: 40,
  /** Padding at arc endpoints so nodes don’t sit on the gap (rad). */
  angleEps: 0.06,
  /** Portion of a full circle the predictions occupy (rest is open toward root). */
  arcCoverage: 0.9,
  /** Direction of gap center (rad); π/2 = screen-down = toward canvas center from top arc. */
  gapCenterRad: Math.PI / 2,
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

/**
 * Layers of branch/newBranch ids to reveal in parallel per layer. Uses only
 * edges between branch-category nodes (e.g. branch-1 → newbranch-1). Root→branch
 * edges are ignored here so nodes with no internal incoming appear in wave 0 together.
 */
export function getBranchRevealWaves(graphNodes, graphEdges) {
  const branchIds = new Set(
    graphNodes
      .filter(
        (n) =>
          n.data?.category === "branch" || n.data?.category === "newBranch"
      )
      .map((n) => n.id)
  );
  if (branchIds.size === 0) return [];

  const internalEdges = graphEdges.filter(
    (e) => branchIds.has(e.source) && branchIds.has(e.target)
  );

  const indeg = new Map();
  for (const id of branchIds) indeg.set(id, 0);
  for (const e of internalEdges) {
    indeg.set(e.target, (indeg.get(e.target) ?? 0) + 1);
  }

  const ts = (id) => {
    const n = graphNodes.find((x) => x.id === id);
    return n?.data?.timestamp
      ? new Date(n.data.timestamp).getTime()
      : 0;
  };

  const waves = [];
  const remaining = new Set(branchIds);

  while (remaining.size > 0) {
    const layer = [...remaining].filter((id) => indeg.get(id) === 0);
    if (layer.length === 0) break;
    layer.sort((a, b) => ts(a) - ts(b));
    waves.push(layer);

    for (const id of layer) {
      remaining.delete(id);
    }
    for (const id of layer) {
      for (const e of internalEdges) {
        if (e.source === id) {
          indeg.set(e.target, (indeg.get(e.target) ?? 0) - 1);
        }
      }
    }
  }

  return waves;
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
  const { baseRadius, radiusPerNode, angleEps, arcCoverage, gapCenterRad } =
    PREDICTION_SEMICIRCLE;

  const n = ids.length;
  const radius =
    typeof radiusPx === "number" && radiusPx > 0
      ? radiusPx
      : baseRadius + Math.max(0, n - 1) * radiusPerNode;

  const cx = originX;
  const cy = originY;

  const gap = (1 - arcCoverage) * 2 * Math.PI;
  const sweep = arcCoverage * 2 * Math.PI;
  const start = gapCenterRad + gap / 2;
  const end = start + sweep;
  const t0 = start + angleEps;
  const t1 = end - angleEps;

  const map = new Map();
  for (let i = 0; i < n; i++) {
    const theta =
      n === 1 ? (t0 + t1) / 2 : t0 + (i / (n - 1)) * (t1 - t0);

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
