import { useEffect, useRef, useState } from "react";
import GraphCanvas from "./graph/GraphCanvas";
import LandingPage from "./LandingPage";
import SourceStreamPanel from "@/components/SourceStreamPanel";
import { GooeySearchBar } from "@/components/ui/animated-search-bar";
import { runWorkflow, streamPredictionSearch, streamWorkflowRun } from "@/lib/api";

function createPlaceholderPayload(query) {
  const timestamp = new Date().toISOString();
  return {
    query,
    fetched_at: timestamp,
    snapshot_id: `placeholder-${Date.now()}`,
    source_mode: "pending",
    warnings: [],
    stream: {
      mode: "live",
      stage: "initial",
      iteration: 0,
    },
    runtime: {
      sentiment_tree_available: false,
      llm_affinity_ran: false,
      startup_preload_ok: true,
    },
    summary: {
      posts: 0,
      posts_by_source: {},
      predictions: 0,
      events: 0,
      enriched_items: 0,
      candidate_pairs: 0,
      affinity_results: 0,
    },
    sources: {
      posts: [],
      predictions: [],
      events: [],
      enriched_items: [],
      candidate_pairs: [],
      affinity_results: [],
    },
    graph: {
      nodes: [
        {
          id: "root",
          data: {
            label: query,
            category: "root",
            sentiment: 0.5,
            source: "search",
            timestamp,
            summary: "Streaming live sources...",
          },
        },
      ],
      edges: [],
    },
  };
}

