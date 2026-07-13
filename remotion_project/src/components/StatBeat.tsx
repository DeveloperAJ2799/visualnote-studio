import React from "react";
import { useCurrentFrame, useVideoConfig, spring, interpolate } from "remotion";
import { theme, springConfig, typography } from "../theme";
import { ConceptAnnotation } from "./ConceptAnnotation";

interface StatBeatProps {
  number: string;
  label: string;
  annotationCircle?: { x: number; y: number; width: number; height: number };
  enterFrame?: number;
  annotationFrame?: number;
}

/**
 * StatBeat - A single number that matters.
 *
 * Big display number + amber annotation circling the part that matters.
 * Not a generic "big number + small label" template.
 */
export const StatBeat: React.FC<StatBeatProps> = ({
  number,
  label,
  annotationCircle,
  enterFrame = 0,
  annotationFrame = 30,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    frame: frame - enterFrame,
    fps,
    config: springConfig,
  });

  const opacity = interpolate(frame, [enterFrame, enterFrame + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <g style={{ opacity, transform: `scale(${scale})`, transformOrigin: "960px 540px" }}>
      {/* Big number */}
      <text
        x={960}
        y={500}
        textAnchor="middle"
        dominantBaseline="central"
        style={{
          fontSize: 160,
          fontFamily: theme.fontFamilyDisplay,
          fill: theme.chalkWhite,
          fontWeight: 800,
        }}
      >
        {number}
      </text>
      {/* Label */}
      <text
        x={960}
        y={600}
        textAnchor="middle"
        dominantBaseline="central"
        style={{
          fontSize: typography.bodyL,
          fontFamily: theme.fontFamilyBody,
          fill: theme.chalkDim,
        }}
      >
        {label}
      </text>
      {/* Annotation circle */}
      {annotationCircle && (
        <ConceptAnnotation
          type="circle"
          x={annotationCircle.x}
          y={annotationCircle.y}
          width={annotationCircle.width}
          height={annotationCircle.height}
          startFrame={annotationFrame}
        />
      )}
    </g>
  );
};
