import React from "react";
import { useCurrentFrame, useVideoConfig, spring, interpolate, Easing } from "remotion";
import { theme, springConfig, typography } from "../theme";

interface DiagramNodeProps {
  x: number;
  y: number;
  label: string;
  sublabel?: string;
  color?: string;
  enterFrame?: number;
  shape?: "circle" | "rect" | "diamond";
  size?: number;
}

/**
 * DiagramNode - A single node in a diagram/flow visualization.
 *
 * Appears with spring physics, optional annotation timing.
 * Used for: molecular structures, process steps, concept maps.
 */
export const DiagramNode: React.FC<DiagramNodeProps> = ({
  x,
  y,
  label,
  sublabel,
  color = theme.accentAmber,
  enterFrame = 0,
  shape = "circle",
  size = 120,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    frame: frame - enterFrame,
    fps,
    config: springConfig,
  });

  // Subtle breathing after entrance settles (frame 40+ after enter)
  const breathePhase = Math.max(0, frame - enterFrame - 40);
  const breathe = breathePhase > 0
    ? 1 + 0.015 * Math.sin(breathePhase * 0.04)
    : 1;

  const opacity = interpolate(frame, [enterFrame, enterFrame + 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const getPath = () => {
    const half = size / 2;
    switch (shape) {
      case "circle":
        return `M ${x - half} ${y} A ${half} ${half} 0 1 1 ${x + half} ${y} A ${half} ${half} 0 1 1 ${x - half} ${y}`;
      case "rect":
        return `M ${x - half} ${y - half * 0.7} L ${x + half} ${y - half * 0.7} L ${x + half} ${y + half * 0.7} L ${x - half} ${y + half * 0.7} Z`;
      case "diamond":
        return `M ${x} ${y - half} L ${x + half} ${y} L ${x} ${y + half} L ${x - half} ${y} Z`;
      default:
        return "";
    }
  };

  return (
    <g style={{ opacity, transform: `scale(${scale * breathe})`, transformOrigin: `${x}px ${y}px` }}>
      <path
        d={getPath()}
        fill={theme.bgSecondary}
        stroke={color}
        strokeWidth={3}
      />
      <text
        x={x}
        y={y - (sublabel ? 8 : 0)}
        textAnchor="middle"
        dominantBaseline="central"
        style={{
          fontSize: typography.monoM,
          fontFamily: theme.fontFamilyMono,
          fill: theme.chalkWhite,
          fontWeight: 600,
        }}
      >
        {label}
      </text>
      {sublabel && (
        <text
          x={x}
          y={y + 18}
          textAnchor="middle"
          dominantBaseline="central"
          style={{
            fontSize: typography.monoS,
            fontFamily: theme.fontFamilyMono,
            fill: theme.chalkDim,
          }}
        >
          {sublabel}
        </text>
      )}
    </g>
  );
};
