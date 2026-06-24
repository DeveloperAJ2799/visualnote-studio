import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { theme } from "../theme";
import type { TitleIntroProps } from "../types";

export const TitleIntro: React.FC<TitleIntroProps> = ({ title, subtitle }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleOpacity = interpolate(frame, [0, 0.8 * fps], [0, 1], {
    extrapolateRight: "clamp",
  });
  const titleY = interpolate(frame, [0, 0.8 * fps], [30, 0], {
    extrapolateRight: "clamp",
  });
  const subtitleOpacity = interpolate(
    frame,
    [0.4 * fps, 1.2 * fps],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const barWidth = interpolate(frame, [0.2 * fps, 1.0 * fps], [0, 200], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        justifyContent: "center",
        alignItems: "center",
        fontFamily: theme.fontFamily,
      }}
    >
      <div
        style={{
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          textAlign: "center",
        }}
      >
        <h1
          style={{
            fontSize: 72,
            color: theme.accent,
            margin: 0,
            fontWeight: 700,
          }}
        >
          {title}
        </h1>
      </div>
      <div
        style={{
          width: barWidth,
          height: 4,
          backgroundColor: theme.accent,
          marginTop: 24,
          marginBottom: 24,
          borderRadius: 2,
        }}
      />
      {subtitle && (
        <div style={{ opacity: subtitleOpacity, textAlign: "center" }}>
          <p
            style={{
              fontSize: 32,
              color: theme.textMuted,
              margin: 0,
              fontWeight: 400,
            }}
          >
            {subtitle}
          </p>
        </div>
      )}
    </AbsoluteFill>
  );
};
