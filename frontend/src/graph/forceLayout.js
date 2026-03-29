import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCollide,
  forceY,
} from "d3-force";

export const LINK_DISTANCE = 140;
export const LINK_DRAG_DISTANCE_FACTOR = 1.12;
export const LINK_REST_STRENGTH = 0.9;
export const LINK_DRAG_STRENGTH = 0.55;

export function setLinkPhysics(simulation, mode) {
  const link = simulation.force("link");
  if (!link) return;
  if (mode === "drag") {
    link.distance(LINK_DISTANCE * LINK_DRAG_DISTANCE_FACTOR);
    link.strength(LINK_DRAG_STRENGTH);
  } else {
    link.distance(LINK_DISTANCE);
    link.strength(LINK_REST_STRENGTH);
  }
}

/**
 * Creates the force simulation.
 *
 * Initial positions:
 *   root       → canvas center
 *   descendant → fan below root (increasing y)
 *   prediction → fan above root (decreasing y)
 *   branch / newBranch → scattered around center
 *
 * Persistent forces:
 *   descendants get a mild forceY pulling them toward cy + 200
 *   everything else: no positional anchor — fully free
 */
export function createLayout(graphNodes, graphEdges, width, height) {
  const cx = width / 2;
  const cy = height / 2;

  const descIds = graphNodes
    .filter((n) => n.data?.category === "descendant")
    .map((n) => n.id);
  const predIds = graphNodes
    .filter((n) => n.data?.category === "prediction")
    .map((n) => n.id);

  const simNodes = graphNodes.map((node) => {
    const cat = node.data?.category ?? "branch";
    let x, y;

    if (node.id === "root") {
      x = cx;
      y = cy;
    } else if (cat === "descendant") {
      const idx = descIds.indexOf(node.id);
      const total = descIds.length;
      const spread = Math.min(300, total * 80);
      x = cx + (total > 1 ? (idx / (total - 1) - 0.5) * spread : 0);
      y = cy + 160 + idx * 70;
    } else if (cat === "prediction") {
      const idx = predIds.indexOf(node.id);
      const total = predIds.length;
      const spread = Math.min(400, total * 90);
      x = cx + (total > 1 ? (idx / (total - 1) - 0.5) * spread : 0);
      y = cy - 200;
    } else {
      // branch / newBranch — orbit around center
      const count = graphNodes.filter(
        (n) => n.data?.category === "branch" || n.data?.category === "newBranch"
      ).length;
      const branchIds = graphNodes
        .filter(
          (n) =>
            n.data?.category === "branch" || n.data?.category === "newBranch"
        )
        .map((n) => n.id);
      const idx = branchIds.indexOf(node.id);
      const angle = (idx / Math.max(count, 1)) * 2 * Math.PI;
      const r = 160;
      x = cx + Math.cos(angle) * r;
      y = cy + Math.sin(angle) * r;
    }

    return { id: node.id, category: cat, x, y, vx: 0, vy: 0 };
  });

  const simLinks = graphEdges.map((e) => ({
    source: e.source,
    target: e.target,
  }));

  const simulation = forceSimulation(simNodes)
    .force(
      "link",
      forceLink(simLinks)
        .id((d) => d.id)
        .distance(LINK_DISTANCE)
        .strength(LINK_REST_STRENGTH)
    )
    .force("charge", forceManyBody().strength(-500))
    .force("collide", forceCollide(52))
    // mild downward pull for descendants keeps them naturally below root
    .force(
      "descendantY",
      forceY((d) => (d.category === "descendant" ? cy + 220 : cy)).strength(
        (d) => (d.category === "descendant" ? 0.12 : 0)
      )
    )
    .velocityDecay(0.55)
    .alphaDecay(0.022);

  return { simulation, simNodes };
}

export function settleSimulation(simulation, maxTicks = 500) {
  let ticks = 0;
  simulation.alpha(1);
  while (simulation.alpha() > 0.001 && ticks < maxTicks) {
    simulation.tick();
    ticks++;
  }
}
