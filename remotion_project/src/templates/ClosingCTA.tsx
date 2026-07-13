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
import type { ClosingCTAProps } from "../types";

/**
 * ClosingCTA - IGWANI closing/cta template.
 *
 * Clean closing with heading, CTA text, and optional links.
 * Amber accent, generous negative space.
 */
export const ClosingCTA: React.FC<ClosingCTAProps> = ({
  heading,
  cta_text,
  links = [],
  annotations = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headingScale = spring({
    frame,
    fps,
    config: springConfig,
  });

  const headingOpacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: "clamp",
  });

  const ctaOpacity = interpolate(frame, [20, 35], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const ctaY = interpolate(frame, [20, 35], [20, 0], {
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
          alignItems: "center",
        }}
      >
        {/* Heading */}
        <div
          style={{
            opacity: headingOpacity,
            transform: `scale(${headingScale})`,
            marginBottom: 40,
          }}
        >
          <h2
            style={{
              fontSize: typography.displayL,
              fontFamily: theme.fontFamilyDisplay,
              color: theme.chalkWhite,
              margin: 0,
              fontWeight: 700,
              textAlign: "center",
            }}
          >
            {heading}
          </h2>
        </div>

        {/* CTA text */}
        <div
          style={{
            opacity: ctaOpacity,
            transform: `translateY(${ctaY}px)`,
          }}
        >
          <p
            style={{
              fontSize: typography.bodyL,
              fontFamily: theme.fontFamilyBody,
              color: theme.accentAmber,
              margin: 0,
              fontWeight: 500,
            }}
          >
            {cta_text}
          </p>
        </div>

        {/* Links */}
        {links.length > 0 && (
          <div
            style={{
              opacity: ctaOpacity,
              marginTop: 40,
              display: "flex",
              gap: 32,
            }}
          >
            {links.map((link, i) => (
              <span
                key={i}
                style={{
                  fontSize: typography.bodyM,
                  fontFamily: theme.fontFamilyMono,
                  color: theme.codeMint,
                }}
              >
                {link}
              </span>
            ))}
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
