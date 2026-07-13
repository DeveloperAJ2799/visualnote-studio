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

interface ComparisonItem {
  label: string;
  sublabel?: string;
  color?: string;
}

interface ComparisonVisualProps {
  title: string;
  leftLabel: string;
  rightLabel: string;
  leftItems: ComparisonItem[];
  rightItems: ComparisonItem[];
  annotations?: Annotation[];
}

/**
 * ComparisonVisual - Side-by-side comparison without bullet lists.
 *
 * Two columns with nodes appearing sequentially.
 * Visual contrast, not text comparison.
 */
export const ComparisonVisual: React.FC<ComparisonVisualProps> = ({
  title,
  leftLabel,
  rightLabel,
  leftItems,
  rightItems,
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

  // Column positions
  const leftX = 360;
  const rightX = 1560;
  const startY = 280;
  const itemSpacing = 120;

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
            marginBottom: 20,
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

        {/* Column headers */}
        <div
          style={{
            position: "absolute",
            top: 160,
            left: 0,
            width: "100%",
            display: "flex",
            justifyContent: "space-around",
          }}
        >
          <span
            style={{
              fontSize: typography.bodyL,
              fontFamily: theme.fontFamilyDisplay,
              color: theme.accentAmber,
              fontWeight: 700,
            }}
          >
            {leftLabel}
          </span>
          <span
            style={{
              fontSize: typography.bodyL,
              fontFamily: theme.fontFamilyDisplay,
              color: theme.accentAmber,
              fontWeight: 700,
            }}
          >
            {rightLabel}
          </span>
        </div>

        {/* Comparison diagram */}
        <svg
          style={{
            position: "absolute",
            top: 200,
            left: theme.padding,
            width: theme.width - theme.padding * 2,
            height: theme.height - 240,
          }}
        >
          {/* Left column */}
          {leftItems.map((item, i) => (
            <DiagramNode
              key={`left-${i}`}
              x={leftX}
              y={startY + i * itemSpacing}
              label={item.label}
              sublabel={item.sublabel}
              color={item.color || theme.chalkWhite}
              enterFrame={20 + i * 12}
              shape="rect"
              size={160}
            />
          ))}

          {/* Right column */}
          {rightItems.map((item, i) => (
            <DiagramNode
              key={`right-${i}`}
              x={rightX}
              y={startY + i * itemSpacing}
              label={item.label}
              sublabel={item.sublabel}
              color={item.color || theme.chalkWhite}
              enterFrame={30 + i * 12}
              shape="rect"
              size={160}
            />
          ))}

          {/* Center divider */}
          <line
            x1={960}
            y1={240}
            x2={960}
            y2={800}
            stroke={theme.chalkDim}
            strokeWidth={1}
            strokeDasharray="4,8"
          />
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
