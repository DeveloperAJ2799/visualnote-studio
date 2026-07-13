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
import type { TitleIntroProps } from "../types";

/**
 * TitleIntro - IGWANI lesson/section opener.
 *
 * Display type, one amber underline-draw on the key term, generous negative space.
 * Spring entrance for title, delayed subtitle.
 */
export const TitleIntro: React.FC<TitleIntroProps> = ({
  title,
  subtitle,
  annotations = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Title entrance with spring
  const titleScale = spring({
    frame,
    fps,
    config: springConfig,
  });

  const titleOpacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Subtitle delayed entrance
  const subtitleOpacity = interpolate(frame, [20, 35], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const subtitleY = interpolate(frame, [20, 35], [20, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Amber underline draw-on for emphasis
  const underlineProgress = interpolate(frame, [25, 45], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <ChalkBackground>
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "flex-start",
          padding: theme.padding,
        }}
      >
        {/* Title with spring entrance */}
        <div
          style={{
            opacity: titleOpacity,
            transform: `scale(${titleScale})`,
            transformOrigin: "left center",
          }}
        >
          <h1
            style={{
              fontSize: typography.displayXL,
              fontFamily: theme.fontFamilyDisplay,
              color: theme.chalkWhite,
              margin: 0,
              fontWeight: 700,
              lineHeight: 1.1,
              maxWidth: 1200,
            }}
          >
            {title}
          </h1>

          {/* Amber underline annotation */}
          <svg
            style={{
              position: "absolute",
              bottom: -8,
              left: 0,
              width: "100%",
              height: 20,
              pointerEvents: "none",
            }}
          >
            <path
              d="M 0 10 Q 100 18 200 10 Q 300 2 400 10"
              fill="none"
              stroke={theme.accentAmber}
              strokeWidth={4}
              strokeLinecap="round"
              strokeDasharray={400}
              strokeDashoffset={400 * (1 - underlineProgress)}
            />
          </svg>
        </div>

        {/* Subtitle with delayed entrance */}
        {subtitle && (
          <div
            style={{
              opacity: subtitleOpacity,
              transform: `translateY(${subtitleY}px)`,
              marginTop: 40,
            }}
          >
            <p
              style={{
                fontSize: typography.bodyL,
                fontFamily: theme.fontFamilyBody,
                color: theme.chalkDim,
                margin: 0,
                fontWeight: 400,
                maxWidth: 800,
              }}
            >
              {subtitle}
            </p>
          </div>
        )}

        {/* Manual annotations from manifest */}
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
