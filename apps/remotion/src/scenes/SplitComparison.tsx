import React from "react";
import { AbsoluteFill, spring, useCurrentFrame, interpolate, Audio } from "@remotion/react";

interface SplitComparisonProps {
  visual_props: { primary_text: string; secondary_text: string; items: string[] };
  audio_url?: string;
  durationInFrames: number;
}

export const SplitComparison: React.FC<SplitComparisonProps> = ({
  visual_props,
  audio_url,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { primary_text, secondary_text, items } = visual_props;

  const leftSlide = spring({ frame, config: { damping: 200, stiffness: 90 } });
  const rightSlide = spring({ frame, config: { damping: 200, stiffness: 90, mass: 1.2 } });

  const leftX = interpolate(leftSlide, [0, 1], [-500, 0]);
  const rightX = interpolate(rightSlide, [0, 1], [500, 0]);

  return (
    <AbsoluteFill style={{ backgroundColor: "#1A1A2E", flexDirection: "row" }}>
      {audio_url && <Audio src={audio_url} />}
      <div style={{
        flex: 1,
        backgroundColor: "#16213E",
        transform: `translateX(${leftX}px)`,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "2rem",
      }}>
        <h2 style={{ color: "#60A5FA", fontSize: "2rem", margin: "0 0 1rem 0" }}>{primary_text}</h2>
        {items?.slice(0, Math.ceil((items?.length || 0) / 2)).map((item, i) => (
          <div key={i} style={{ color: "#E0E0E0", fontSize: "1.2rem", marginBottom: "0.5rem" }}>
            • {item}
          </div>
        ))}
      </div>
      <div style={{
        flex: 1,
        backgroundColor: "#1F1F3D",
        transform: `translateX(${rightX}px)`,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "2rem",
      }}>
        <h2 style={{ color: "#F472B6", fontSize: "2rem", margin: "0 0 1rem 0" }}>{secondary_text}</h2>
        {items?.slice(Math.ceil((items?.length || 0) / 2)).map((item, i) => (
          <div key={i} style={{ color: "#E0E0E0", fontSize: "1.2rem", marginBottom: "0.5rem" }}>
            • {item}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};