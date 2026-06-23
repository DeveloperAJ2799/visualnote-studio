import React from "react";
import { AbsoluteFill, spring, useCurrentFrame, interpolate, Audio } from "@remotion/react";

interface DataCalloutProps {
  visual_props: { metric: string; primary_text: string };
  audio_url?: string;
  durationInFrames: number;
}

export const DataCallout: React.FC<DataCalloutProps> = ({
  visual_props,
  audio_url,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { metric, primary_text } = visual_props;

  const scaleSpring = spring({ frame, config: { damping: 100, stiffness: 80 } });
  const scale = interpolate(scaleSpring, [0, 1], [0.5, 1.2]);
  const fadeIn = interpolate(frame, [0, 40], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{
      backgroundColor: "#0F0F1A",
      justifyContent: "center",
      alignItems: "center",
      flexDirection: "column",
    }}>
      {audio_url && <Audio src={audio_url} />}
      <div style={{
        transform: `scale(${scale})`,
        textAlign: "center",
      }}>
        <div style={{
          color: "#6366F1",
          fontSize: "8rem",
          fontWeight: 800,
          lineHeight: 1,
          fontFamily: "Arial Black, sans-serif",
        }}>
          {metric}
        </div>
      </div>
      <div style={{
        opacity: fadeIn,
        marginTop: "1.5rem",
        textAlign: "center",
        maxWidth: "80%",
      }}>
        <p style={{
          color: "#A0A0B0",
          fontSize: "2rem",
          margin: 0,
          fontFamily: "Arial, sans-serif",
        }}>
          {primary_text}
        </p>
      </div>
    </AbsoluteFill>
  );
};