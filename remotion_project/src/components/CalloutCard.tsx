import React from "react";
import { useCurrentFrame, useVideoConfig, spring, interpolate } from "remotion";
import { theme, springConfig, typography } from "../theme";

interface CalloutCardProps {
  text: string;
  x?: number;
  y?: number;
  enterFrame?: number;
}

/**
 * CalloutCard - Coral-accented "common mistake / gotcha" callout.
 *
 * 2-4 words max, used sparingly. Appears with spring physics.
 * Reserved for warnings, incorrect assumptions, key contrasts.
 */
export const CalloutCard: React.FC<CalloutCardProps> = ({
  text,
  x = 960,
  y = 540,
  enterFrame = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scale = spring({
    frame: frame - enterFrame,
    fps,
    config: springConfig,
  });

  const opacity = interpolate(frame, [enterFrame, enterFrame + 10], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <g style={{ opacity, transform: `scale(${scale})`, transformOrigin: `${x}px ${y}px` }}>
      {/* Card background */}
      <rect
        x={x - 160}
        y={y - 40}
        width={320}
        height={80}
        rx={8}
        fill={theme.bgSecondary}
        stroke={theme.accentCoral}
        strokeWidth={3}
      />
      {/* Coral accent bar */}
      <rect
        x={x - 160}
        y={y - 40}
        width={6}
        height={80}
        fill={theme.accentCoral}
      />
      {/* Text */}
      <text
        x={x}
        y={y}
        textAnchor="middle"
        dominantBaseline="central"
        style={{
          fontSize: typography.bodyM,
          fontFamily: theme.fontFamilyDisplay,
          fill: theme.accentCoral,
          fontWeight: 700,
        }}
      >
        {text}
      </text>
    </g>
  );
};
