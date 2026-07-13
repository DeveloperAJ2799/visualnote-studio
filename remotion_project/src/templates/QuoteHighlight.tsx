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
import type { QuoteHighlightProps } from "../types";

/**
 * QuoteHighlight - IGWANI quote/key insight template.
 *
 * Large quote text with attribution.
 * Amber accent on the quote marks, generous negative space.
 */
export const QuoteHighlight: React.FC<QuoteHighlightProps> = ({
  quote_text,
  attribution,
  annotations = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const quoteScale = spring({
    frame,
    fps,
    config: springConfig,
  });

  const quoteOpacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: "clamp",
  });

  const attrOpacity = interpolate(frame, [25, 40], [0, 1], {
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
          alignItems: "flex-start",
        }}
      >
        {/* Quote mark */}
        <div
          style={{
            opacity: quoteOpacity,
            transform: `scale(${quoteScale})`,
            fontSize: 120,
            fontFamily: theme.fontFamilyDisplay,
            color: theme.accentAmber,
            lineHeight: 1,
            marginBottom: -20,
          }}
        >
          "
        </div>

        {/* Quote text */}
        <div
          style={{
            opacity: quoteOpacity,
            transform: `scale(${quoteScale})`,
            transformOrigin: "left center",
            maxWidth: 1200,
          }}
        >
          <p
            style={{
              fontSize: typography.displayM,
              fontFamily: theme.fontFamilyDisplay,
              color: theme.chalkWhite,
              margin: 0,
              fontWeight: 500,
              lineHeight: 1.3,
              fontStyle: "italic",
            }}
          >
            {quote_text}
          </p>
        </div>

        {/* Attribution */}
        {attribution && (
          <div
            style={{
              opacity: attrOpacity,
              marginTop: 32,
            }}
          >
            <span
              style={{
                fontSize: typography.bodyM,
                fontFamily: theme.fontFamilyBody,
                color: theme.chalkDim,
              }}
            >
              — {attribution}
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
