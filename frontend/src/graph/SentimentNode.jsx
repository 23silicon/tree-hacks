import { useState, memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { colorsFor } from "./groupColors";

const SOURCE_ICONS = {
  twitter: "𝕏",
  reddit: "⬡",
  news: "📰",
  polymarket: "📊",
  search: "🔍",
};

const CATEGORY_LABEL = {
  root: "Root",
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
      return 48;
    case "newBranch":
      return 42;
    case "descendant":
      return 36;
    default:
      return 40;
  }
}

function SentimentNode({ data }) {
  const [hovered, setHovered] = useState(false);
  const category = data.category ?? "branch";
  const { bg, glow } = colorsFor(category);
  const size = nodeSize(category);
  const iconSize = category === "root" ? 20 : 16;

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
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />

      <div
        style={{
          width: size,
          height: size,
          borderRadius: "50%",
          background: bg,
          boxShadow: hovered
            ? `0 0 24px 8px ${glow}, 0 0 48px 16px ${glow}`
            : `0 0 12px 4px ${glow}`,
          transition: "box-shadow 0.25s ease, transform 0.2s ease",
          transform: hovered ? "scale(1.15)" : "scale(1)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: iconSize,
          cursor: "pointer",
        }}
      >
        {SOURCE_ICONS[data.source] ?? "●"}
      </div>

      {hovered && (
        <div
          style={{
            position: "absolute",
            top: size + 8,
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

      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </div>
  );
}

export default memo(SentimentNode);
