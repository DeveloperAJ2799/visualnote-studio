import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";
import { theme } from "../theme";
import type { StepProcessProps } from "../types";

export const StepProcess: React.FC<StepProcessProps> = ({ steps }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

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
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 0,
          justifyContent: "center",
        }}
      >
        {steps.map((step, i) => {
          const delay = 0.2 * fps + i * 0.25 * fps;
          const stepOpacity = interpolate(
            frame,
            [delay, delay + 0.4 * fps],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );
          const stepY = interpolate(
            frame,
            [delay, delay + 0.4 * fps],
            [20, 0],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );
          const isLast = i === steps.length - 1;
          return (
            <React.Fragment key={i}>
              <div
                style={{
                  opacity: stepOpacity,
                  transform: `translateY(${stepY}px)`,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  width: 240,
                }}
              >
                <div
                  style={{
                    width: 64,
                    height: 64,
                    borderRadius: "50%",
                    backgroundColor: theme.accent,
                    color: theme.bg,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 28,
                    fontWeight: 700,
                    marginBottom: 16,
                  }}
                >
                  {i + 1}
                </div>
                <p
                  style={{
                    fontSize: 26,
                    color: theme.text,
                    fontWeight: 600,
                    margin: "0 0 8px 0",
                    textAlign: "center",
                  }}
                >
                  {step.label}
                </p>
                {step.description && (
                  <p
                    style={{
                      fontSize: 20,
                      color: theme.textMuted,
                      margin: 0,
                      textAlign: "center",
                      lineHeight: 1.4,
                    }}
                  >
                    {step.description}
                  </p>
                )}
              </div>
              {!isLast && (
                <div
                  style={{
                    opacity: stepOpacity,
                    width: 80,
                    height: 3,
                    backgroundColor: theme.accent,
                    marginTop: 30,
                    borderRadius: 2,
                  }}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