function formatCompactMetric(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "0";
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${Math.round(value / 1_000)}k`;
  }
  return `${Math.round(value)}`;
}

function shortenLabel(text, maxLength = 80) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  if (clean.length <= maxLength) {
    return clean;
  }
  return `${clean.slice(0, maxLength - 1).trimEnd()}…`;
}

function createPredictionPhasePayload(query, predictions) {
  const timestamp = new Date().toISOString();
  return {
    query,
    fetched_at: timestamp,
    snapshot_id: `predictions-${Date.now()}`,
    source_mode: "live",
    warnings: [],
    stream: {
      mode: "phased",
      stage: "predictions",
      iteration: 0,
    },
    runtime: {
      sentiment_tree_available: false,
      llm_affinity_ran: false,
      startup_preload_ok: true,
    },
    summary: {
      posts: 0,
      posts_by_source: {},
      predictions: predictions.length,
      events: 0,
      enriched_items: 0,
      candidate_pairs: 0,
      affinity_results: 0,
      event_prediction_links: 0,
    },
    sources: {
      posts: [],
      predictions,
      events: [],
      enriched_items: [],
      candidate_pairs: [],
      affinity_results: [],
      event_prediction_links: [],
    },
    graph: {
      nodes: [
        {
          id: "root",
          data: {
            label: query,
            category: "root",
            sentiment: 0.5,
            source: "search",
            timestamp,
            summary: `${predictions.length} prediction markets matched so far.`,
          },
        },
        ...predictions.map((prediction) => ({
          id: prediction.id,
          data: {
            label: shortenLabel(prediction.question, 80),
            category: "prediction",
            sentiment:
              typeof prediction.yes_probability === "number"
                ? prediction.yes_probability
                : 0.5,
            source: prediction.source,
            timestamp: prediction.closes_at || timestamp,
            summary: `${(prediction.category || "general").toString()} · YES ${Math.round(((prediction.yes_probability ?? 0.5) * 100))}% · Vol $${formatCompactMetric(prediction.volume_usd)}`,
          },
        })),
      ],
      edges: predictions.map((prediction) => ({
        id: `e-root-${prediction.id}`,
        source: "root",
        target: prediction.id,
      })),
      support_edges: [],
      prediction_event_map: {},
    },
  };
}

function mergePredictionsIntoPayload(payload, predictions) {
  if (!payload) {
    return null;
  }
  if (!Array.isArray(predictions) || predictions.length === 0) {
    return payload;
  }

  const timestamp = payload.fetched_at || new Date().toISOString();
  const graph = payload.graph || { nodes: [], edges: [], support_edges: [], prediction_event_map: {} };
  const baseNodes = Array.isArray(graph.nodes) ? graph.nodes : [];
  const nonPredictionNodes = baseNodes.filter((node) => node?.data?.category !== "prediction");
  const rootNode = nonPredictionNodes.find((node) => node.id === "root") || {
    id: "root",
    data: {
      label: payload.query,
      category: "root",
      sentiment: 0.5,
      source: "search",
      timestamp,
      summary: `${predictions.length} prediction markets matched so far.`,
    },
  };
  const remainingNodes = nonPredictionNodes.filter((node) => node.id !== "root");

  const predictionNodes = predictions.map((prediction) => ({
    id: prediction.id,
    data: {
      label: shortenLabel(prediction.question, 80),
      category: "prediction",
      sentiment:
        typeof prediction.yes_probability === "number"
          ? prediction.yes_probability
          : 0.5,
      source: prediction.source,
      timestamp: prediction.closes_at || timestamp,
      summary: `${(prediction.category || "general").toString()} · YES ${Math.round(((prediction.yes_probability ?? 0.5) * 100))}% · Vol $${formatCompactMetric(prediction.volume_usd)}`,
    },
  }));

  const nonPredictionEdges = Array.isArray(graph.edges)
    ? graph.edges.filter((edge) => {
        const sourceNode = baseNodes.find((node) => node.id === edge.source);
        const targetNode = baseNodes.find((node) => node.id === edge.target);
        return sourceNode?.data?.category !== "prediction" && targetNode?.data?.category !== "prediction";
      })
    : [];
  const predictionEdges = predictions.map((prediction) => ({
    id: `e-root-${prediction.id}`,
    source: "root",
    target: prediction.id,
  }));

  return {
    ...payload,
    summary: {
      ...(payload.summary || {}),
      predictions: predictions.length,
    },
    sources: {
      ...(payload.sources || {}),
      predictions,
    },
    graph: {
      ...graph,
      nodes: [{ ...rootNode }, ...remainingNodes, ...predictionNodes],
      edges: [...nonPredictionEdges, ...predictionEdges],
      support_edges: Array.isArray(graph.support_edges) ? graph.support_edges : [],
      prediction_event_map: graph.prediction_event_map || {},
    },
  };
}

const WORKFLOW_REFRESH_MS = 20000;
const INITIAL_WORKFLOW_OPTIONS = {
  include_social: true,
  bluesky_seconds: 2,
  prediction_limit: 10,
  max_descendants: 28,
};

export default function App() {
  const [showGraph, setShowGraph] = useState(false);
  const [graphPayload, setGraphPayload] = useState(null);
  const [sourceFeedPayload, setSourceFeedPayload] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [error, setError] = useState("");
  const [streamMessage, setStreamMessage] = useState("");
  const [isWorkflowLoading, setIsWorkflowLoading] = useState(false);
  const requestAbortRef = useRef(null);
  const pollTimerRef = useRef(null);
  const latestPredictionBatchRef = useRef([]);
  const latestWorkflowPayloadRef = useRef(null);
  const workflowStageRef = useRef("initial");

  useEffect(() => {
    return () => {
      requestAbortRef.current?.abort();
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
      }
    };
  }, []);

  const clearActiveRun = () => {
    requestAbortRef.current?.abort();
    requestAbortRef.current = null;
    setIsWorkflowLoading(false);
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  const scheduleRefresh = (query, controller) => {
    pollTimerRef.current = setTimeout(async () => {
      if (requestAbortRef.current !== controller || controller.signal.aborted) {
        return;
      }

      setStreamMessage("Refreshing graph...");
      try {
        const payload = await runWorkflow(query, {
          signal: controller.signal,
          workflowOptions: INITIAL_WORKFLOW_OPTIONS,
        });
        if (requestAbortRef.current !== controller || controller.signal.aborted) {
          return;
        }
        setGraphPayload(payload);
        setSourceFeedPayload(payload);
        setStreamMessage(
          `Live graph: ${payload?.summary?.posts ?? 0} sources, ${payload?.summary?.predictions ?? 0} predictions, ${payload?.summary?.events ?? 0} events.`
        );
      } catch (err) {
        if (controller.signal.aborted) {
          return;
        }
        setError(err instanceof Error ? err.message : "Refresh failed.");
        setStreamMessage("Auto-refresh failed.");
      }

      if (requestAbortRef.current === controller && !controller.signal.aborted) {
        scheduleRefresh(query, controller);
      }
    }, WORKFLOW_REFRESH_MS);
  };

  const handleSearch = async (query) => {
    clearActiveRun();

    const controller = new AbortController();
    requestAbortRef.current = controller;
    const placeholderPayload = createPlaceholderPayload(query);

    setShowGraph(true);
    setGraphPayload(placeholderPayload);
    setSourceFeedPayload(placeholderPayload);
    setSelectedNodeId(null);
    setError("");
    setStreamMessage("Opening workflow stream...");
    setIsWorkflowLoading(true);

    latestPredictionBatchRef.current = [];
    latestWorkflowPayloadRef.current = placeholderPayload;
    workflowStageRef.current = "initial";

    const predictionStreamPromise = streamPredictionSearch(query, {
      signal: controller.signal,
      limit: INITIAL_WORKFLOW_OPTIONS.prediction_limit,
      onPrediction: (prediction) => {
        if (requestAbortRef.current !== controller || controller.signal.aborted) {
          return;
        }
        if (["predictions", "complete", "analysis"].includes(workflowStageRef.current)) {
          return;
        }
        latestPredictionBatchRef.current = [
          ...latestPredictionBatchRef.current.filter((item) => item.id !== prediction.id),
          prediction,
        ].slice(0, INITIAL_WORKFLOW_OPTIONS.prediction_limit);
        const mergedPayload = mergePredictionsIntoPayload(
          latestWorkflowPayloadRef.current,
          latestPredictionBatchRef.current
        );
        setGraphPayload(
          mergedPayload || createPredictionPhasePayload(query, latestPredictionBatchRef.current)
        );
        setStreamMessage(
          `Matched ${latestPredictionBatchRef.current.length} prediction markets. Building event chain...`
        );
      },
      onStatus: (event) => {
        if (requestAbortRef.current !== controller || controller.signal.aborted) {
          return;
        }
        if (event.status === "started") {
          setStreamMessage("Matching prediction markets...");
        }
      },
    }).catch((err) => {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "Prediction search failed.");
      }
    });

    try {
      await streamWorkflowRun(query, {
        signal: controller.signal,
        workflowOptions: INITIAL_WORKFLOW_OPTIONS,
        onStatus: (event) => {
          if (requestAbortRef.current !== controller || controller.signal.aborted) {
            return;
          }

          if (event.status === "started") {
            setStreamMessage("Opening workflow stream...");
            return;
          }
          if (event.status === "sources_started") {
            setStreamMessage("Pulling sources from Google News, RSS, Reddit, Bluesky, and Hacker News...");
            return;
          }
          if (event.status === "source_batch") {
            const label = String(event.label || "source")
              .replace(/^google_news:/, "Google News: ")
              .replace(/^hackernews:/, "Hacker News: ")
              .replace(/^rss$/, "RSS feeds")
              .replace(/^reddit$/, "Reddit");
            setStreamMessage(`Pulling sources... ${event.posts ?? 0} collected after ${label}.`);
            return;
          }
          if (event.status === "sources_collected") {
            setStreamMessage(`Collected ${event.posts ?? 0} sources. Matching prediction markets...`);
            return;
          }
          if (event.status === "historical_context_loaded") {
            setStreamMessage(
              `Loaded ${event.historical_posts ?? 0} older context items from local cache.`
            );
            return;
          }
          if (event.status === "predictions_ready") {
            setStreamMessage(
              `Matched ${event.predictions ?? 0} prediction markets. Building event chain...`
            );
            return;
          }
          if (event.status === "sentiment_tree_complete") {
            setStreamMessage(
              `Linking ${event.events ?? 0} events into the timeline...`
            );
          }
        },
        onSnapshot: (data, event) => {
          if (requestAbortRef.current !== controller || controller.signal.aborted) {
            return;
          }

          const stage = event?.stage || data?.stream?.stage || "initial";
          workflowStageRef.current = stage;
          latestWorkflowPayloadRef.current = data;
          setSourceFeedPayload(data);

          if (stage === "predictions" || stage === "complete" || stage === "analysis") {
            setGraphPayload(data);
            return;
          }

          setGraphPayload(
            mergePredictionsIntoPayload(data, latestPredictionBatchRef.current) || data
          );
        },
      });
      if (requestAbortRef.current !== controller || controller.signal.aborted) {
        return false;
      }
      await predictionStreamPromise;
      const payload = latestWorkflowPayloadRef.current;
      if (payload) {
        setGraphPayload(payload);
        setSourceFeedPayload(payload);
      }
      setIsWorkflowLoading(false);
      setStreamMessage(
        `Live graph: ${payload?.summary?.posts ?? 0} sources, ${payload?.summary?.predictions ?? 0} predictions, ${payload?.summary?.events ?? 0} events.`
      );
      scheduleRefresh(query, controller);
    } catch {
      if (controller.signal.aborted) {
        return false;
      }

      try {
        const payload = await runWorkflow(query, {
          signal: controller.signal,
          workflowOptions: INITIAL_WORKFLOW_OPTIONS,
        });
        if (requestAbortRef.current !== controller || controller.signal.aborted) {
          return false;
        }
        await predictionStreamPromise;
        latestWorkflowPayloadRef.current = payload;
        workflowStageRef.current = "complete";
        setGraphPayload(payload);
        setSourceFeedPayload(payload);
        setIsWorkflowLoading(false);
        setStreamMessage(
          `Live graph: ${payload?.summary?.posts ?? 0} sources, ${payload?.summary?.predictions ?? 0} predictions, ${payload?.summary?.events ?? 0} events.`
        );
        scheduleRefresh(query, controller);
      } catch (fallbackErr) {
        if (controller.signal.aborted) {
          return false;
        }
        setIsWorkflowLoading(false);
        setError(fallbackErr instanceof Error ? fallbackErr.message : "Search failed.");
        setStreamMessage("Search failed.");
      }
    }

    return true;
  };

  if (!showGraph) {
    return <LandingPage onSearch={handleSearch} error={error} />;
  }

  const statsPayload = sourceFeedPayload ?? graphPayload;

  return (
    <div className="flex h-full min-h-0 w-full flex-col">
      <GooeySearchBar onSearch={handleSearch} />
      <div className="border-b border-white/10 bg-slate-950/90 px-4 py-2 text-sm text-slate-200">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>{streamMessage || "Streaming live updates..."}</span>
          <span className="text-slate-400">
            {statsPayload?.summary?.posts ?? 0} sources · {statsPayload?.summary?.predictions ?? 0} predictions · {statsPayload?.summary?.events ?? 0} events
          </span>
        </div>
      </div>
      {error ? (
        <div className="border-b border-red-400/30 bg-red-500/10 px-4 py-2 text-sm text-red-100">
          {error}
        </div>
      ) : null}
      <div className="relative min-h-0 flex-1">
        <SourceStreamPanel
          payload={sourceFeedPayload ?? graphPayload}
          message={streamMessage}
          active={isWorkflowLoading}
        />
        <GraphCanvas
          key={graphPayload?.snapshot_id ?? graphPayload?.fetched_at ?? "sample-graph"}
          payload={graphPayload}
          selectedNodeId={selectedNodeId}
          onSelectNode={setSelectedNodeId}
        />
      </div>
    </div>
  );
}
