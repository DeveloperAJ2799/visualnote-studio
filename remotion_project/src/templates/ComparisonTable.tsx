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
import type { ComparisonTableProps } from "../types";

/**
 * ComparisonTable - IGWANI comparison template.
 *
 * Clean table layout with columns and rows.
 * Spring entrance per row, staggered.
 */
export const ComparisonTable: React.FC<ComparisonTableProps> = ({
  columns,
  rows,
  annotations = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headerScale = spring({
    frame,
    fps,
    config: springConfig,
  });

  const headerOpacity = interpolate(frame, [0, 12], [0, 1], {
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
        {/* Table */}
        <div
          style={{
            opacity: headerOpacity,
            transform: `scale(${headerScale})`,
            transformOrigin: "left center",
          }}
        >
          {/* Header row */}
          <div
            style={{
              display: "flex",
              borderBottom: `2px solid ${theme.accentAmber}`,
              paddingBottom: 16,
              marginBottom: 24,
            }}
          >
            {columns.map((col, i) => (
              <div
                key={i}
                style={{
                  flex: 1,
                  fontSize: typography.bodyL,
                  fontFamily: theme.fontFamilyDisplay,
                  color: theme.accentAmber,
                  fontWeight: 600,
                }}
              >
                {col}
              </div>
            ))}
          </div>

          {/* Data rows */}
          {rows.map((row, rowIdx) => {
            const rowDelay = 20 + rowIdx * 12;
            const rowScale = spring({
              frame: frame - rowDelay,
              fps,
              config: springConfig,
            });

            const rowOpacity = interpolate(
              frame,
              [rowDelay, rowDelay + 10],
              [0, 1],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              }
            );

            return (
              <div
                key={rowIdx}
                style={{
                  opacity: rowOpacity,
                  transform: `scale(${rowScale})`,
                  transformOrigin: "left center",
                  display: "flex",
                  borderBottom: `1px solid ${theme.chalkDim}30`,
                  padding: "16px 0",
                }}
              >
                {row.map((cell, cellIdx) => (
                  <div
                    key={cellIdx}
                    style={{
                      flex: 1,
                      fontSize: typography.bodyM,
                      fontFamily: theme.fontFamilyBody,
                      color: theme.chalkWhite,
                      lineHeight: 1.5,
                    }}
                  >
                    {cell}
                  </div>
                ))}
              </div>
            );
          })}
        </div>

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
