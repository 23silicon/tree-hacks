import { useRef, useCallback, useMemo, useEffect, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import SentimentNode from "./SentimentNode";
import CircleIntersectEdge from "./CircleIntersectEdge";
import { sampleNodes, sampleEdges } from "./sampleGraph";
import { colorsFor } from "./groupColors";
import {
  createLayout,
  settleSimulation,
  setLinkPhysics,
  refreshPredictionAnchorForces,
} from "./forceLayout";
import {
  applyResetViewLayout,
  getBranchNodeCount,
  getPredictionArcRadiusPx,
  getPredictionNodeIds,
  getPredictionSemicircleTargets,
  getEventLaneTargets,
  getSortedEventIds,
} from "./predictionLayout";

const nodeTypes = { sentiment: SentimentNode };
const edgeTypes = { circleIntersect: CircleIntersectEdge };

const CANVAS_W = 1400;
const CANVAS_H = 800;

const ARC_SLIDER_MAX = 100;
const ARC_SLIDER_STEP = 2;

/** Reset-view: one visibility set — edges show when both ends are visible. */
const REVEAL_DESCENDANT_STEP_MS = 300;
const ROOT_RETURN_RATE = 0.065;
const ROOT_HOME_EPS = 1.25;

function initSimulationBundle(graphNodes, graphEdges, layoutParamsRef) {
  const bundle = createLayout(
    graphNodes,
    graphEdges,
    CANVAS_W,
    CANVAS_H,
    layoutParamsRef
  );
  settleSimulation(bundle.simulation, 500);
  const cx = CANVAS_W / 2;
  const cy = CANVAS_H / 2;
  for (const sn of bundle.simNodes) {
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
  bundle.simulation.stop();
  return bundle;
}

function buildFlowNodes(
  graphNodes,
  simNodes,
  revealedIds,
  activePredictionId = null,
  activeEventIds = new Set(),
  positionOverrideMap = null
) {
  const cx = CANVAS_W / 2;
  const cy = CANVAS_H / 2;
  return graphNodes.map((n) => {
    const sn = simNodes.find((s) => s.id === n.id);
    const position = positionOverrideMap?.get(n.id) ?? {
      x: sn?.x ?? cx,
      y: sn?.y ?? cy,
    };
    const revealed = revealedIds.has(n.id);
    const category = n.data?.category;
    const inFocus =
      !activePredictionId ||
      n.id === "root" ||
      n.id === activePredictionId ||
      (category === "event" && activeEventIds.has(n.id));
    const data = { ...n.data, reveal: revealed };
    if (n.data?.category === "prediction") {
      const dx = cx - position.x;
      const dy = cy - position.y;
      data.faceTowardCenterDeg =
        Math.hypot(dx, dy) > 1e-6
          ? (Math.atan2(dy, dx) * 180) / Math.PI - 90
          : 0;
    }
    return {
      id: n.id,
      type: "sentiment",
      position,
      // Do not set `style.transform` on nodes — React Flow uses transform for
      // translate(x,y); overriding it stacks every node at the origin.
      data,
      draggable: true,
      style: {
        opacity: !revealed ? 0 : inFocus ? 1 : category === "prediction" ? 0.1 : 0.12,
        transition: "opacity 0.42s cubic-bezier(0.33, 1, 0.68, 1)",
        pointerEvents: revealed ? "auto" : "none",
      },
    };
  });
}

function ResetViewButton({ onResetLayout }) {
  return (
    <button
      type="button"
      onClick={() => {
        onResetLayout();
      }}
      style={{
        padding: "10px 16px",
        borderRadius: 8,
        border: "1px solid #334155",
        background: "#1e293b",
        color: "#e2e8f0",
        fontSize: 13,
        fontWeight: 600,
        cursor: "pointer",
        boxShadow: "0 4px 14px rgba(0,0,0,0.35)",
      }}
    >
      Reset view
    </button>
  );
}

function buildFlowEdges(
  graphNodes,
  graphEdges,
  visibleIds,
  activePredictionId = null,
  activeEventIds = new Set()
) {
  return graphEdges.map((e) => {
    const sourceNode = graphNodes.find((n) => n.id === e.source);
    const targetNode = graphNodes.find((n) => n.id === e.target);
    const c = colorsFor(sourceNode?.data?.category ?? "branch");
    const targetCategory = targetNode?.data?.category;
    const relation = e.relation ?? "timeline";
    const isSupportEdge = relation === "support";
    const isPredictionEdge =
      relation === "prediction" ||
      (sourceNode?.id === "root" && targetCategory === "prediction");
    const visible = visibleIds.has(e.source) && visibleIds.has(e.target);
    const focusedVisible = !activePredictionId
      ? visible
      : visible;
    const opacity = !visible
      ? 0
      : activePredictionId
        ? focusedVisible
          ? 1
          : isPredictionEdge
            ? 0.04
            : 0.06
        : isSupportEdge
          ? 0.54
          : isPredictionEdge
            ? 0.15
            : 0.94;
    return {
      id: e.id,
      type: "circleIntersect",
      source: e.source,
      target: e.target,
      style: {
        stroke: isSupportEdge
          ? "rgba(226,232,240,0.82)"
          : isPredictionEdge
            ? "rgba(148,163,184,0.72)"
            : c.edge,
        strokeWidth: isSupportEdge ? 2.5 : isPredictionEdge ? 1.8 : 2.2,
        strokeDasharray: isSupportEdge ? "6 6" : isPredictionEdge ? "3 10" : undefined,
        opacity,
        transition: "opacity 0.48s ease",
      },
      animated:
        focusedVisible &&
        (isSupportEdge || isPredictionEdge || targetCategory === "prediction"),
    };
  });
}

function buildFocusedTimelinePositions({
  graphNodes,
  orderedEventNodes,
  activeEventIds,
  selectedNodeCategory,
  selectedNodeId,
  predictionTargets,
  predictionRadiusPx,
}) {
  if (
    !selectedNodeId ||
    (selectedNodeCategory !== "prediction" && selectedNodeCategory !== "event")
  ) {
    return null;
  }

  const cx = CANVAS_W / 2;
  const cy = CANVAS_H / 2;
  const focusedEvents = orderedEventNodes.filter((node) => activeEventIds.has(node.id));
  const focusMap = new Map([["root", { x: cx, y: cy }]]);
  const eventTargets = getEventLaneTargets(
    graphNodes,
    CANVAS_W,
    CANVAS_H,
    predictionRadiusPx
  );

  let endPoint =
    selectedNodeCategory === "prediction"
      ? predictionTargets.get(selectedNodeId)
      : eventTargets.get(selectedNodeId);

  if (!endPoint) {
    endPoint = { x: cx, y: cy - Math.max(180, predictionRadiusPx * 0.55) };
  }

  let dx = endPoint.x - cx;
  let dy = endPoint.y - cy;
  const totalDistance = Math.hypot(dx, dy) || 1;
  if (totalDistance <= 1e-6) {
    dx = 0;
    dy = -1;
  }
  const ux = dx / (Math.hypot(dx, dy) || 1);
  const uy = dy / (Math.hypot(dx, dy) || 1);
  const terminalInset = selectedNodeCategory === "prediction" ? 108 : 36;
  const startOffset = 92;
  const maxEventDistance = Math.max(
    startOffset + 60,
    totalDistance - terminalInset
  );
  const segment = Math.max(90, maxEventDistance - startOffset);

  focusedEvents.forEach((node, index) => {
    const distance =
      startOffset + ((index + 1) / (focusedEvents.length + 1)) * segment;
    focusMap.set(node.id, {
      x: cx + ux * distance,
      y: cy + uy * distance,
    });
  });

  if (selectedNodeCategory === "prediction") {
    focusMap.set(selectedNodeId, endPoint);
  }

  return focusMap;
}

function formatPercent(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "n/a";
  }
  return `${Math.round(value * 100)}%`;
}

function formatCompactMetric(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "n/a";
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${Math.round(value / 1_000)}k`;
  }
  return `${Math.round(value)}`;
}

function formatTimestamp(timestamp) {
  if (!timestamp) {
    return "Unknown time";
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return timestamp;
  }
  return date.toLocaleString();
}

function tokenizeText(value) {
  return new Set(String(value || "").toLowerCase().match(/[a-z0-9]+/g) ?? []);
}

function rankRelatedPosts(posts, queryParts, limit = 5) {
  if (!Array.isArray(posts) || posts.length === 0) {
    return [];
  }

  const normalizedTerms = queryParts
    .map((item) => String(item || "").trim().toLowerCase())
    .filter(Boolean);

  if (normalizedTerms.length === 0) {
    return posts.slice(0, limit);
  }

  return posts
    .map((post) => {
      const haystack = `${post.text || ""} ${post.author || ""} ${post.source || ""}`.toLowerCase();
      const haystackTokens = tokenizeText(haystack);
      let score = 0;

      for (const term of normalizedTerms) {
        const termTokens = tokenizeText(term);
        const overlap = [...termTokens].filter((token) => haystackTokens.has(token)).length;
        if (overlap > 0) {
          score += overlap * 8;
        }
        if (term && haystack.includes(term)) {
          score += 14;
        }
      }

      return { post, score };
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((item) => item.post);
}

function buildRootSummary(payload, orderedEvents) {
  if (!Array.isArray(orderedEvents) || orderedEvents.length === 0) {
    return payload?.graph?.nodes?.find((node) => node.id === "root")?.data?.summary
      || "Collecting source-backed events for this topic.";
  }

  const firstEvent = orderedEvents[0];
  const latestEvent = orderedEvents[orderedEvents.length - 1];
  const totalSources = orderedEvents.reduce(
    (sum, event) => sum + (Number(event.source_count) || 0),
    0
  );

  return `${orderedEvents.length} source-backed events traced for ${payload?.query || "this topic"}. The chain starts with ${firstEvent.title} and currently runs through ${latestEvent.title}. ${totalSources} total source references are attached across the timeline.`;
}

function buildSelectedNodeDetails(payload, selectedNodeId, activeEventIds = new Set()) {
  if (!payload || !selectedNodeId) {
    return null;
  }

  const graphNodes = payload.graph?.nodes ?? [];
  const node = graphNodes.find((item) => item.id === selectedNodeId);
  if (!node) {
    return null;
  }

  const posts = Array.isArray(payload.sources?.posts) ? payload.sources.posts : [];
  const eventPredictionLinks = Array.isArray(payload.sources?.event_prediction_links)
    ? payload.sources.event_prediction_links
    : [];
  const predictions = Array.isArray(payload.sources?.predictions)
    ? payload.sources.predictions
    : [];
  const events = Array.isArray(payload.sources?.events) ? payload.sources.events : [];
  const category = node.data?.category ?? "branch";
  const orderedEvents = [...events].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );
  const activeEvents = orderedEvents.filter((event) => activeEventIds.has(event.id));
  const dedupedActivePosts = [];
  const seenPostKeys = new Set();
  for (const event of activeEvents) {
    const sources = Array.isArray(event.sources) ? event.sources : [];
    for (const source of sources) {
      const key = source.id || source.url || `${source.source}:${source.timestamp}:${source.text}`;
      if (!key || seenPostKeys.has(key)) {
        continue;
      }
      seenPostKeys.add(key);
      dedupedActivePosts.push(source);
      if (dedupedActivePosts.length >= 6) {
        break;
      }
    }
    if (dedupedActivePosts.length >= 6) {
      break;
    }
  }

  if (category === "prediction") {
    const prediction = predictions.find((item) => item.id === selectedNodeId);
    const relatedEvents = activeEvents.map((event) => {
      const link = eventPredictionLinks.find(
        (item) => item.event_id === event.id && item.prediction_id === selectedNodeId
      );
      return { ...event, link };
    });
    const relatedPosts =
      dedupedActivePosts.length > 0
        ? dedupedActivePosts
        : rankRelatedPosts(posts, [
            prediction?.question,
            prediction?.category,
            node.data?.label,
          ]);

    return {
      category,
      title: prediction?.question ?? node.data?.label,
      summary: node.data?.summary,
      externalUrl: prediction?.url,
      metrics: [
        { label: "Market", value: prediction?.source ?? node.data?.source },
        { label: "Category", value: prediction?.category ?? "general" },
        { label: "YES", value: formatPercent(prediction?.yes_probability) },
        { label: "NO", value: formatPercent(prediction?.no_probability) },
        { label: "Volume", value: `$${formatCompactMetric(prediction?.volume_usd)}` },
        { label: "Liquidity", value: `$${formatCompactMetric(prediction?.liquidity_usd)}` },
        { label: "Closes", value: formatTimestamp(prediction?.closes_at ?? node.data?.timestamp) },
        { label: "Linked events", value: `${relatedEvents.length}` },
      ],
      relatedPosts,
      relatedPredictions: [],
      relatedEvents,
    };
  }

  if (category === "event") {
    const event = events.find((item) => item.id === selectedNodeId);
    const relatedPosts =
      Array.isArray(event?.sources) && event.sources.length > 0
        ? event.sources
        : rankRelatedPosts(posts, [
            event?.title,
            event?.description,
            ...(event?.topic_tags ?? []),
            ...(event?.entities ?? []),
          ]);

    return {
      category,
      title: event?.title ?? node.data?.label,
      summary: event?.description ?? node.data?.summary,
      externalUrl: event?.url,
      metrics: [
        { label: "Source bundle", value: event?.source ?? node.data?.source },
        { label: "Backing sources", value: `${event?.source_count ?? relatedPosts.length}` },
        { label: "Stack", value: event?.stack_key ?? node.data?.stackKey ?? "general" },
        { label: "Time", value: formatTimestamp(event?.timestamp ?? node.data?.timestamp) },
        { label: "Scope", value: event?.time_scope ?? node.data?.timeScope ?? "current" },
        { label: "Sentiment", value: formatPercent(event?.sentiment_score ?? node.data?.sentiment) },
        {
          label: "Relevance",
          value:
            typeof event?.relevance_score === "number"
              ? formatPercent(event.relevance_score)
              : "n/a",
        },
      ],
      relatedPosts,
      relatedPredictions: predictions.filter((prediction) =>
        (event?.support_prediction_ids ?? []).includes(prediction.id)
      ),
      relatedEvents:
        activeEvents.length > 0
          ? activeEvents
          : event
            ? [event]
            : [],
    };
  }

  return {
    category,
    title: payload.query ?? node.data?.label,
    summary: buildRootSummary(payload, orderedEvents),
    externalUrl: null,
    metrics: [
      { label: "Sources", value: `${payload.summary?.posts ?? 0}` },
      { label: "Predictions", value: `${payload.summary?.predictions ?? 0}` },
      { label: "Events", value: `${payload.summary?.events ?? 0}` },
      { label: "Updated", value: formatTimestamp(payload.fetched_at ?? node.data?.timestamp) },
    ],
    relatedPosts:
      dedupedActivePosts.length > 0
        ? dedupedActivePosts
        : rankRelatedPosts(
            posts,
            [
              payload.query,
              ...orderedEvents.slice(0, 4).map((event) => event.title),
            ],
            8
          ),
    relatedPredictions: predictions.slice(0, 6),
    relatedEvents: activeEvents.length > 0 ? activeEvents : orderedEvents,
  };
}

function SidebarSection({ title, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "#94a3b8",
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

function DetailsSidebar({ details, onClose }) {
  if (!details) {
    return null;
  }

  const color = colorsFor(details.category);

  return (
    <div
      style={{
        position: "absolute",
        top: 18,
        right: 18,
        width: "min(360px, calc(100% - 36px))",
        maxHeight: "calc(100% - 36px)",
        overflowY: "auto",
        zIndex: 40,
        borderRadius: 22,
        border: `1px solid ${color.bg}33`,
        background:
          "linear-gradient(180deg, rgba(2,6,23,0.96), rgba(15,23,42,0.96))",
        boxShadow: "0 24px 60px rgba(2, 6, 23, 0.45)",
        padding: 18,
        display: "flex",
        flexDirection: "column",
        gap: 18,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: color.bg,
            }}
          >
            {details.category}
          </div>
          <div style={{ color: "#f8fafc", fontSize: 20, fontWeight: 700, lineHeight: 1.2 }}>
            {details.title}
          </div>
          <div style={{ color: "#94a3b8", fontSize: 13, lineHeight: 1.6 }}>
            {details.summary}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{
            border: "none",
            background: "rgba(148,163,184,0.12)",
            color: "#e2e8f0",
            width: 32,
            height: 32,
            borderRadius: 999,
            cursor: "pointer",
            fontSize: 16,
          }}
        >
          ×
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
          gap: 10,
        }}
      >
        {details.metrics.map((metric) => (
          <div
            key={`${metric.label}-${metric.value}`}
            style={{
              borderRadius: 14,
              border: "1px solid rgba(148,163,184,0.12)",
              background: "rgba(15,23,42,0.65)",
              padding: "10px 12px",
            }}
          >
            <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748b" }}>
              {metric.label}
            </div>
            <div style={{ marginTop: 4, color: "#f8fafc", fontSize: 13, fontWeight: 600, lineHeight: 1.4 }}>
              {metric.value}
            </div>
          </div>
        ))}
      </div>

      {details.externalUrl ? (
        <a
          href={details.externalUrl}
          target="_blank"
          rel="noreferrer"
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            borderRadius: 12,
            background: color.bg,
            color: "#020617",
            fontWeight: 700,
            textDecoration: "none",
            padding: "10px 14px",
          }}
        >
          Open source link
        </a>
      ) : null}

      {details.relatedPosts.length > 0 ? (
        <SidebarSection title="Related sources">
          {details.relatedPosts.map((post) => (
            <div
              key={post.id}
              style={{
                borderRadius: 16,
                border: "1px solid rgba(148,163,184,0.14)",
                background: "rgba(15,23,42,0.74)",
                padding: 14,
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <div style={{ color: "#cbd5e1", fontSize: 12, fontWeight: 600 }}>
                {post.author || post.source} · {formatTimestamp(post.timestamp)}
                {post.recency_tag ? ` · ${post.recency_tag}` : ""}
              </div>
              <div style={{ color: "#f8fafc", fontSize: 13, lineHeight: 1.55 }}>{post.text}</div>
              {post.url ? (
                <a
                  href={post.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: color.bg, fontSize: 12, fontWeight: 600, textDecoration: "none" }}
                >
                  View article
                </a>
              ) : null}
            </div>
          ))}
        </SidebarSection>
      ) : null}

      {details.relatedPredictions.length > 0 ? (
        <SidebarSection title="Linked markets">
          {details.relatedPredictions.map((prediction) => (
            <div
              key={prediction.id}
              style={{
                borderRadius: 16,
                border: "1px solid rgba(148,163,184,0.14)",
                background: "rgba(15,23,42,0.74)",
                padding: 14,
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <div style={{ color: "#f8fafc", fontSize: 13, fontWeight: 600, lineHeight: 1.5 }}>
                {prediction.question}
              </div>
              <div style={{ color: "#94a3b8", fontSize: 12 }}>
                {prediction.category || "general"} · YES {formatPercent(prediction.yes_probability)} · Vol $
                {formatCompactMetric(prediction.volume_usd)}
              </div>
            </div>
          ))}
        </SidebarSection>
      ) : null}

      {details.relatedEvents.length > 0 ? (
        <SidebarSection title="Timeline events">
          {details.relatedEvents.map((event) => (
            <div
              key={event.id}
              style={{
                borderRadius: 16,
                border: "1px solid rgba(148,163,184,0.14)",
                background: "rgba(15,23,42,0.74)",
                padding: 14,
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <div style={{ color: "#f8fafc", fontSize: 13, fontWeight: 600 }}>{event.title}</div>
              <div style={{ color: "#94a3b8", fontSize: 12 }}>
                {formatTimestamp(event.timestamp)}
                {event.time_scope ? ` · ${event.time_scope}` : ""}
                {typeof event.source_count === "number" ? ` · ${event.source_count} sources` : ""}
              </div>
              <div style={{ color: "#94a3b8", fontSize: 12 }}>{event.description}</div>
              {event.link?.reasoning ? (
                <div style={{ color: "#cbd5e1", fontSize: 12, lineHeight: 1.5 }}>
                  {event.link.reasoning}
                </div>
              ) : null}
            </div>
          ))}
        </SidebarSection>
      ) : null}
    </div>
  );
}

export default function GraphCanvas({ payload, selectedNodeId, onSelectNode }) {
  const graph = payload?.graph;
  const graphNodes = graph?.nodes?.length ? graph.nodes : sampleNodes;
  const graphEdges = Array.isArray(graph?.edges) ? graph.edges : sampleEdges;
  const supportEdges = Array.isArray(graph?.support_edges) ? graph.support_edges : [];
  const allGraphNodeIds = useMemo(
    () => new Set(graphNodes.map((node) => node.id)),
    [graphNodes]
  );
  const eventCount = useMemo(
    () => graphNodes.filter((node) => node.data?.category === "event").length,
    [graphNodes]
  );
  const branchCount = useMemo(() => getBranchNodeCount(graphNodes), [graphNodes]);
  const selectedNodeCategory = useMemo(() => {
    const selectedNode = graphNodes.find((node) => node.id === selectedNodeId);
    return selectedNode?.data?.category ?? null;
  }, [graphNodes, selectedNodeId]);
  const layoutParamsRef = useRef({
    arcSlider: 1,
  });
  const [arcSliderPercent, setArcSliderPercent] = useState(ARC_SLIDER_MAX);
  const activePredictionId = useMemo(() => {
    if (!selectedNodeCategory) {
      return null;
    }
    return selectedNodeId;
  }, [selectedNodeCategory, selectedNodeId]);
  const orderedEventNodes = useMemo(
    () =>
      graphNodes
        .filter((node) => node.data?.category === "event")
        .sort(
          (a, b) =>
            new Date(a.data.timestamp).getTime() -
            new Date(b.data.timestamp).getTime()
        ),
    [graphNodes]
  );
  const activeEventIds = useMemo(
    () => {
      if (!activePredictionId) {
        return new Set();
      }
      if (selectedNodeCategory === "prediction") {
        const directEventIds = graph?.prediction_event_map?.[activePredictionId] ?? [];
        if (directEventIds.length === 0) {
          return new Set();
        }
        const directIndexSet = new Set(
          directEventIds
            .map((eventId) =>
              orderedEventNodes.findIndex((node) => node.id === eventId)
            )
            .filter((index) => index >= 0)
        );
        if (directIndexSet.size === 0) {
          return new Set(directEventIds);
        }
        const maxIndex = Math.max(...directIndexSet);
        return new Set(
          orderedEventNodes
            .slice(0, maxIndex + 1)
            .map((node) => node.id)
        );
      }
      if (selectedNodeCategory === "event") {
        const selectedIndex = orderedEventNodes.findIndex(
          (node) => node.id === activePredictionId
        );
        if (selectedIndex === -1) {
          return new Set();
        }
        return new Set(
          orderedEventNodes.slice(0, selectedIndex + 1).map((node) => node.id)
        );
      }
      return new Set();
    },
    [graph, activePredictionId, orderedEventNodes, selectedNodeCategory]
  );
  const displayArcRadiusPx = useMemo(
    () =>
      getPredictionArcRadiusPx(graphNodes, arcSliderPercent / ARC_SLIDER_MAX),
    [graphNodes, arcSliderPercent]
  );
  const predictionTargets = useMemo(
    () =>
      getPredictionSemicircleTargets(
        graphNodes,
        CANVAS_W / 2,
        CANVAS_H / 2,
        displayArcRadiusPx
      ),
    [graphNodes, displayArcRadiusPx]
  );
  const focusedPositionMap = useMemo(
    () =>
      buildFocusedTimelinePositions({
        graphNodes,
        orderedEventNodes,
        activeEventIds,
        selectedNodeCategory,
        selectedNodeId,
        predictionTargets,
        predictionRadiusPx: displayArcRadiusPx,
      }),
    [
      activeEventIds,
      displayArcRadiusPx,
      graphNodes,
      orderedEventNodes,
      predictionTargets,
      selectedNodeCategory,
      selectedNodeId,
    ]
  );
  const displayGraphEdges = useMemo(() => {
    if (!activePredictionId) {
      return [...graphEdges, ...supportEdges];
    }

    const orderedFocusedEvents = orderedEventNodes.filter((node) =>
      activeEventIds.has(node.id)
    );

    const focusedEdges = [];
    if (orderedFocusedEvents.length > 0) {
      focusedEdges.push({
        id: `focus-root-${orderedFocusedEvents[0].id}`,
        source: "root",
        target: orderedFocusedEvents[0].id,
        relation: "timeline",
      });
    }
    for (let index = 0; index < orderedFocusedEvents.length - 1; index += 1) {
      focusedEdges.push({
        id: `focus-${orderedFocusedEvents[index].id}-${orderedFocusedEvents[index + 1].id}`,
        source: orderedFocusedEvents[index].id,
        target: orderedFocusedEvents[index + 1].id,
        relation: "timeline",
      });
    }
    if (selectedNodeCategory === "prediction") {
      const predictionParent =
        orderedFocusedEvents[orderedFocusedEvents.length - 1]?.id ?? "root";
      focusedEdges.push({
        id: `focus-${predictionParent}-${activePredictionId}`,
        source: predictionParent,
        target: activePredictionId,
        relation: "prediction",
      });
      return focusedEdges;
    }

    return focusedEdges;
  }, [
    activeEventIds,
    activePredictionId,
    graphEdges,
    orderedEventNodes,
    selectedNodeCategory,
    supportEdges,
  ]);

  const simBundleRef = useRef(null);
  if (simBundleRef.current === null) {
    simBundleRef.current = initSimulationBundle(
      graphNodes,
      graphEdges,
      layoutParamsRef
    );
  }
  const { simulation, simNodes, predIdSet } = simBundleRef.current;

  const initialNodes = useMemo(
    () =>
      buildFlowNodes(
        graphNodes,
        simNodes,
        allGraphNodeIds,
        activePredictionId,
        activeEventIds,
        focusedPositionMap
      ),
    [
      graphNodes,
      simNodes,
      allGraphNodeIds,
      activePredictionId,
      activeEventIds,
      focusedPositionMap,
    ]
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(
    buildFlowEdges(
      graphNodes,
      displayGraphEdges,
      allGraphNodeIds,
      activePredictionId,
      activeEventIds
    )
  );

  const draggingRef = useRef(null);
  const rafRef = useRef(null);
  const reactFlowInstanceRef = useRef(null);
  const resetAnimGenRef = useRef(0);

  const applySimPositions = useCallback(
    (pinnedId) => {
      const cx = CANVAS_W / 2;
      const cy = CANVAS_H / 2;
      setNodes((prev) =>
        prev.map((n) => {
          if (n.id === pinnedId) return n;
          const sn = simNodes.find((s) => s.id === n.id);
          const position = focusedPositionMap?.get(n.id) ?? (sn
            ? { x: sn.x, y: sn.y }
            : n.position);
          if (!position) return n;
          if (n.data?.category === "prediction") {
            const dx = cx - position.x;
            const dy = cy - position.y;
            const deg =
              Math.hypot(dx, dy) > 1e-6
                ? (Math.atan2(dy, dx) * 180) / Math.PI - 90
                : 0;
            return {
              ...n,
              position,
              data: { ...n.data, faceTowardCenterDeg: deg },
            };
          }
          return { ...n, position };
        })
      );
    },
    [focusedPositionMap, setNodes, simNodes]
  );

  const tickLoop = useCallback(() => {
    const cx = CANVAS_W / 2;
    const cy = CANVAS_H / 2;
    const root = simNodes.find((s) => s.id === "root");

    if (root) {
      if (draggingRef.current === "root") {
        simulation.alpha(Math.max(simulation.alpha(), 0.28));
      } else {
        const rx = root.fx ?? root.x;
        const ry = root.fy ?? root.y;
        const dist = Math.hypot(rx - cx, ry - cy);
        if (dist > ROOT_HOME_EPS) {
          if (root.fx == null || root.fy == null) {
            root.fx = root.x;
            root.fy = root.y;
          }
          root.fx += (cx - root.fx) * ROOT_RETURN_RATE;
          root.fy += (cy - root.fy) * ROOT_RETURN_RATE;
          root.x = root.fx;
          root.y = root.fy;
          root.vx = 0;
          root.vy = 0;
          simulation.alpha(Math.max(simulation.alpha(), 0.14));
        } else {
          root.fx = cx;
          root.fy = cy;
          root.x = cx;
          root.y = cy;
          root.vx = 0;
          root.vy = 0;
        }
      }
    }

    simulation.tick();

    applySimPositions(draggingRef.current);

    const rootReturning =
      root &&
      draggingRef.current !== "root" &&
      Math.hypot((root.fx ?? root.x) - cx, (root.fy ?? root.y) - cy) >
        ROOT_HOME_EPS;

    const keepGoing =
      simulation.alpha() > 0.002 ||
      rootReturning ||
      draggingRef.current === "root";

    if (keepGoing) {
      rafRef.current = requestAnimationFrame(tickLoop);
    } else {
      rafRef.current = null;
      simulation.stop();
    }
  }, [simulation, applySimPositions, simNodes]);

  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  useEffect(() => {
    setNodes(
      buildFlowNodes(
        graphNodes,
        simNodes,
        allGraphNodeIds,
        activePredictionId,
        activeEventIds,
        focusedPositionMap
      )
    );
    setEdges(
      buildFlowEdges(
        graphNodes,
        displayGraphEdges,
        allGraphNodeIds,
        activePredictionId,
        activeEventIds
      )
    );
  }, [
    graphNodes,
    simNodes,
    allGraphNodeIds,
    activePredictionId,
    activeEventIds,
    displayGraphEdges,
    focusedPositionMap,
    setNodes,
    setEdges,
  ]);

  const revealEverything = useCallback(() => {
    setNodes(
      buildFlowNodes(
        graphNodes,
        simNodes,
        allGraphNodeIds,
        activePredictionId,
        activeEventIds,
        focusedPositionMap
      )
    );
    setEdges(
      buildFlowEdges(
        graphNodes,
        displayGraphEdges,
        allGraphNodeIds,
        activePredictionId,
        activeEventIds
      )
    );
  }, [
    graphNodes,
    displayGraphEdges,
    simNodes,
    allGraphNodeIds,
    activePredictionId,
    activeEventIds,
    focusedPositionMap,
    setNodes,
    setEdges,
  ]);

  const onNodeDragStart = useCallback(
    (_event, node) => {
      resetAnimGenRef.current += 1;
      revealEverything();
      draggingRef.current = node.id;
      const sn = simNodes.find((s) => s.id === node.id);
      if (sn) {
        sn.fx = node.position.x;
        sn.fy = node.position.y;
        sn.x = node.position.x;
        sn.y = node.position.y;
      }
      setLinkPhysics(simulation, "drag", predIdSet);
      simulation.alpha(Math.max(simulation.alpha(), 0.4));
      if (!rafRef.current) {
        rafRef.current = requestAnimationFrame(tickLoop);
      }
    },
    [simulation, simNodes, predIdSet, tickLoop, revealEverything]
  );

  const onNodeDrag = useCallback(
    (_event, node) => {
      const sn = simNodes.find((s) => s.id === node.id);
      if (sn) {
        sn.fx = node.position.x;
        sn.fy = node.position.y;
        sn.x = node.position.x;
        sn.y = node.position.y;
      }
      simulation.alpha(Math.max(simulation.alpha(), 0.3));
    },
    [simulation, simNodes]
  );

  const onNodeDragStop = useCallback(
    (_event, node) => {
      draggingRef.current = null;
      const sn = simNodes.find((s) => s.id === node.id);
      if (sn && node.id !== "root") {
        sn.fx = null;
        sn.fy = null;
      }
      setLinkPhysics(simulation, "rest", predIdSet);
      simulation.alpha(node.id === "root" ? 0.35 : 0.2);
      if (node.id === "root" && sn) {
        sn.fx = sn.x;
        sn.fy = sn.y;
      }
      if (!rafRef.current) {
        rafRef.current = requestAnimationFrame(tickLoop);
      }
    },
    [simulation, simNodes, predIdSet, tickLoop]
  );

  const miniMapColor = useCallback(
    (node) => colorsFor(node.data?.category).bg,
    []
  );

  const handleArcSliderChange = useCallback(
    (value) => {
      const pct = Number(value);
      const t = pct / ARC_SLIDER_MAX;
      layoutParamsRef.current.arcSlider = t;
      setArcSliderPercent(pct);
      refreshPredictionAnchorForces(simulation, simNodes);
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      simulation.alpha(0.55);
      rafRef.current = requestAnimationFrame(tickLoop);
    },
    [simulation, simNodes, tickLoop]
  );

  const selectedDetails = useMemo(
    () => buildSelectedNodeDetails(payload, selectedNodeId, activeEventIds),
    [payload, selectedNodeId, activeEventIds]
  );

  useEffect(() => {
    if (!selectedNodeId) {
      return;
    }
    if (!allGraphNodeIds.has(selectedNodeId)) {
      onSelectNode?.(null);
    }
  }, [selectedNodeId, allGraphNodeIds, onSelectNode]);

  const handleResetView = useCallback(() => {
    resetAnimGenRef.current += 1;
    const gen = resetAnimGenRef.current;

    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    draggingRef.current = null;
    applyResetViewLayout(
      simNodes,
      graphNodes,
      CANVAS_W,
      CANVAS_H,
      getPredictionArcRadiusPx(graphNodes, layoutParamsRef.current.arcSlider)
    );
    refreshPredictionAnchorForces(simulation, simNodes);
    setLinkPhysics(simulation, "rest", predIdSet);
    simulation.alpha(1);
    settleSimulation(simulation, 500);
    simulation.stop();

    const rootId = "root";
    const predIds = getPredictionNodeIds(graphNodes);
    /** Nodes that are visible; any edge is shown iff both endpoints are in this set. */
    const visible = new Set([rootId, ...predIds]);

    const flush = () => {
      setNodes(
        buildFlowNodes(
          graphNodes,
          simNodes,
          visible,
          activePredictionId,
          activeEventIds,
          focusedPositionMap
        )
      );
      setEdges(
        buildFlowEdges(
          graphNodes,
          displayGraphEdges,
          visible,
          activePredictionId,
          activeEventIds
        )
      );
    };

    flush();

    const rf = reactFlowInstanceRef.current;
    requestAnimationFrame(() => {
      rf?.fitView({ padding: 0.18, duration: 480 });
    });

    const wait = (ms) =>
      new Promise((resolve) => {
        setTimeout(resolve, ms);
      });

    const eventIds = getSortedEventIds(graphNodes);

    (async () => {
      await wait(120);
      if (gen !== resetAnimGenRef.current) return;

      for (const id of eventIds) {
        if (gen !== resetAnimGenRef.current) return;
        visible.add(id);
        flush();
        await wait(REVEAL_DESCENDANT_STEP_MS);
        if (gen !== resetAnimGenRef.current) return;
      }

      requestAnimationFrame(() => {
        if (gen !== resetAnimGenRef.current) return;
        reactFlowInstanceRef.current?.fitView({ padding: 0.18, duration: 520 });
      });
    })();
  }, [
    graphNodes,
    simulation,
    simNodes,
    predIdSet,
    setNodes,
    setEdges,
    activePredictionId,
    activeEventIds,
    displayGraphEdges,
    focusedPositionMap,
  ]);

  return (
    <div style={{ width: "100%", height: "100%" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onInit={(instance) => {
          reactFlowInstanceRef.current = instance;
        }}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_event, node) => {
          onSelectNode?.(node.id);
        }}
        onNodeDragStart={onNodeDragStart}
        onNodeDrag={onNodeDrag}
        onNodeDragStop={onNodeDragStop}
        onPaneClick={() => {
          onSelectNode?.(null);
        }}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesConnectable={false}
        connectOnClick={false}
        fitView
        minZoom={0.2}
        maxZoom={2.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1e293b" gap={24} size={1} />
        <Controls
          position="bottom-right"
          style={{ background: "#1e1e2e", borderColor: "#334155" }}
        />
        <MiniMap
          nodeColor={miniMapColor}
          maskColor="rgba(0,0,0,0.7)"
          style={{ background: "#0f172a" }}
        />
        <Panel position="bottom-left">
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 12,
              padding: 12,
              borderRadius: 10,
              border: "1px solid #334155",
              background: "rgba(15,23,42,0.92)",
              minWidth: 220,
            }}
          >
            <label
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 6,
                color: "#94a3b8",
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              Prediction ring · {eventCount}{" "}
              {eventCount === 1 ? "event" : "events"} · {branchCount} lane
              {branchCount === 1 ? "" : "s"} (~
              {Math.round(displayArcRadiusPx)} px)
              <input
                type="range"
                min={0}
                max={ARC_SLIDER_MAX}
                step={ARC_SLIDER_STEP}
                value={arcSliderPercent}
                onChange={(e) => handleArcSliderChange(e.target.value)}
                style={{ width: "100%", accentColor: "#38bdf8" }}
              />
            </label>
            <ResetViewButton onResetLayout={handleResetView} />
          </div>
        </Panel>
      </ReactFlow>
      <DetailsSidebar
        details={selectedDetails}
        onClose={() => {
          onSelectNode?.(null);
        }}
      />
    </div>
  );
}
