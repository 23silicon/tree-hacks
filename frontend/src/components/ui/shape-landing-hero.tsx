import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { CSSProperties, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";

const FALL_DURATION_BASE = 92;
const SWAY_DURATION = 28;

function noise(seed: number) {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

type LeafPalette = "emerald" | "teal" | "lime" | "green";
type LeafKind = "classic" | "mimic";

/** Static asset: user-provided 8-bit leaf sprite (`frontend/public/leaf-pixel-template.png`) */
const LEAF_PIXEL_SPRITE = "/leaf-pixel-template.png";
const LEAF_PIXEL_MIMIC_SPRITE = "/leaf2.png";

/** CSS filter base per palette — hue/saturation variation; extra hue from `patternIndex` + `leafIndex` */
const LEAF_PALETTE_FILTER: Record<LeafPalette, string> = {
  emerald: "saturate(1.1) brightness(1.02)",
  teal: "saturate(1.14) brightness(1.03) hue-rotate(-20deg)",
  lime: "saturate(1.2) brightness(1.05) hue-rotate(30deg)",
  green: "saturate(1.06) brightness(1.02) hue-rotate(5deg)",
};

/** Leaf configs: anchor %, box size, rotation, palette, variant (flip / scale / hue) */
type LeafConfig = {
  anchorLeftPct: number;
  anchorTopPct: number;
  width: number;
  height: number;
  rotate: number;
  palette: LeafPalette;
  patternIndex: number;
  kind: LeafKind;
};

const BASE_LEAVES: LeafConfig[] = [
  { anchorLeftPct: 9, anchorTopPct: 11, width: 320, height: 118, rotate: 11, palette: "emerald", patternIndex: 0, kind: "mimic" },
  { anchorLeftPct: 91, anchorTopPct: 14, width: 110, height: 140, rotate: -13, palette: "teal", patternIndex: 1, kind: "classic" },
  { anchorLeftPct: 50, anchorTopPct: 7, width: 280, height: 96, rotate: 6, palette: "green", patternIndex: 2, kind: "mimic" },
  { anchorLeftPct: 11, anchorTopPct: 44, width: 95, height: 128, rotate: -16, palette: "lime", patternIndex: 1, kind: "classic" },
  { anchorLeftPct: 89, anchorTopPct: 46, width: 360, height: 104, rotate: 17, palette: "emerald", patternIndex: 2, kind: "classic" },
  { anchorLeftPct: 30, anchorTopPct: 72, width: 140, height: 200, rotate: -9, palette: "teal", patternIndex: 0, kind: "mimic" },
  { anchorLeftPct: 70, anchorTopPct: 74, width: 300, height: 88, rotate: 12, palette: "lime", patternIndex: 0, kind: "mimic" },
  { anchorLeftPct: 50, anchorTopPct: 38, width: 200, height: 160, rotate: 4, palette: "green", patternIndex: 1, kind: "classic" },
  { anchorLeftPct: 24, anchorTopPct: 24, width: 380, height: 92, rotate: 19, palette: "emerald", patternIndex: 2, kind: "mimic" },
  { anchorLeftPct: 76, anchorTopPct: 26, width: 88, height: 176, rotate: -11, palette: "green", patternIndex: 0, kind: "classic" },
];

function LeafShape({
  config,
  index,
  reducedMotion,
}: {
  config: LeafConfig;
  index: number;
  reducedMotion: boolean;
}) {
  const { width, height, rotate, palette, patternIndex, anchorLeftPct, anchorTopPct, kind } =
    config;

  const fallDuration = FALL_DURATION_BASE + (index % 6) * 11;
  const phaseDelay = -(index / BASE_LEAVES.length) * fallDuration;
  const swayX = 5 + noise(index + 3) * 7;
  const swayTilt = 1.4 + noise(index + 11) * 2.6;
  const swayDuration = SWAY_DURATION + noise(index + 17) * 12;
  const bobY = 0.8 + noise(index + 29) * 2.1;
  const bobDuration = 8 + noise(index + 43) * 5;
  const swayPhase = phaseDelay * (0.25 + noise(index + 67) * 0.35);
  const driftRotate = (noise(index + 79) - 0.5) * 3.2;
  const driftRotateDuration = 18 + noise(index + 97) * 16;

  const styleAnchor: CSSProperties = {
    left: `${anchorLeftPct}%`,
    top: `${anchorTopPct}%`,
    width,
    height,
    transform: "translate(-50%, -50%)",
  };

  if (reducedMotion) {
    return (
      <div className="absolute" style={styleAnchor}>
        <PixelLeafSprite
          palette={palette}
          patternIndex={patternIndex}
          leafIndex={index}
          kind={kind}
        />
      </div>
    );
  }

  return (
    <motion.div
      className="absolute will-change-transform"
      style={styleAnchor}
      initial={false}
      animate={{
        /** Only vertical drift: always full opacity — reads as falling from above, not “popping in” */
        y: ["-125vh", "125vh"],
        rotate: [0, driftRotate, -driftRotate * 0.6, driftRotate * 0.35, 0],
      }}
      transition={{
        y: {
          duration: fallDuration,
          repeat: Number.POSITIVE_INFINITY,
          ease: "linear",
          delay: phaseDelay,
          repeatDelay: 0,
        },
        rotate: {
          duration: driftRotateDuration,
          repeat: Number.POSITIVE_INFINITY,
          ease: "easeInOut",
          delay: swayPhase,
        },
      }}
    >
      <motion.div
        style={{ width, height }}
        className="relative"
        animate={{
          x: [0, swayX, -swayX * 0.78, swayX * 0.48, 0],
          y: [0, -bobY, bobY * 0.66, -bobY * 0.35, 0],
          rotate: [
            rotate,
            rotate + swayTilt,
            rotate - swayTilt * 0.82,
            rotate + swayTilt * 0.34,
            rotate,
          ],
          scale: [1, 1.012, 0.992, 1.008, 1],
        }}
        transition={{
          x: {
            duration: swayDuration,
            repeat: Number.POSITIVE_INFINITY,
            ease: "easeInOut",
            delay: swayPhase,
          },
          y: {
            duration: bobDuration,
            repeat: Number.POSITIVE_INFINITY,
            ease: "easeInOut",
            delay: swayPhase * 0.7,
          },
          rotate: {
            duration: swayDuration * 0.92,
            repeat: Number.POSITIVE_INFINITY,
            ease: "easeInOut",
            delay: swayPhase,
          },
          scale: {
            duration: bobDuration * 1.08,
            repeat: Number.POSITIVE_INFINITY,
            ease: "easeInOut",
            delay: swayPhase * 0.55,
          },
        }}
      >
        <PixelLeafSprite
          palette={palette}
          patternIndex={patternIndex}
          leafIndex={index}
          kind={kind}
        />
      </motion.div>
    </motion.div>
  );
}

/** Renders the fixed pixel-art PNG; size from box, color from filters, orientation from flip + parent rotation */
function PixelLeafSprite({
  palette,
  patternIndex,
  leafIndex,
  kind,
}: {
  palette: LeafPalette;
  patternIndex: number;
  leafIndex: number;
  kind: LeafKind;
}) {
  const hueJitter = (patternIndex - 1) * 7 + (leafIndex % 5) * 5;
  const flipX = patternIndex === 1;
  const innerScale = 0.88 + (patternIndex % 3) * 0.08;
  const spriteSrc = kind === "mimic" ? LEAF_PIXEL_MIMIC_SPRITE : LEAF_PIXEL_SPRITE;

  const filter = [
    LEAF_PALETTE_FILTER[palette],
    `hue-rotate(${hueJitter}deg)`,
    "drop-shadow(0 3px 0 rgba(0,0,0,0.38))",
    "drop-shadow(0 8px 18px rgba(34,197,94,0.28))",
  ].join(" ");

  const spriteBaseClass = cn(
    "h-full w-full max-h-full max-w-full object-contain",
    "[image-rendering:pixelated] [image-rendering:-moz-crisp-edges]",
  );

  const baseTransform = `${flipX ? "scaleX(-1) " : ""}scale(${innerScale})`;
  const kindTransform =
    kind === "mimic" ? "rotate(-6deg) translate(-1%, 1%)" : "";

  return (
    <div className="relative flex h-full w-full items-center justify-center overflow-visible">
      <img
        src={spriteSrc}
        alt=""
        draggable={false}
        className={spriteBaseClass}
        style={{
          filter,
          transform: `${baseTransform} ${kindTransform}`,
          transformOrigin: "center center",
        }}
      />
    </div>
  );
}

function LeafDriftMask({ children }: { children: ReactNode }) {
  return (
    <div
      className="absolute inset-0 overflow-hidden [mask-image:linear-gradient(to_bottom,transparent_0%,black_4%,black_96%,transparent_100%)] [-webkit-mask-image:linear-gradient(to_bottom,transparent_0%,black_4%,black_96%,transparent_100%)]"
      style={{ maskSize: "100% 100%" }}
    >
      {children}
    </div>
  );
}

function ContinuousLeavesLayer() {
  const reducedMotion = useReducedMotion() ?? false;

  return (
    <LeafDriftMask>
      {BASE_LEAVES.map((config, i) => (
        <LeafShape key={i} config={config} index={i} reducedMotion={reducedMotion} />
      ))}
    </LeafDriftMask>
  );
}

// --- Forest graph: one node at a time per tree cluster, edges to neighbors in-tree ---

const NODE_LIFETIME_MS = 10_000;
/** One new node this often (staggered, not a burst) */
const SPAWN_INTERVAL_MS = 620;
const MAX_NODES_TOTAL = 48;
const DOT_FADE_OUT_SEC = 0.5;

type TreeCluster = {
  id: number;
  /** Horizontal center % for this “tree” */
  centerX: number;
};

const TREE_CLUSTERS: TreeCluster[] = [
  { id: 0, centerX: 10 },
  { id: 1, centerX: 24 },
  { id: 2, centerX: 38 },
  { id: 3, centerX: 52 },
  { id: 4, centerX: 66 },
  { id: 5, centerX: 80 },
  { id: 6, centerX: 92 },
];

type GraphNode = {
  id: number;
  treeId: number;
  leftPct: number;
  topPct: number;
  spawnTime: number;
  sizePx: number;
};

type GraphEdge = {
  id: number;
  fromId: number;
  toId: number;
};

function dist2(a: Pick<GraphNode, "leftPct" | "topPct">, b: Pick<GraphNode, "leftPct" | "topPct">) {
  const dx = a.leftPct - b.leftPct;
  const dy = a.topPct - b.topPct;
  return dx * dx + dy * dy;
}

function nearestInTree(
  p: Pick<GraphNode, "leftPct" | "topPct">,
  others: GraphNode[],
): GraphNode | null {
  if (others.length === 0) return null;
  let best = others[0];
  let bestD = dist2(p, others[0]);
  for (let i = 1; i < others.length; i++) {
    const d = dist2(p, others[i]);
    if (d < bestD) {
      bestD = d;
      best = others[i];
    }
  }
  return best;
}

function TreeNodeDotCore({ sizePx }: { sizePx: number }) {
  return (
    <span
      className="block rounded-full bg-emerald-300/80 shadow-[0_0_12px_3px_rgba(110,231,183,0.5),0_0_24px_5px_rgba(52,211,153,0.22)]"
      style={{ width: sizePx, height: sizePx }}
    />
  );
}

function EdgePath({
  x1,
  y1,
  x2,
  y2,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}) {
  const d = `M ${x1} ${y1} L ${x2} ${y2}`;
  return (
    <motion.path
      d={d}
      fill="none"
      stroke="url(#branchGrad)"
      strokeWidth={1.25}
      strokeLinecap="round"
      vectorEffect="non-scaling-stroke"
      initial={{ pathLength: 0, opacity: 0 }}
      animate={{ pathLength: 1, opacity: 0.62 }}
      transition={{
        pathLength: { duration: 0.55, ease: [0.22, 1, 0.36, 1] },
        opacity: { duration: 0.35, delay: 0.1 },
      }}
    />
  );
}

type GraphState = { nodes: GraphNode[]; edges: GraphEdge[] };

function BackgroundForestLayer() {
  const [graph, setGraph] = useState<GraphState>({ nodes: [], edges: [] });
  const nodeIdRef = useRef(0);
  const edgeIdRef = useRef(0);
  const treeRoundRobin = useRef(0);
  const reducedMotion = useReducedMotion() ?? false;

  const nodes = graph.nodes;
  const edges = graph.edges;

  const nodeById = useMemo(() => {
    const m = new Map<number, GraphNode>();
    for (const n of nodes) m.set(n.id, n);
    return m;
  }, [nodes]);

  /** Drop nodes older than NODE_LIFETIME_MS; edges that reference removed nodes go too */
  const pruneExpired = useCallback(() => {
    const now = Date.now();
    setGraph((g) => {
      const nextNodes = g.nodes.filter((n) => now - n.spawnTime < NODE_LIFETIME_MS);
      const alive = new Set(nextNodes.map((n) => n.id));
      const nextEdges = g.edges.filter((e) => alive.has(e.fromId) && alive.has(e.toId));
      if (nextNodes.length === g.nodes.length && nextEdges.length === g.edges.length) {
        return g;
      }
      return { nodes: nextNodes, edges: nextEdges };
    });
  }, []);

  useEffect(() => {
    if (reducedMotion) return;
    const iv = window.setInterval(pruneExpired, 380);
    return () => window.clearInterval(iv);
  }, [reducedMotion, pruneExpired]);

  const spawnOneNode = useCallback(() => {
    setGraph((g) => {
      if (g.nodes.length >= MAX_NODES_TOTAL) return g;

      const tree = TREE_CLUSTERS[treeRoundRobin.current % TREE_CLUSTERS.length];
      treeRoundRobin.current += 1;

      const newId = ++nodeIdRef.current;
      const leftPct = tree.centerX + (Math.random() - 0.5) * 6.5;
      const topPct = 14 + Math.random() * 72;
      const sizePx = 3.2 + Math.random() * 3.8;

      const candidate: GraphNode = {
        id: newId,
        treeId: tree.id,
        leftPct,
        topPct,
        spawnTime: Date.now(),
        sizePx,
      };

      const sameTree = g.nodes.filter((n) => n.treeId === tree.id);
      const neighbor = nearestInTree(candidate, sameTree);

      const newEdges = [...g.edges];
      if (neighbor) {
        newEdges.push({
          id: ++edgeIdRef.current,
          fromId: neighbor.id,
          toId: newId,
        });
      }

      return {
        nodes: [...g.nodes, candidate],
        edges: newEdges,
      };
    });
  }, []);

  useEffect(() => {
    if (reducedMotion) return;
    let cancelled = false;
    const schedule = () => {
      if (cancelled) return;
      spawnOneNode();
      timer = window.setTimeout(schedule, SPAWN_INTERVAL_MS);
    };
    let timer = window.setTimeout(schedule, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [reducedMotion, spawnOneNode]);

  if (reducedMotion) return null;

  return (
    <div
      className="pointer-events-none absolute inset-0 overflow-hidden"
      aria-hidden
    >
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="branchGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="rgba(134,239,172,0.6)" />
            <stop offset="50%" stopColor="rgba(52,211,153,0.5)" />
            <stop offset="100%" stopColor="rgba(16,185,129,0.4)" />
          </linearGradient>
        </defs>
        {edges.map((e) => {
          const a = nodeById.get(e.fromId);
          const b = nodeById.get(e.toId);
          if (!a || !b) return null;
          return (
            <EdgePath
              key={e.id}
              x1={a.leftPct}
              y1={a.topPct}
              x2={b.leftPct}
              y2={b.topPct}
            />
          );
        })}
      </svg>

      <AnimatePresence initial={false}>
        {nodes.map((n) => (
          <motion.div
            key={n.id}
            className="absolute"
            style={{
              left: `${n.leftPct}%`,
              top: `${n.topPct}%`,
              transform: "translate(-50%, -50%)",
            }}
            initial={{ opacity: 1 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0, scale: 0.88 }}
            transition={{
              duration: DOT_FADE_OUT_SEC,
              ease: [0.4, 0, 0.2, 1],
            }}
          >
            <TreeNodeDotCore sizePx={n.sizePx} />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

function HeroGeometric({
  title1 = "See how opinion",
  title2 = "Branches",
  onBrandClick,
  children,
}: {
  title1?: string;
  title2?: string;
  onBrandClick?: () => void;
  children?: ReactNode;
}) {
  const firstLineWords = title1.split(/\s+/).filter(Boolean);
  const wordRevealBaseDelay = 0.6;
  const wordRevealStepDelay = 0.4;
  const postWordPause = 0.75;
  const branchesAndSearchDelay =
    wordRevealBaseDelay + Math.max(firstLineWords.length - 1, 0) * wordRevealStepDelay + postWordPause;

  return (
    <div className="relative flex min-h-screen w-full flex-col items-center justify-center overflow-hidden bg-[#050806]">
      <button
        type="button"
        onClick={onBrandClick}
        className="absolute left-4 top-4 z-40 cursor-pointer text-base font-semibold tracking-wide text-white transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 md:left-6 md:top-6 md:text-lg"
        aria-label="Return to main page"
      >
        Sentimentree
      </button>

      <div className="absolute inset-0 bg-gradient-to-br from-emerald-600/[0.14] via-emerald-900/[0.08] to-green-950/[0.12] blur-3xl" />

      <div className="pointer-events-none absolute inset-0 z-[3] bg-gradient-to-t from-[#050806]/75 via-transparent to-[#050806]/40" />

      <div className="absolute inset-0 z-[6]">
        <BackgroundForestLayer />
      </div>

      <div className="absolute inset-0 z-[8]">
        <ContinuousLeavesLayer />
      </div>

      <div className="relative z-10 flex w-full max-w-full flex-1 flex-col items-center justify-center px-4 md:px-6">
        <div className="mx-auto flex w-full max-w-3xl flex-col items-center justify-center text-center">
          <div className="flex w-full flex-col items-center text-center">
            <h1 className="mb-6 w-full text-center text-4xl font-bold tracking-tight sm:text-6xl md:mb-8 md:text-8xl">
              <span>
                {firstLineWords.map((word, index) => (
                  <motion.span
                    key={`${word}-${index}`}
                    initial={{ opacity: 0, y: 18, filter: "blur(6px)" }}
                    animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                    transition={{
                      duration: 0.55,
                      delay: wordRevealBaseDelay + index * wordRevealStepDelay,
                      ease: [0.25, 0.4, 0.25, 1],
                    }}
                    className="inline-block bg-gradient-to-b from-white to-white/80 bg-clip-text text-transparent"
                  >
                    {word}
                    {index < firstLineWords.length - 1 ? "\u00a0" : ""}
                  </motion.span>
                ))}
              </span>
              <br />
              <motion.span
                initial={{ opacity: 0, y: 24, filter: "blur(8px)" }}
                animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
                transition={{
                  duration: 0.8,
                  delay: branchesAndSearchDelay,
                  ease: [0.25, 0.4, 0.25, 1],
                }}
                className={cn(
                  "font-grand-cursive bg-gradient-to-r from-emerald-300 via-lime-200 to-green-400 bg-clip-text text-transparent",
                )}
              >
                {title2}
              </motion.span>
            </h1>
          </div>

          {children ? (
            <motion.div
              initial={{ opacity: 0, y: 26, filter: "blur(8px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={{
                duration: 0.8,
                delay: branchesAndSearchDelay,
                ease: [0.25, 0.4, 0.25, 1],
              }}
              className="flex w-full flex-col items-center justify-center text-center"
            >
              {children}
            </motion.div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export { HeroGeometric };
