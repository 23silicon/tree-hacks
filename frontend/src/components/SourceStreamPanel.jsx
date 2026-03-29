function formatSourceLabel(source) {
  const normalized = String(source || "unknown").toLowerCase().replace(/_/g, " ");
  if (normalized === "google news") {
    return "Google News";
  }
  if (normalized === "hackernews") {
    return "Hacker News";
  }
  if (normalized === "bluesky") {
    return "Bluesky";
  }
  if (normalized === "rss") {
    return "RSS";
  }
  if (normalized === "reddit") {
    return "Reddit";
  }
  return normalized.replace(/\b\w/g, (match) => match.toUpperCase());
}

function sourceTone(source) {
  const normalized = String(source || "").toLowerCase();
  if (normalized === "google_news") {
    return "border-emerald-400/40 bg-emerald-500/10 text-emerald-200";
  }
  if (normalized === "bluesky") {
    return "border-sky-400/40 bg-sky-500/10 text-sky-200";
  }
  if (normalized === "hackernews") {
    return "border-amber-400/40 bg-amber-500/10 text-amber-200";
  }
  if (normalized === "rss") {
    return "border-fuchsia-400/40 bg-fuchsia-500/10 text-fuchsia-200";
  }
  if (normalized === "reddit") {
    return "border-orange-400/40 bg-orange-500/10 text-orange-200";
  }
  return "border-slate-400/30 bg-slate-500/10 text-slate-200";
}

function recencyTone(tag) {
  if (tag === "historical") {
    return "border-amber-400/35 bg-amber-500/10 text-amber-100";
  }
  if (tag === "context") {
    return "border-violet-400/35 bg-violet-500/10 text-violet-100";
  }
  if (tag === "recent") {
    return "border-cyan-400/35 bg-cyan-500/10 text-cyan-100";
  }
  return "border-emerald-400/35 bg-emerald-500/10 text-emerald-100";
}

function formatTimestamp(timestamp) {
  if (!timestamp) {
    return "Waiting...";
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return String(timestamp);
  }
  return date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function compactText(text, maxLength = 170) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  if (clean.length <= maxLength) {
    return clean;
  }
  return `${clean.slice(0, maxLength - 1).trimEnd()}…`;
}

function stageLabel(payload) {
  const stage = payload?.stream?.stage;
  if (stage === "sources") {
    return "Pulling sources";
  }
  if (stage === "predictions") {
    return "Matching predictions";
  }
  if (stage === "complete" || stage === "analysis") {
    return "Graph ready";
  }
  return "Opening stream";
}

export default function SourceStreamPanel({ payload, message, active }) {
  if (!active && !payload?.sources?.posts?.length) {
    return null;
  }

  const posts = Array.isArray(payload?.sources?.posts) ? payload.sources.posts.slice(0, 12) : [];
  const sourceCounts = payload?.summary?.posts_by_source ?? {};
  const countEntries = Object.entries(sourceCounts).sort((left, right) => right[1] - left[1]);

  return (
    <div className="absolute left-4 top-4 z-30 flex w-[min(420px,calc(100%-2rem))] max-w-full flex-col gap-3">
      <div className="rounded-3xl border border-cyan-400/20 bg-slate-950/88 p-4 shadow-2xl shadow-slate-950/60 backdrop-blur-xl">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-200/90">
              <span className="inline-flex h-2.5 w-2.5 rounded-full bg-cyan-300 shadow-[0_0_14px_rgba(103,232,249,0.9)]" />
              {stageLabel(payload)}
            </div>
            <div className="text-sm text-slate-100">{message || "Collecting live sources..."}</div>
          </div>
          <div className="text-right text-xs text-slate-400">
            <div className="text-lg font-semibold text-slate-100">{payload?.summary?.posts ?? 0}</div>
            <div>sources</div>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {countEntries.length > 0
            ? countEntries.map(([source, count]) => (
                <div
                  key={source}
                  className={`rounded-full border px-2.5 py-1 text-[11px] font-medium ${sourceTone(source)}`}
                >
                  {formatSourceLabel(source)} {count}
                </div>
              ))
            : ["Google News", "Bluesky", "Hacker News"].map((label) => (
                <div
                  key={label}
                  className="rounded-full border border-slate-700/80 bg-slate-800/80 px-2.5 py-1 text-[11px] font-medium text-slate-300"
                >
                  {label}
                </div>
              ))}
        </div>
      </div>

      <div className="max-h-[min(60vh,560px)] overflow-hidden rounded-3xl border border-white/10 bg-slate-950/78 p-3 shadow-2xl shadow-slate-950/60 backdrop-blur-xl">
        <div className="flex max-h-[min(60vh,536px)] flex-col gap-2 overflow-y-auto pr-1">
          {posts.length > 0
            ? posts.map((post) => (
                <div
                  key={post.id || `${post.source}-${post.timestamp}-${post.text}`}
                  className="rounded-2xl border border-white/8 bg-slate-900/85 px-3 py-3 text-sm text-slate-100 shadow-lg shadow-slate-950/30"
                >
                  <div className="mb-2 flex items-center justify-between gap-2 text-[11px] uppercase tracking-[0.16em] text-slate-400">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full border px-2 py-0.5 ${sourceTone(post.source)}`}>
                        {formatSourceLabel(post.source)}
                      </span>
                      {post.recency_tag ? (
                        <span className={`rounded-full border px-2 py-0.5 ${recencyTone(post.recency_tag)}`}>
                          {post.recency_tag}
                        </span>
                      ) : null}
                    </div>
                    <span>{formatTimestamp(post.timestamp)}</span>
                  </div>
                  <div className="text-sm leading-6 text-slate-100">{compactText(post.text)}</div>
                  <div className="mt-2 text-xs text-slate-400">
                    {post.author || formatSourceLabel(post.source)}
                  </div>
                </div>
              ))
            : Array.from({ length: 4 }).map((_, index) => (
                <div
                  key={`skeleton-${index}`}
                  className="animate-pulse rounded-2xl border border-white/8 bg-slate-900/80 px-3 py-3"
                >
                  <div className="mb-3 h-3 w-28 rounded-full bg-slate-700/80" />
                  <div className="space-y-2">
                    <div className="h-3 rounded-full bg-slate-800/90" />
                    <div className="h-3 w-11/12 rounded-full bg-slate-800/70" />
                    <div className="h-3 w-4/5 rounded-full bg-slate-800/60" />
                  </div>
                </div>
              ))}
        </div>
      </div>
    </div>
  );
}
