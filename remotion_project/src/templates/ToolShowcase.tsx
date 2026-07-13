import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import { theme, springConfig, typography } from "../theme";
import { ChalkBackground } from "../components/ChalkBackground";
import { ConceptAnnotation } from "../components/ConceptAnnotation";
import type { ToolShowcaseProps } from "../types";

/**
 * ToolShowcase - IGWANI tool/platform explanation template.
 *
 * Clean layout with tool name, description, and optional link.
 * Spring entrance, one focal point.
 */
export const ToolShowcase: React.FC<ToolShowcaseProps> = ({
  tool_name,
  description,
  link,
  annotations = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleScale = spring({
    frame,
    fps,
    config: springConfig,
  });

  const titleOpacity = interpolate(frame, [0, 12], [0, 1], {
    extrapolateRight: "clamp",
  });

  const descOpacity = interpolate(frame, [15, 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const descY = interpolate(frame, [15, 30], [20, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <ChalkBackground>
      <AbsoluteFill
        style={{
          padding: theme.padding,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
        }}
      >
        {/* Tool name */}
        <div
          style={{
            opacity: titleOpacity,
            transform: `scale(${titleScale})`,
            transformOrigin: "left center",
            marginBottom: 40,
          }}
        >
          <h2
            style={{
              fontSize: typography.displayL,
              fontFamily: theme.fontFamilyDisplay,
              color: theme.accentAmber,
              margin: 0,
              fontWeight: 700,
            }}
          >
            {tool_name}
          </h2>
        </div>

        {/* Description */}
        <div
          style={{
            opacity: descOpacity,
            transform: `translateY(${descY}px)`,
            maxWidth: 1000,
          }}
        >
          <p
            style={{
              fontSize: typography.bodyL,
              fontFamily: theme.fontFamilyBody,
              color: theme.chalkWhite,
              margin: 0,
              lineHeight: 1.6,
            }}
          >
            {description}
          </p>
        </div>

        {/* Link */}
        {link && (
          <div
            style={{
              opacity: descOpacity,
              marginTop: 32,
            }}
          >
            <span
              style={{
                fontSize: typography.bodyM,
                fontFamily: theme.fontFamilyMono,
                color: theme.codeMint,
              }}
            >
              {link}
            </span>
          </div>
        )}

        {annotations.map((annotation, i) => (
          <ConceptAnnotation
            key={i}
            type={annotation.type}
            x={400}
            y={400}
            width={200}
            height={100}
            startFrame={annotation.startFrame}
            color={annotation.color}
          />
        ))}
      </AbsoluteFill>
    </ChalkBackground>
  );
};
