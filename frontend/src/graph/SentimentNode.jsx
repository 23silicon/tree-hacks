import { useState, memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { colorsFor } from "./groupColors";

const SOURCE_ICONS = {
  twitter: "X",
  reddit: "R",
  news: "GN",
  google_news: "GN",
  bluesky: "BS",
  affinity: "AI",
  polymarket: "PM",
  kalshi: "K",
  search: "?",
};

const CATEGORY_LABEL = {
  root: "Root",
  event: "Event",
  branch: "Branch",
  newBranch: "New branch",
  prediction: "Prediction",
  descendant: "Descendant",
};

function nodeSize(category) {
  switch (category) {
    case "root":
      return 56;
    case "prediction":
      return 72;
    case "event":
      return 44;
    case "newBranch":
      return 42;
    case "descendant":
      return 36;
    default:
      return 40;
  }
}

function formatPredictionPercent(sentiment) {
  const normalized =
    typeof sentiment === "number" && !Number.isNaN(sentiment) ? sentiment : 0.5;
  return `${Math.round(normalized * 100)}%`;
}

function PredictionRingFace({
  size,
  bg,
  glow,
  hovered,
  revealed,
  icon,
  sentiment,
}) {
  const glowCss = hovered
    ? `0 0 22px 8px ${glow}, inset 0 0 0 1px rgba(255,255,255,0.12)`
    : `0 0 14px 4px ${glow}, inset 0 0 0 1px rgba(255,255,255,0.08)`;

  return (
    <div
      style={{
        position: "relative",
        width: size,
        height: size,
        borderRadius: "999px",
        background:
          "radial-gradient(circle at 30% 28%, rgba(255,255,255,0.24), transparent 42%), rgba(2,6,23,0.9)",
        border: `2px solid ${bg}`,
        boxShadow: glowCss,
        transition:
          "transform 0.42s cubic-bezier(0.34, 1.45, 0.64, 1), box-shadow 0.25s ease",
        transform: hovered ? "scale(1.1)" : revealed ? "scale(1)" : "scale(0.82)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        cursor: "pointer",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 7,
          borderRadius: "999px",
          border: `1.5px solid ${bg}AA`,
          background: `linear-gradient(160deg, ${bg}22, rgba(15,23,42,0.72))`,
        }}
      />
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 4,
          fontSize: 13,
          fontWeight: 700,
          lineHeight: 1,
          pointerEvents: "none",
          color: "#e0f2fe",
        }}
      >
        <span style={{ fontSize: 11, letterSpacing: "0.08em" }}>{icon}</span>
        <span style={{ fontSize: 14, color: "#f8fafc" }}>
          {formatPredictionPercent(sentiment)}
        </span>
      </div>
    </div>
  );
}

function SentimentNode({ data }) {
  const [hovered, setHovered] = useState(false);
  const category = data.category ?? "branch";
  const { bg, glow } = colorsFor(category);
  const size = nodeSize(category);
  const iconSize = category === "root" ? 20 : 16;
  const revealed = data.reveal !== false;
  const isPrediction = category === "prediction";

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: "relative",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        isConnectable={false}
        style={{ opacity: 0, pointerEvents: "none", width: 1, height: 1 }}
      />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {isPrediction ? (
          <PredictionRingFace
            size={size}
            bg={bg}
            glow={glow}
            hovered={hovered}
            revealed={revealed}
            icon={SOURCE_ICONS[data.source] ?? "●"}
            sentiment={data.sentiment}
          />
        ) : (
          <div
            style={{
              width: size,
              height: size,
              borderRadius: "50%",
              background: bg,
              boxShadow: hovered
                ? `0 0 24px 8px ${glow}, 0 0 48px 16px ${glow}`
                : `0 0 12px 4px ${glow}`,
              transition:
                "box-shadow 0.25s ease, transform 0.42s cubic-bezier(0.34, 1.45, 0.64, 1)",
              transform: hovered
                ? "scale(1.15)"
                : revealed
                  ? "scale(1)"
                  : "scale(0.82)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: iconSize,
              cursor: "pointer",
              color: category === "root" ? "#111827" : "#0f172a",
              fontWeight: 700,
            }}
          >
            {SOURCE_ICONS[data.source] ?? "●"}
          </div>
        )}
      </div>

      {hovered && (
        <div
          style={{
            position: "absolute",
            top:
              size + 8,
            left: "50%",
            transform: "translateX(-50%)",
            background: "rgba(15,15,20,0.92)",
            border: `1px solid ${bg}44`,
            borderRadius: 10,
            padding: "10px 14px",
            width: 240,
            zIndex: 50,
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              fontSize: 10,
              fontWeight: 600,
              letterSpacing: "0.04em",
              textTransform: "uppercase",
              color: "#64748b",
              marginBottom: 4,
            }}
          >
            {CATEGORY_LABEL[category] ?? category}
          </div>
          <div
            style={{
              color: category === "root" ? "#e2e8f0" : bg,
              fontWeight: 700,
              fontSize: 13,
              marginBottom: 4,
              lineHeight: 1.3,
            }}
          >
            {data.label}
          </div>
          <div style={{ color: "#94a3b8", fontSize: 11, lineHeight: 1.5 }}>
            {data.summary}
          </div>
          <div
            style={{
              marginTop: 6,
              display: "flex",
              justifyContent: "space-between",
              fontSize: 10,
              color: "#64748b",
            }}
          >
            <span>{data.source}</span>
            <span>sentiment {(data.sentiment * 100).toFixed(0)}%</span>
          </div>
        </div>
      )}

      <Handle
        type="source"
        position={Position.Top}
        isConnectable={false}
        style={{ opacity: 0, pointerEvents: "none", width: 1, height: 1 }}
      />
    </div>
  );
}

export default memo(SentimentNode);
