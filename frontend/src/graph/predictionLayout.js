export const PREDICTION_SEMICIRCLE = {
  margin: 72,
  /** Base radius for 1 node; grows by radiusPerNode for each additional node. */
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

/** Ids pinned to static arcs (not draggable): descendants + predictions + root. */
export function getPinnedLayoutNodeIds(graphNodes) {
  return [
    ...getDescendantNodeIds(graphNodes),
    ...getPredictionNodeIds(graphNodes),
    "root",
  ];
}

/**
 * Pins the root node to the canvas center.
 */
export function applyRootPin(simNodes, width, height) {
  const sn = simNodes.find((s) => s.id === "root");
  if (!sn) return;
  sn.x = width / 2;
  sn.y = height / 2;
  sn.fx = width / 2;
  sn.fy = height / 2;
  sn.vx = 0;
  sn.vy = 0;
}

/**
 * Places prediction nodes on an upper semicircle (−y, top of screen).
 * Radius expands as more nodes are added.
 *
 * Center: (width/2, margin + radius).
 * Angles (π + ε, 2π − ε) → upper half, bulge toward smaller y.
 */
export function applyPredictionSemiCirclePins(simNodes, graphNodes, width, height) {
  const ids = getPredictionNodeIds(graphNodes);
  const byId = new Map(simNodes.map((s) => [s.id, s]));
  const { margin, baseRadius, radiusPerNode, angleEps } = PREDICTION_SEMICIRCLE;

  const n = ids.length;
  const radius = baseRadius + Math.max(0, n - 1) * radiusPerNode;

  const cx = width / 2;
  const cy = margin + radius;
  const start = Math.PI + angleEps;
  const end = 2 * Math.PI - angleEps;

  for (let i = 0; i < n; i++) {
    const sn = byId.get(ids[i]);
    if (!sn) continue;

    const theta =
      n === 1
        ? (3 * Math.PI) / 2
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

/**
 * Places descendant nodes on a lower semicircle (+y, bottom of screen).
 *
 * Center: (width/2, height − margin − radius).
 * Angles (ε, π − ε) → lower half, bulge toward larger y.
 */
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
