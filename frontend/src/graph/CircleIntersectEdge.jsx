import { memo, useMemo } from "react";
import { BaseEdge, getStraightPath, useInternalNode } from "@xyflow/react";

function CircleIntersectEdge({
  id,
  source,
  target,
  style,
  markerEnd,
  markerStart,
  interactionWidth,
}) {
  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);

  const { path, labelX, labelY } = useMemo(() => {
    if (!sourceNode || !targetNode) {
      return { path: "", labelX: 0, labelY: 0 };
    }

    const w1 = sourceNode.measured.width ?? 44;
    const h1 = sourceNode.measured.height ?? 44;
    const w2 = targetNode.measured.width ?? 44;
    const h2 = targetNode.measured.height ?? 44;

    const { x: ax, y: ay } = sourceNode.internals.positionAbsolute;
    const { x: bx, y: by } = targetNode.internals.positionAbsolute;

    const cx1 = ax + w1 / 2;
    const cy1 = ay + h1 / 2;
    const cx2 = bx + w2 / 2;
    const cy2 = by + h2 / 2;

    const r1 = Math.min(w1, h1) / 2;
    const r2 = Math.min(w2, h2) / 2;

    const dx = cx2 - cx1;
    const dy = cy2 - cy1;
    const len = Math.hypot(dx, dy);

    let x1;
    let y1;
    let x2;
    let y2;

    if (len < 1e-6) {
      x1 = cx1 + r1;
      y1 = cy1;
      x2 = cx2 - r2;
      y2 = cy2;
    } else {
      const ux = dx / len;
      const uy = dy / len;
      x1 = cx1 + ux * r1;
      y1 = cy1 + uy * r1;
      x2 = cx2 - ux * r2;
      y2 = cy2 - uy * r2;
    }

    const [p, lx, ly] = getStraightPath({
      sourceX: x1,
      sourceY: y1,
      targetX: x2,
      targetY: y2,
    });
    return { path: p, labelX: lx, labelY: ly };
  }, [sourceNode, targetNode]);

  if (!path) {
    return null;
  }

  return (
    <BaseEdge
      id={id}
      path={path}
      labelX={labelX}
      labelY={labelY}
      style={style}
      markerEnd={markerEnd}
      markerStart={markerStart}
      interactionWidth={interactionWidth}
    />
  );
}

export default memo(CircleIntersectEdge);
