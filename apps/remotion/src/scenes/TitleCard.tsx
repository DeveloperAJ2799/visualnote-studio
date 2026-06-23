import React from "react";
import { AbsoluteFill, spring, useCurrentFrame, interpolate, Audio } from "@remotion/react";

interface TitleCardProps {
  title: string;
  visual_props: { primary_text?: string };
  audio_url?: string;
  durationInFrames: number;
}

export const TitleCard: React.FC<TitleCardProps> = ({
  title,
  visual_props,
  audio_url,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const primaryText = visual_props?.primary_text || "";

  const slideUp = spring({ frame, config: { damping: 200, stiffness: 100 } });
  const accentProgress = interpolate(frame, [0, 30], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0F0F1A", justifyContent: "center", alignItems: "center" }}>
      {audio_url && <Audio src={audio_url} />}
      <div style={{
        position: "absolute",
        top: "50%",
        left: "10%",
        right: "10%",
        transform: `translateY(${interpolate(slideUp, [0, 1], [100, 0])}px)`,
        opacity: interpolate(slideUp, [0, 1], [0, 1]),
      }}>
        <h1 style={{
          color: "#FFFFFF",
          fontSize: "4rem",
          fontWeight: 700,
          margin: 0,
          textAlign: "center",
          fontFamily: "Arial, sans-serif",
        }}>
          {title}
        </h1>
        {primaryText && (
          <p style={{
            color: "#A0A0B0",
            fontSize: "1.5rem",
            marginTop: "1rem",
            textAlign: "center",
            fontFamily: "Arial, sans-serif",
          }}>
            {primaryText}
          </p>
        )}
      </div>
      <div style={{
        position: "absolute",
        top: "50%",
        left: "5%",
        width: interpolate(accentProgress, [0, 1], [0, 90], { extrapolateRight: "clamp" }) + "%",
        height: "2px",
        backgroundColor: "#6366F1",
      }} />
    </AbsoluteFill>
  );
};