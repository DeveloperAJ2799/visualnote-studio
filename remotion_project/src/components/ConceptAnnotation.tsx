import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { theme } from "../theme";

/**
 * Annotation types for the signature IGWANI "teacher marking up content" effect.
 */
export type AnnotationType = "circle" | "underline" | "bracket" | "arrow";

interface ConceptAnnotationProps {
  type: AnnotationType;
  x: number;
  y: number;
  width: number;
  height: number;
  startFrame: number;
  drawDuration?: number;
  color?: string;
  strokeWidth?: number;
}

/**
 * ConceptAnnotation - The signature IGWANI component.
 *
 * SVG-based annotations that draw on with stroke-dashoffset, timed to land
 * exactly when the narration says the relevant word. This is what makes the
 * video feel like teaching instead of decoration.
 *
 * Usage:
 * <ConceptAnnotation
 *   type="circle"
 *   x={400}
 *   y={300}
 *   width={200}
 *   height={100}
 *   startFrame={30}
 * />
 */
export const ConceptAnnotation: React.FC<ConceptAnnotationProps> = ({
  type,
  x,
  y,
  width,
  height,
  startFrame,
  drawDuration = 20,
  color = theme.accentAmber,
  strokeWidth = 4,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const drawProgress = interpolate(
    frame,
    [startFrame, startFrame + drawDuration],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    }
  );

  const pathData = getPathData(type, x, y, width, height);
  const pathLength = estimatePathLength(type, width, height);
  const dashOffset = pathLength * (1 - drawProgress);

  return (
    <svg
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
      }}
    >
      <path
        d={pathData}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={pathLength}
        strokeDashoffset={dashOffset}
      />
    </svg>
  );
};

/**
 * Generate SVG path data for each annotation type.
 */
function getPathData(
  type: AnnotationType,
  x: number,
  y: number,
  width: number,
  height: number
): string {
  switch (type) {
    case "circle": {
      const cx = x + width / 2;
      const cy = y + height / 2;
      const rx = width / 2 + 10;
      const ry = height / 2 + 10;
      return `M ${cx - rx} ${cy} 
              A ${rx} ${ry} 0 1 1 ${cx + rx} ${cy}
              A ${rx} ${ry} 0 1 1 ${cx - rx} ${cy}`;
    }
    case "underline":
      return `M ${x} ${y + height + 8} 
              Q ${x + width * 0.25} ${y + height + 20} ${x + width * 0.5} ${y + height + 8}
              Q ${x + width * 0.75} ${y + height - 4} ${x + width} ${y + height + 8}`;
    case "bracket":
      return `M ${x - 12} ${y - 8} 
              L ${x - 20} ${y - 8}
              L ${x - 20} ${y + height + 8}
              L ${x - 12} ${y + height + 8}`;
    case "arrow":
      return `M ${x} ${y + height / 2} 
              L ${x + width} ${y + height / 2}
              M ${x + width - 12} ${y + height / 2 - 8}
              L ${x + width} ${y + height / 2}
              L ${x + width - 12} ${y + height / 2 + 8}`;
    default:
      return "";
  }
}

/**
 * Estimate path length for stroke-dashoffset animation.
 */
function estimatePathLength(
  type: AnnotationType,
  width: number,
  height: number
): number {
  switch (type) {
    case "circle":
      return Math.PI * (width + height) + 40;
    case "underline":
      return width * 1.2;
    case "bracket":
      return height + 40;
    case "arrow":
      return width + 24;
    default:
      return width;
  }
}
