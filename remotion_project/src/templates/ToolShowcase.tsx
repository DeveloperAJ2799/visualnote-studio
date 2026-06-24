import React from "react";
import {
  AbsoluteFill,
  Img,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";
import { theme } from "../theme";
import type { ToolShowcaseProps } from "../types";

export const ToolShowcase: React.FC<ToolShowcaseProps> = ({
  tool_name,
  tool_logo_url,
  description,
  link,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const cardOpacity = interpolate(frame, [0, 0.6 * fps], [0, 1], {
    extrapolateRight: "clamp",
  });
  const cardScale = interpolate(frame, [0, 0.6 * fps], [0.95, 1], {
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
          opacity: cardOpacity,
          transform: `scale(${cardScale})`,
          backgroundColor: theme.bgLight,
          borderRadius: 24,
          padding: 64,
          maxWidth: 1400,
          textAlign: "center",
        }}
      >
        {tool_logo_url && (
          <Img
            src={tool_logo_url}
            style={{
              width: 120,
              height: 120,
              objectFit: "contain",
              marginBottom: 32,
              borderRadius: 16,
            }}
          />
        )}
        <h2
          style={{
            fontSize: 64,
            color: theme.accent,
            margin: "0 0 24px 0",
            fontWeight: 700,
          }}
        >
          {tool_name}
        </h2>
        <p
          style={{
            fontSize: 32,
            color: theme.text,
            lineHeight: 1.6,
            margin: "0 0 32px 0",
            maxWidth: 1000,
          }}
        >
          {description}
        </p>
        {link && (
          <p
            style={{
              fontSize: 24,
              color: theme.accentAlt,
              margin: 0,
            }}
          >
            {link}
          </p>
        )}
      </div>
    </AbsoluteFill>
  );
};
