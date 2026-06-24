import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";
import { theme } from "../theme";
import type { ComparisonTableProps } from "../types";

export const ComparisonTable: React.FC<ComparisonTableProps> = ({
  columns,
  rows,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headerOpacity = interpolate(frame, [0, 0.4 * fps], [0, 1], {
    extrapolateRight: "clamp",
  });

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
          gap: 4,
          marginBottom: 4,
          opacity: headerOpacity,
        }}
      >
        {columns.map((col, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              backgroundColor: theme.accent,
              color: theme.bg,
              padding: "20px 24px",
              fontSize: 28,
              fontWeight: 700,
              textAlign: "center",
              borderRadius: i === 0 ? "12px 0 0 0" : i === columns.length - 1 ? "0 12px 0 0" : 0,
            }}
          >
            {col}
          </div>
        ))}
      </div>
      {rows.map((row, ri) => {
        const rowDelay = 0.3 * fps + ri * 0.15 * fps;
        const rowOpacity = interpolate(
          frame,
          [rowDelay, rowDelay + 0.3 * fps],
          [0, 1],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        );
        return (
          <div
            key={ri}
            style={{
              display: "flex",
              gap: 4,
              marginBottom: 4,
              opacity: rowOpacity,
            }}
          >
            {row.map((cell, ci) => (
              <div
                key={ci}
                style={{
                  flex: 1,
                  backgroundColor:
                    ri % 2 === 0 ? theme.bgLight : "rgba(255,255,255,0.05)",
                  color: ci === 0 ? theme.text : theme.text,
                  padding: "18px 24px",
                  fontSize: 26,
                  textAlign: "center",
                  borderRadius:
                    ri === rows.length - 1 && ci === 0
                      ? "0 0 0 12px"
                      : ri === rows.length - 1 && ci === row.length - 1
                      ? "0 0 12px 0"
                      : 0,
                }}
              >
                {cell}
              </div>
            ))}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
