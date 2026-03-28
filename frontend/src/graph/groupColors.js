/** Semantic node categories for SentimentTree (see claude.md). */
const nodeCategoryColors = {
  /** Initial question/event — all forward branches start here */
  root: {
    bg: "#ffffff",
    glow: "rgba(255,255,255,0.55)",
    text: "#111111",
    edge: "rgba(255,255,255,0.28)",
  },
  /** Past events (scraped) — default branch timeline */
  branch: {
    bg: "#c4b5d4",
    glow: "rgba(196,181,212,0.45)",
    text: "#3d3550",
    edge: "rgba(196,181,212,0.35)",
  },
  /** Recent branch events (within N days of “today”) — slightly darker green than prediction */
  newBranch: {
    bg: "#6dd3a0",
    glow: "rgba(109,211,160,0.48)",
    text: "#14532d",
    edge: "rgba(109,211,160,0.38)",
  },
  /** Future / not yet occurred — prediction-market or scheduled outcomes */
  prediction: {
    bg: "#86efac",
    glow: "rgba(134,239,172,0.55)",
    text: "#14532d",
    edge: "rgba(134,239,172,0.4)",
  },
  /** Historical timeline leading up to the root (special past chain) */
  descendant: {
    bg: "#94a3b8",
    glow: "rgba(148,163,184,0.4)",
    text: "#1e293b",
    edge: "rgba(148,163,184,0.3)",
  },
};

export function colorsFor(category) {
  return nodeCategoryColors[category] ?? nodeCategoryColors.branch;
}

export default nodeCategoryColors;
