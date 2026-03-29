/**
 * Graph fixture built from repo `sentiment-tree/` JSON (Polymarket + event scrapes).
 * Categories: root, descendant, branch, newBranch, prediction — see groupColors / predictionLayout.
 */

import polymarketData from "@sentiment-tree/polymarket_preds.json";
import eventsData from "@sentiment-tree/events_example.json";

export const SAMPLE_TODAY = "2025-03-28T12:00:00Z";
export const NEW_BRANCH_DAYS = 7;

function fmtVol(n) {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}k`;
  return String(n);
}

function shortQuestion(q, max = 78) {
  if (!q || q.length <= max) return q;
  return `${q.slice(0, max - 1)}…`;
}

function buildDescendants(events) {
  const evs = Array.isArray(events) ? [...events].sort((a, b) => a.ID - b.ID) : [];
  const timestamps = ["2024-06-15T12:00:00Z", "2025-02-10T12:00:00Z"];
  return evs.map((ev, i) => {
    const src = ev.Sources?.[0];
    const summary = [ev.Description, src?.Summary].filter(Boolean).join(" — ");
    return {
      id: `desc-${i + 1}`,
      data: {
        label: ev.Title,
        category: "descendant",
        sentiment: 0.42 + i * 0.06,
        source: "news",
        timestamp: timestamps[i] ?? timestamps[timestamps.length - 1],
        summary: summary || ev.Title,
      },
    };
  });
}

function buildPredictionNodes(preds) {
  return preds.map((p) => ({
    id: p.id,
    data: {
      label: shortQuestion(p.question, 80),
      category: "prediction",
      sentiment: p.yes_probability,
      source: p.source === "kalshi" ? "kalshi" : "polymarket",
      timestamp: p.closes_at,
      summary: `${p.category} · Yes ${(p.yes_probability * 100).toFixed(0)}% · Vol $${fmtVol(p.volume_usd)} · Liq $${fmtVol(p.liquidity_usd)}`,
    },
  }));
}

function buildBranchLayer(preds) {
  const byCat = (cat) => preds.find((p) => p.category === cat);
  const military = byCat("military");
  const diplomatic = preds.find((p) => p.category === "diplomatic");
  const economic = preds.find((p) => p.category === "economic");

  const branches = [
    {
      id: "branch-1",
      label: military ? shortQuestion(military.question, 72) : "Military scenario",
      sentiment: military?.yes_probability ?? 0.4,
      timestamp: "2025-01-08T14:00:00Z",
    },
    {
      id: "branch-2",
      label: diplomatic ? shortQuestion(diplomatic.question, 72) : "Diplomatic scenario",
      sentiment: diplomatic?.yes_probability ?? 0.35,
      timestamp: "2025-02-03T11:00:00Z",
    },
    {
      id: "branch-3",
      label: economic ? shortQuestion(economic.question, 72) : "Economic scenario",
      sentiment: economic?.yes_probability ?? 0.3,
      timestamp: "2025-02-19T09:30:00Z",
    },
  ];

  const nbA = preds.find((p) => p.id === "pm_006");
  const nbB = preds.find((p) => p.id === "pm_001");
  const newBranches = [
    {
      id: "newbranch-1",
      label: nbA ? shortQuestion(nbA.question, 72) : "Near-term policy",
      sentiment: nbA?.yes_probability ?? 0.55,
      timestamp: "2025-03-22T08:30:00Z",
    },
    {
      id: "newbranch-2",
      label: nbB ? shortQuestion(nbB.question, 72) : "Summer risk window",
      sentiment: nbB?.yes_probability ?? 0.4,
      timestamp: "2025-03-26T15:00:00Z",
    },
  ];

  const toNode = (b, cat) => ({
    id: b.id,
    data: {
      label: b.label,
      category: cat,
      sentiment: b.sentiment,
      source: "news",
      timestamp: b.timestamp,
      summary: `Narrative branch aligned with query “${polymarketData.query}”.`,
    },
  });

  return {
    branches: branches.map((b) => toNode(b, "branch")),
    newBranches: newBranches.map((b) => toNode(b, "newBranch")),
  };
}

function buildEdges(descendants) {
  const edges = [];
  for (let i = 0; i < descendants.length - 1; i++) {
    const a = descendants[i].id;
    const b = descendants[i + 1].id;
    edges.push({ id: `e-${a}-${b}`, source: a, target: b });
  }
  if (descendants.length > 0) {
    const last = descendants[descendants.length - 1].id;
    edges.push({ id: `e-${last}-root`, source: last, target: "root" });
  }

  const branchIds = ["branch-1", "branch-2", "branch-3", "newbranch-1", "newbranch-2"];
  for (const bid of branchIds) {
    edges.push({ id: `e-root-${bid}`, source: "root", target: bid });
  }
  edges.push({ id: "e-b1-nb1", source: "branch-1", target: "newbranch-1" });
  return edges;
}

const preds = polymarketData.predictions ?? [];
const descendants = buildDescendants(eventsData);
const { branches, newBranches } = buildBranchLayer(preds);

const rootNode = {
  id: "root",
  data: {
    label: polymarketData.query,
    category: "root",
    sentiment: 0.5,
    source: "search",
    timestamp: polymarketData.fetched_at,
    summary: `Live search focus — ${preds.length} Polymarket/Kalshi contracts linked (fetched ${polymarketData.fetched_at.slice(0, 10)}).`,
  },
};

const predictionNodes = buildPredictionNodes(preds);

const sampleNodes = [
  ...descendants,
  rootNode,
  ...branches,
  ...newBranches,
  ...predictionNodes,
];

const sampleEdges = buildEdges(descendants);

export { sampleNodes, sampleEdges };
