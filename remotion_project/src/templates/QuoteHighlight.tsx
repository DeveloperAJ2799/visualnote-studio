import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";
import { theme } from "../theme";
import type { QuoteHighlightProps } from "../types";

export const QuoteHighlight: React.FC<QuoteHighlightProps> = ({
  quote_text,
  attribution,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const quoteOpacity = interpolate(frame, [0, 0.6 * fps], [0, 1], {
    extrapolateRight: "clamp",
  });
  const quoteY = interpolate(frame, [0, 0.6 * fps], [20, 0], {
    extrapolateRight: "clamp",
  });
  const attrOpacity = interpolate(
    frame,
    [0.5 * fps, 1.0 * fps],
    [0, 1],
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
          opacity: quoteOpacity,
          transform: `translateY(${quoteY}px)`,
          maxWidth: 1200,
          textAlign: "center",
          position: "relative",
          padding: "0 64px",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: 0,
            top: -20,
            fontSize: 120,
            color: theme.accent,
            opacity: 0.3,
            fontFamily: "Georgia, serif",
            lineHeight: 1,
          }}
        >
          {"\u201C"}
        </div>
        <p
          style={{
            fontSize: 44,
            color: theme.text,
            fontStyle: "italic",
            lineHeight: 1.6,
            margin: 0,
          }}
        >
          {quote_text}
        </p>
      </div>
      {attribution && (
        <div style={{ opacity: attrOpacity, marginTop: 32 }}>
          <p
            style={{
              fontSize: 24,
              color: theme.textMuted,
              margin: 0,
            }}
          >
            {"\u2014 "}{attribution}
          </p>
        </div>
      )}
    </AbsoluteFill>
  );
};
