import React from "react";
import { AbsoluteFill, spring, useCurrentFrame, interpolate, Audio } from "@remotion/react";

interface ListCascadeProps {
  title: string;
  visual_props: { items: string[] };
  audio_url?: string;
  durationInFrames: number;
}

export const ListCascade: React.FC<ListCascadeProps> = ({
  title,
  visual_props,
  audio_url,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { items } = visual_props;

  return (
    <AbsoluteFill style={{ backgroundColor: "#0F0F1A", padding: "3rem" }}>
      {audio_url && <Audio src={audio_url} />}
      <h2 style={{ color: "#FFFFFF", fontSize: "2.5rem", marginBottom: "2rem" }}>{title}</h2>
      <div style={{ position: "relative", paddingLeft: "2rem" }}>
        <div style={{
          position: "absolute",
          left: "0",
          top: "0",
          bottom: "0",
          width: "2px",
          backgroundColor: "#6366F1",
          opacity: 0.5,
        }} />
        {items?.map((item, index) => {
          const itemFrame = Math.max(0, frame - index * 15);
          const slideIn = spring({ frame: itemFrame, config: { damping: 200, stiffness: 120 } });
          const xOffset = interpolate(slideIn, [0, 1], [100, 0]);

          return (
            <div key={index} style={{
              transform: `translateX(${xOffset}px)`,
              opacity: interpolate(slideIn, [0, 1], [0, 1]),
              marginBottom: "1.5rem",
              display: "flex",
              alignItems: "flex-start",
            }}>
              <div style={{
                width: "12px",
                height: "12px",
                borderRadius: "50%",
                backgroundColor: "#6366F1",
                marginTop: "0.5rem",
                marginRight: "1rem",
                flexShrink: 0,
              }} />
              <span style={{ color: "#E0E0E0", fontSize: "1.4rem" }}>{item}</span>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};