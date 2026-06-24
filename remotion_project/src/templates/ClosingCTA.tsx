import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";
import { theme } from "../theme";
import type { ClosingCTAProps } from "../types";

export const ClosingCTA: React.FC<ClosingCTAProps> = ({
  heading,
  cta_text,
  links,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headingOpacity = interpolate(frame, [0, 0.6 * fps], [0, 1], {
    extrapolateRight: "clamp",
  });
  const ctaOpacity = interpolate(
    frame,
    [0.4 * fps, 1.0 * fps],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  const ctaScale = interpolate(
    frame,
    [0.4 * fps, 1.0 * fps],
    [0.9, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

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
          opacity: headingOpacity,
          textAlign: "center",
          marginBottom: 48,
        }}
      >
        <h1
          style={{
            fontSize: 64,
            color: theme.accent,
            margin: 0,
            fontWeight: 700,
          }}
        >
          {heading}
        </h1>
      </div>
      <div
        style={{
          opacity: ctaOpacity,
          transform: `scale(${ctaScale})`,
          textAlign: "center",
        }}
      >
        <div
          style={{
            display: "inline-block",
            backgroundColor: theme.accent,
            color: theme.bg,
            padding: "20px 48px",
            borderRadius: 12,
            fontSize: 32,
            fontWeight: 700,
          }}
        >
          {cta_text}
        </div>
      </div>
      {links && links.length > 0 && (
        <div
          style={{
            opacity: ctaOpacity,
            marginTop: 32,
            display: "flex",
            gap: 24,
          }}
        >
          {links.map((link, i) => (
            <p
              key={i}
              style={{
                fontSize: 22,
                color: theme.textMuted,
                margin: 0,
              }}
            >
              {link}
            </p>
          ))}
        </div>
      )}
    </AbsoluteFill>
  );
};
