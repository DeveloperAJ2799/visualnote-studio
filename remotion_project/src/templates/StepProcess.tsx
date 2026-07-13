import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
  Easing,
} from "remotion";
import { theme, springConfig, typography } from "../theme";
import { ChalkBackground } from "../components/ChalkBackground";
import { ConceptAnnotation } from "../components/ConceptAnnotation";
import type { StepProcessProps } from "../types";

/**
 * StepProcess - IGWANI process/flow template.
 *
 * Steps as connected flow, not numbered list.
 * Connectors draw on with stroke animation.
 * Only uses numbering if it's a real sequence.
 * Spring entrance per step with 10-frame offset.
 */
export const StepProcess: React.FC<StepProcessProps> = ({
  steps,
  annotations = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

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
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 0,
          }}
        >
          {steps.map((step, i) => {
            const stepDelay = 15 + i * 15;
            const isLast = i === steps.length - 1;

            // Step entrance
            const stepScale = spring({
              frame: frame - stepDelay,
              fps,
              config: springConfig,
            });

            const stepOpacity = interpolate(
              frame,
              [stepDelay, stepDelay + 10],
              [0, 1],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }
            );

            // Connector draw-on (not for last step)
            const connectorDelay = stepDelay + 12;
            const connectorProgress = isLast
              ? 0
              : interpolate(
                  frame,
                  [connectorDelay, connectorDelay + 15],
                  [0, 1],
                  {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                    easing: Easing.out(Easing.cubic),
                  }
                );

            return (
              <div key={i}>
                {/* Step content */}
                <div
                  style={{
                    opacity: stepOpacity,
                    transform: `scale(${stepScale})`,
                    transformOrigin: "left center",
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 24,
                  }}
                >
                  {/* Step number circle */}
                  <div
                    style={{
                      width: 48,
                      height: 48,
                      borderRadius: "50%",
                      backgroundColor: theme.accentAmber,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <span
                      style={{
                        fontSize: typography.monoM,
                        fontFamily: theme.fontFamilyMono,
                        color: theme.bgPrimary,
                        fontWeight: 600,
                      }}
                    >
                      {i + 1}
                    </span>
                  </div>

                  {/* Step text */}
                  <div style={{ flex: 1 }}>
                    <h3
                      style={{
                        fontSize: typography.bodyL,
                        fontFamily: theme.fontFamilyDisplay,
                        color: theme.chalkWhite,
                        margin: 0,
                        fontWeight: 600,
                        lineHeight: 1.3,
                      }}
                    >
                      {step.label}
                    </h3>
                    {step.description && (
                      <p
                        style={{
                          fontSize: typography.bodyM,
                          fontFamily: theme.fontFamilyBody,
                          color: theme.chalkDim,
                          margin: "8px 0 0 0",
                          lineHeight: 1.5,
                        }}
                      >
                        {step.description}
                      </p>
                    )}
                  </div>
                </div>

                {/* Connector line */}
                {!isLast && (
                  <div
                    style={{
                      display: "flex",
                      paddingLeft: 23,
                      height: 40,
                    }}
                  >
                    <svg
                      style={{
                        width: 2,
                        height: "100%",
                      }}
                    >
                      <line
                        x1={1}
                        y1={0}
                        x2={1}
                        y2={40}
                        stroke={theme.chalkDim}
                        strokeWidth={2}
                        strokeDasharray={40}
                        strokeDashoffset={40 * (1 - connectorProgress)}
                        opacity={0.4}
                      />
                    </svg>
                  </div>
                )}
              </div>
            );
          })}
        </div>

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
