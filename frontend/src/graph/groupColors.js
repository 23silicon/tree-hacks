/** Semantic node categories for Sentimentree (see claude.md). */
const nodeCategoryColors = {
  /** Initial question/event — all forward branches start here */
  root: {
    bg: "#f5efe2",
    glow: "rgba(245,239,226,0.42)",
    text: "#21170d",
    edge: "rgba(245,239,226,0.28)",
  },
  /** Past events (scraped) — default branch timeline */
  branch: {
    bg: "#f59e0b",
    glow: "rgba(245,158,11,0.34)",
    text: "#3b2204",
    edge: "rgba(245,158,11,0.32)",
  },
  event: {
    bg: "#f97316",
    glow: "rgba(249,115,22,0.34)",
    text: "#431407",
    edge: "rgba(249,115,22,0.3)",
  },
  /** Recent branch events (within N days of “today”) — slightly darker green than prediction */
  newBranch: {
    bg: "#2dd4bf",
    glow: "rgba(45,212,191,0.34)",
    text: "#072f2a",
    edge: "rgba(45,212,191,0.32)",
  },
  /** Future / not yet occurred — prediction-market or scheduled outcomes */
  prediction: {
    bg: "#38bdf8",
    glow: "rgba(56,189,248,0.34)",
    text: "#062133",
    edge: "rgba(56,189,248,0.34)",
  },
  /** Historical timeline leading up to the root (special past chain) */
  descendant: {
    bg: "#8b9fb5",
    glow: "rgba(139,159,181,0.32)",
    text: "#1e293b",
    edge: "rgba(139,159,181,0.28)",
  },
};

export function colorsFor(category) {
  return nodeCategoryColors[category] ?? nodeCategoryColors.branch;
}

export default nodeCategoryColors;
