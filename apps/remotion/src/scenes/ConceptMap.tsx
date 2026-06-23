import React from "react";
import { AbsoluteFill, spring, useCurrentFrame, interpolate, Audio } from "@remotion/react";

interface ConceptMapProps {
  visual_props: { primary_text: string; items: string[] };
  audio_url?: string;
  durationInFrames: number;
}

export const ConceptMap: React.FC<ConceptMapProps> = ({
  visual_props,
  audio_url,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { primary_text, items } = visual_props;

  const centerSpring = spring({ frame, config: { damping: 150, stiffness: 100 } });
  const lineProgress = interpolate(frame, [10, 60], [0, 1], { extrapolateRight: "clamp" });

  const centerScale = interpolate(centerSpring, [0, 1], [0, 1]);
  const centerOpacity = interpolate(centerSpring, [0, 1], [0, 1]);

  const centerX = 400;
  const centerY = 300;
  const radius = 150;
  const nodePositions = items?.map((_, i) => {
    const angle = (i / (items?.length || 1)) * 2 * Math.PI - Math.PI / 2;
    return {
      x: centerX + radius * Math.cos(angle),
      y: centerY + radius * Math.sin(angle),
    };
  }) || [];

  return (
    <AbsoluteFill style={{ backgroundColor: "#0F0F1A" }}>
      {audio_url && <Audio src={audio_url} />}
      <svg width="800" height="600" style={{ position: "absolute", inset: 0 }}>
        {nodePositions.map((pos, i) => {
          const itemSpring = spring({ frame: Math.max(0, frame - 20 - i * 10), config: { damping: 150, stiffness: 100 } });
          const nodeOpacity = interpolate(itemSpring, [0, 1], [0, 1]);
          const nodeScale = interpolate(itemSpring, [0, 1], [0.5, 1]);

          const lineLength = Math.sqrt(
            Math.pow(pos.x - centerX, 2) + Math.pow(pos.y - centerY, 2)
          );
          const dashOffset = interpolate(lineProgress, [0, 1], [lineLength, 0]);

          const angle = Math.atan2(pos.y - centerY, pos.x - centerX);
          const lineX2 = centerX + (radius - 30) * Math.cos(angle);
          const lineY2 = centerY + (radius - 30) * Math.sin(angle);

          return (
            <React.Fragment key={i}>
              <line
                x1={centerX}
                y1={centerY}
                x2={lineX2}
                y2={lineY2}
                stroke="#6366F1"
                strokeWidth="2"
                style={{
                  strokeDasharray: lineLength,
                  strokeDashoffset: dashOffset,
                }}
              />
              <circle
                cx={pos.x}
                cy={pos.y}
                r={25 * nodeScale}
                fill="#1E1E3F"
                stroke="#6366F1"
                strokeWidth="2"
                opacity={nodeOpacity}
              />
              <text
                x={pos.x}
                y={pos.y + 50}
                textAnchor="middle"
                fill="#A0A0B0"
                fontSize="12"
                opacity={nodeOpacity}
              >
                {items?.[i]?.slice(0, 15)}
              </text>
            </React.Fragment>
          );
        })}
        <circle
          cx={centerX}
          cy={centerY}
          r={40 * centerScale}
          fill="#6366F1"
          opacity={centerOpacity}
        />
        <text
          x={centerX}
          y={centerY + 5}
          textAnchor="middle"
          fill="#FFFFFF"
          fontSize="14"
          fontWeight="bold"
        >
          {primary_text?.slice(0, 10)}
        </text>
      </svg>
    </AbsoluteFill>
  );
};