import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCollide,
  forceX,
  forceY,
} from "d3-force";

/**
 * Runs a d3-force simulation and returns a map of { [nodeId]: { x, y } }.
 *
 * Layout strategy:
 *   x-axis → time   (earliest node left, latest right)
 *   y-axis → sentiment  (1 = top / bullish, 0 = bottom / bearish)
 *   Forces nudge nodes apart so labels don't overlap while respecting
 *   the time + sentiment anchors.
 */
export default function forceLayout(nodes, edges, width = 1400, height = 800) {
  const PADDING = 80;

  const timestamps = nodes.map((n) => new Date(n.data.timestamp).getTime());
  const tMin = Math.min(...timestamps);
  const tMax = Math.max(...timestamps);
  const tRange = tMax - tMin || 1;

  const simNodes = nodes.map((n) => {
    const t = new Date(n.data.timestamp).getTime();
    return {
      id: n.id,
      // anchor positions based on time (x) and sentiment (y)
      tx: PADDING + ((t - tMin) / tRange) * (width - PADDING * 2),
      ty: PADDING + (1 - n.data.sentiment) * (height - PADDING * 2),
      x: PADDING + ((t - tMin) / tRange) * (width - PADDING * 2),
      y: PADDING + (1 - n.data.sentiment) * (height - PADDING * 2),
    };
  });

  const simEdges = edges.map((e) => ({
    source: e.source,
    target: e.target,
  }));

  const simulation = forceSimulation(simNodes)
    .force(
      "link",
      forceLink(simEdges)
        .id((d) => d.id)
        .distance(120)
        .strength(0.3)
    )
    .force("charge", forceManyBody().strength(-200))
    .force("collide", forceCollide(50))
    .force(
      "x",
      forceX((d) => d.tx).strength(0.7)
    )
    .force(
      "y",
      forceY((d) => d.ty).strength(0.7)
    )
    .stop();

  // run synchronously for a fixed number of ticks
  const TICKS = 120;
  for (let i = 0; i < TICKS; i++) simulation.tick();

  const positions = {};
  for (const n of simNodes) {
    positions[n.id] = { x: n.x, y: n.y };
  }
  return positions;
}
