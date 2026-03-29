/**
 * Fixture graph using SentimentTree node categories:
 *   root        — question/event all forward branches start from
 *   branch      — past events (older than recent window)
 *   newBranch   — branch events within `newBranchDays` of reference “today”
 *   prediction  — future / not yet occurred
 *   descendant  — historical chain leading *to* the root (what led here)
 */

/** Reference “today” for demo (recent vs older branch split). */
export const SAMPLE_TODAY = "2026-03-28T12:00:00Z";
export const NEW_BRANCH_DAYS = 7;

const sampleNodes = [
  // ── Descendants: historical timeline → root ─────────────────────────
  {
    id: "desc-1",
    data: {
      label: "2022: Fed aggressive hiking cycle begins",
      category: "descendant",
      sentiment: 0.35,
      source: "news",
      timestamp: "2022-03-16T14:00:00Z",
      summary:
        "First 25bp hike — start of the fastest tightening in decades; sets baseline for later labor and inflation debates.",
    },
  },
  {
    id: "desc-2",
    data: {
      label: "2024: Soft landing narrative takes hold",
      category: "descendant",
      sentiment: 0.55,
      source: "news",
      timestamp: "2024-08-01T09:00:00Z",
      summary:
        "Disinflation without deep recession — consensus shifts; frames how markets read each subsequent jobs print.",
    },
  },
  {
    id: "desc-3",
    data: {
      label: "Early 2026: Labor market still tight",
      category: "descendant",
      sentiment: 0.48,
      source: "reddit",
      timestamp: "2026-02-01T12:00:00Z",
      summary:
        "Historical context immediately before the root question: job openings elevated, quit rate normalized.",
    },
  },

  // ── Root: question / event under exploration ─────────────────────────
  {
    id: "root",
    data: {
      label: "Will the US enter a recession before 2027?",
      category: "root",
      sentiment: 0.5,
      source: "search",
      timestamp: "2026-03-15T00:00:00Z",
      summary:
        "Root query — branches explore live discourse; descendants show what historically led to this framing.",
    },
  },

  // ── Branch nodes: older events (before recent window) ─────────────────
  {
    id: "branch-1",
    data: {
      label: "January CPI above expectations",
      category: "branch",
      sentiment: 0.32,
      source: "news",
      timestamp: "2026-01-14T08:30:00Z",
      summary:
        "Headline inflation sticky — branches the inflation narrative from the root.",
    },
  },
  {
    id: "branch-2",
    data: {
      label: "Q4 earnings: consumer resilient",
      category: "branch",
      sentiment: 0.68,
      source: "news",
      timestamp: "2026-02-10T16:00:00Z",
      summary:
        "Equities rally on guidance — older branch feeding the growth vs recession debate.",
    },
  },
  {
    id: "branch-3",
    data: {
      label: "Regional bank stress headlines",
      category: "branch",
      sentiment: 0.28,
      source: "twitter",
      timestamp: "2026-02-22T11:00:00Z",
      summary:
        "Credit concerns resurface — branch split toward financial stability worries.",
    },
  },

  // ── New branch nodes: within NEW_BRANCH_DAYS of SAMPLE_TODAY ──────────
  {
    id: "newbranch-1",
    data: {
      label: "March jobs report surprise",
      category: "newBranch",
      sentiment: 0.62,
      source: "news",
      timestamp: "2026-03-22T08:30:00Z",
      summary:
        "Strong payrolls — fresh branch activity; occurred within the recent window.",
    },
  },
  {
    id: "newbranch-2",
    data: {
      label: "Fed speakers lean hawkish",
      category: "newBranch",
      sentiment: 0.4,
      source: "twitter",
      timestamp: "2026-03-26T15:00:00Z",
      summary:
        "Last-moment narrative shift before “today” — tagged as new branch.",
    },
  },

  // ── Prediction nodes: future / not yet resolved ───────────────────────
  {
    id: "pred-1",
    data: {
      label: "FOMC decision (June 2026)",
      category: "prediction",
      sentiment: 0.52,
      source: "polymarket",
      timestamp: "2026-06-17T18:00:00Z",
      summary:
        "Scheduled outcome not yet realized — prediction node; market-implied path.",
    },
  },
  {
    id: "pred-2",
    data: {
      label: "Q3 GDP first print",
      category: "prediction",
      sentiment: 0.45,
      source: "polymarket",
      timestamp: "2026-10-29T12:00:00Z",
      summary:
        "Future data release — branches may converge on recession call here.",
    },
  },
  {
    id: "pred-3",
    data: {
      label: "Unemployment hits 5%?",
      category: "prediction",
      sentiment: 0.33,
      source: "kalshi",
      timestamp: "2026-08-14T12:00:00Z",
      summary:
        "Kalshi contract on U-3 unemployment crossing 5% before year-end — bearish labor signal.",
    },
  },
  {
    id: "pred-4",
    data: {
      label: "S&P 500 correction >15%",
      category: "prediction",
      sentiment: 0.28,
      source: "polymarket",
      timestamp: "2026-09-30T16:00:00Z",
      summary:
        "Polymarket contract on a peak-to-trough drawdown exceeding 15% before Q4 close.",
    },
  },
];

const sampleEdges = [
  // Historical chain → root
  { id: "e-desc1-desc2", source: "desc-1", target: "desc-2" },
  { id: "e-desc2-desc3", source: "desc-2", target: "desc-3" },
  { id: "e-desc3-root", source: "desc-3", target: "root" },

  // Root → branches (older)
  { id: "e-root-b1", source: "root", target: "branch-1" },
  { id: "e-root-b2", source: "root", target: "branch-2" },
  { id: "e-root-b3", source: "root", target: "branch-3" },

  // Root → recent branches
  { id: "e-root-nb1", source: "root", target: "newbranch-1" },
  { id: "e-root-nb2", source: "root", target: "newbranch-2" },

  // branch ↔ newBranch only (predictions are visually separate for now)
  { id: "e-b1-nb1", source: "branch-1", target: "newbranch-1" },
];

export { sampleNodes, sampleEdges };
