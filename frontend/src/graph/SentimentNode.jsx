import { useState, memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { colorsFor } from "./groupColors";

const SOURCE_ICONS = {
  twitter: "X",
  reddit: "R",
  news: "N",
  polymarket: "P",
  kalshi: "K",
  search: "S",
};

const SOURCE_LABELS = {
  twitter: "Twitter",
  reddit: "Reddit",
  news: "News",
  polymarket: "Polymarket",
  kalshi: "Kalshi",
  search: "Search",
};

const LEAF_PREDICTION_SPRITE = "/leaf-pixel-template.png";
const LEAF_PREDICTION_MIMIC_SPRITE = "/leaf2.png";

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
      return 64;
    case "newBranch":
      return 42;
    case "descendant":
      return 36;
    default:
      return 40;
  }
}

/** Prediction leaves render larger than branch nodes for readability in dense layouts. */
const PREDICTION_LEAF_WIDTH_MULT = 2.12;
const PREDICTION_LEAF_HEIGHT_MULT = 1.34;

function PredictionLeafFace({
  size,
  bg,
  glow,
  hovered,
  revealed,
  source,
}) {
  const w = size * PREDICTION_LEAF_WIDTH_MULT;
  const h = size * PREDICTION_LEAF_HEIGHT_MULT;
  const glowCss = hovered
    ? `drop-shadow(0 0 16px ${glow}) drop-shadow(0 0 30px ${glow})`
    : `drop-shadow(0 0 10px ${glow})`;
  const sprite = source === "kalshi" ? LEAF_PREDICTION_MIMIC_SPRITE : LEAF_PREDICTION_SPRITE;

  return (
    <div
      style={{
        position: "relative",
        width: w,
        height: h,
        transition:
          "transform 0.42s cubic-bezier(0.34, 1.45, 0.64, 1), filter 0.25s ease",
        transform: hovered ? "scale(1.1)" : revealed ? "scale(1)" : "scale(0.82)",
        filter: glowCss,
        cursor: "pointer",
      }}
    >
      <img
        src={sprite}
        alt=""
        draggable={false}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
          imageRendering: "pixelated",
          filter: [
            "saturate(1.1) brightness(1.02)",
            "hue-rotate(6deg)",
            `drop-shadow(0 0 8px ${bg}88)`,
            "drop-shadow(0 6px 14px rgba(34,197,94,0.22))",
          ].join(" "),
          transform: "scale(1.02)",
          transformOrigin: "center center",
          pointerEvents: "none",
        }}
      />
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
  const faceDeg =
    typeof data.faceTowardCenterDeg === "number"
      ? data.faceTowardCenterDeg
      : 0;

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

      {isPrediction ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 4,
          }}
        >
          <div
            style={{
              transform: `rotate(${faceDeg}deg)`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
          <PredictionLeafFace
            size={size}
            bg={bg}
            glow={glow}
            hovered={hovered}
            revealed={revealed}
            source={data.source}
          />
          </div>
          <div
            style={{
              fontSize: 12,
              lineHeight: 1,
              letterSpacing: "0.04em",
              textTransform: "uppercase",
              fontWeight: 700,
              color: hovered ? "#f8fafc" : "#e2e8f0",
              textShadow: "0 1px 6px rgba(2, 6, 23, 0.7)",
              pointerEvents: "none",
              userSelect: "none",
            }}
          >
            {SOURCE_LABELS[data.source] ?? "Source"}
          </div>
        </div>
      ) : (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
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
            }}
          >
            {SOURCE_ICONS[data.source] ?? "o"}
          </div>
        </div>
      )}

      {hovered && (
        <div
          style={{
            position: "absolute",
            top:
              (isPrediction
                ? size * PREDICTION_LEAF_HEIGHT_MULT + 20
                : size) + 8,
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
