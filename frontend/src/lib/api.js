const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
const DEFAULT_WORKFLOW_OPTIONS = {
  prediction_limit: 24,
  max_descendants: 18,
  include_social: true,
  bluesky_seconds: 3,
};

async function readJson(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new Error("The API returned invalid JSON.");
  }
}

export async function runWorkflow(query, options = {}) {
  const workflowOptions = options.workflowOptions ?? {};
  const response = await fetch(`${API_BASE}/workflow/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query,
      ...DEFAULT_WORKFLOW_OPTIONS,
      ...workflowOptions,
    }),
    signal: options.signal,
  });

  const payload = await readJson(response);
  if (!response.ok) {
    throw new Error(payload?.detail || "Workflow request failed.");
  }
  return payload;
}

async function parseNdjsonStream(response, handlers) {
  if (!response.body) {
    throw new Error("Streaming is not supported in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        continue;
      }

      let event;
      try {
        event = JSON.parse(trimmed);
      } catch {
        continue;
      }

      if (event.type === "status") {
        handlers.onStatus?.(event);
        continue;
      }
      if (event.type === "snapshot") {
        handlers.onSnapshot?.(event.data, event);
        continue;
      }
      if (event.type === "complete") {
        handlers.onComplete?.(event);
        continue;
      }
      if (event.type === "error") {
        const message = event.message || "Workflow stream failed.";
        handlers.onError?.(message, event);
        throw new Error(message);
      }
    }
  }

  const trailing = buffer.trim();
  if (!trailing) {
    return;
  }

  try {
    const event = JSON.parse(trailing);
    if (event.type === "snapshot") {
      handlers.onSnapshot?.(event.data, event);
    } else if (event.type === "status") {
      handlers.onStatus?.(event);
    } else if (event.type === "complete") {
      handlers.onComplete?.(event);
    }
  } catch {
    // Ignore trailing partial JSON.
  }
}

export async function streamWorkflow(query, handlers = {}) {
  const response = await fetch(`${API_BASE}/workflow/live/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query,
      ...DEFAULT_WORKFLOW_OPTIONS,
      poll_interval_seconds: 12,
    }),
    signal: handlers.signal,
  });

  if (!response.ok) {
    const payload = await readJson(response);
    throw new Error(payload?.detail || "Workflow stream request failed.");
  }

  await parseNdjsonStream(response, handlers);
}

export async function streamWorkflowRun(query, handlers = {}) {
  const workflowOptions = handlers.workflowOptions ?? {};
  const response = await fetch(`${API_BASE}/workflow/run/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query,
      ...DEFAULT_WORKFLOW_OPTIONS,
      ...workflowOptions,
    }),
    signal: handlers.signal,
  });

  if (!response.ok) {
    const payload = await readJson(response);
    throw new Error(payload?.detail || "Workflow stream request failed.");
  }

  await parseNdjsonStream(response, handlers);
}

export async function streamPredictionSearch(query, handlers = {}) {
  const response = await fetch(`${API_BASE}/predictions/search/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      query,
      limit: handlers.limit ?? 10,
    }),
    signal: handlers.signal,
  });

  if (!response.ok) {
    const payload = await readJson(response);
    throw new Error(payload?.detail || "Prediction stream request failed.");
  }

  if (!response.body) {
    throw new Error("Streaming is not supported in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        continue;
      }

      let event;
      try {
        event = JSON.parse(trimmed);
      } catch {
        continue;
      }

      if (event.type === "status") {
        handlers.onStatus?.(event);
        continue;
      }
      if (event.type === "prediction") {
        handlers.onPrediction?.(event.data, event);
        continue;
      }
      if (event.type === "complete") {
        handlers.onComplete?.(event);
        continue;
      }
      if (event.type === "error") {
        const message = event.message || "Prediction stream failed.";
        handlers.onError?.(message, event);
        throw new Error(message);
      }
    }
  }
}

export async function fetchPredictionSuggestions(query) {
  if (!query.trim()) {
    return [];
  }

  const search = new URLSearchParams({
    query,
    limit: "8",
  });
  const response = await fetch(`${API_BASE}/search/suggestions?${search.toString()}`);
  const payload = await readJson(response);
  if (!response.ok) {
    return [];
  }

  const suggestions = Array.isArray(payload?.suggestions) ? payload.suggestions : [];
  return suggestions.filter(
    (suggestion) => typeof suggestion === "string" && suggestion.trim().length > 0
  );
}
