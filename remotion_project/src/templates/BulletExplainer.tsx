import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";
import { theme } from "../theme";
import type { BulletExplainerProps } from "../types";

export const BulletExplainer: React.FC<BulletExplainerProps> = ({
  heading,
  bullets,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headingOpacity = interpolate(frame, [0, 0.5 * fps], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.bg,
        padding: theme.padding,
        fontFamily: theme.fontFamily,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
      }}
    >
      <h2
        style={{
          fontSize: 56,
          color: theme.accent,
          margin: "0 0 48px 0",
          opacity: headingOpacity,
          fontWeight: 700,
        }}
      >
        {heading}
      </h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        {bullets.map((bullet, i) => {
          const delay = 0.3 * fps + i * 0.2 * fps;
          const bulletOpacity = interpolate(
            frame,
            [delay, delay + 0.4 * fps],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );
          const bulletX = interpolate(
            frame,
            [delay, delay + 0.4 * fps],
            [-20, 0],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );
          return (
            <div
              key={i}
              style={{
                opacity: bulletOpacity,
                transform: `translateX(${bulletX}px)`,
                display: "flex",
                alignItems: "flex-start",
                gap: 16,
              }}
            >
              <span
                style={{
                  fontSize: 36,
                  color: theme.yellow,
                  fontWeight: 700,
                  minWidth: 40,
                }}
              >
                {i + 1}.
              </span>
              <span
                style={{
                  fontSize: 32,
                  color: theme.text,
                  lineHeight: 1.5,
                }}
              >
                {bullet}
              </span>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
