import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { theme } from "../theme";

interface DiagramConnectorProps {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  drawFrame?: number;
  drawDuration?: number;
  color?: string;
  label?: string;
  dashed?: boolean;
}

/**
 * DiagramConnector - Animated line connecting two diagram nodes.
 *
 * Draws on with stroke-dashoffset, timed to narration.
 * Used for: arrows, flow lines, relationships between concepts.
 */
export const DiagramConnector: React.FC<DiagramConnectorProps> = ({
  x1,
  y1,
  x2,
  y2,
  drawFrame = 0,
  drawDuration = 20,
  color = theme.chalkDim,
  label,
  dashed = false,
}) => {
  const frame = useCurrentFrame();

  const drawProgress = interpolate(
    frame,
    [drawFrame, drawFrame + drawDuration],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    }
  );

  const pathLength = Math.sqrt(Math.pow(x2 - x1, 2) + Math.pow(y2 - y1, 2));
  const dashOffset = pathLength * (1 - drawProgress);

  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;

  return (
    <g>
      <line
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        stroke={color}
        strokeWidth={2}
        strokeDasharray={dashed ? "8,6" : undefined}
        style={{
          strokeDasharray: dashed ? undefined : pathLength,
          strokeDashoffset: dashed ? undefined : dashOffset,
        }}
      />
      {/* Arrow head */}
      <polygon
        points={`${x2},${y2} ${x2 - 10},${y2 - 6} ${x2 - 10},${y2 + 6}`}
        fill={color}
        style={{ opacity: drawProgress }}
      />
      {label && (
        <text
          x={midX}
          y={midY - 12}
          textAnchor="middle"
          style={{
            fontSize: 18,
            fontFamily: theme.fontFamilyHand,
            fill: theme.accentAmber,
            opacity: drawProgress,
          }}
        >
          {label}
        </text>
      )}
    </g>
  );
};
