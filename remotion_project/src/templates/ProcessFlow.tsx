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
import { DiagramNode } from "../components/DiagramNode";
import { DiagramConnector } from "../components/DiagramConnector";
import { ConceptAnnotation } from "../components/ConceptAnnotation";
import type { Annotation } from "../types";

interface ProcessStep {
  label: string;
  sublabel?: string;
  x: number;
  y: number;
  enterFrame: number;
}

interface ProcessFlowProps {
  title: string;
  steps: ProcessStep[];
  annotations?: Annotation[];
}

/**
 * ProcessFlow - Sequential process visualization.
 *
 * Steps appear left-to-right or top-to-bottom with connecting arrows.
 * Each step has a spring entrance, connectors draw on.
 * No bullet lists — visual flow only.
 */
export const ProcessFlow: React.FC<ProcessFlowProps> = ({
  title,
  steps,
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

  return (
    <ChalkBackground>
      <AbsoluteFill
        style={{
          padding: theme.padding,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Title */}
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
              fontSize: typography.displayM,
              fontFamily: theme.fontFamilyDisplay,
              color: theme.chalkWhite,
              margin: 0,
              fontWeight: 700,
            }}
          >
            {title}
          </h2>
        </div>

        {/* Process flow */}
        <svg
          style={{
            position: "absolute",
            top: 140,
            left: theme.padding,
            width: theme.width - theme.padding * 2,
            height: theme.height - 180,
          }}
        >
          {/* Connectors */}
          {steps.slice(0, -1).map((step, i) => (
            <DiagramConnector
              key={`conn-${i}`}
              x1={step.x + 80}
              y1={step.y}
              x2={steps[i + 1].x - 80}
              y2={steps[i + 1].y}
              drawFrame={step.enterFrame + 15}
              color={theme.chalkDim}
            />
          ))}

          {/* Steps */}
          {steps.map((step, i) => (
            <DiagramNode
              key={`step-${i}`}
              x={step.x}
              y={step.y}
              label={step.label}
              sublabel={step.sublabel}
              enterFrame={step.enterFrame}
              shape="rect"
              size={140}
            />
          ))}
        </svg>

        {/* Manual annotations */}
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
