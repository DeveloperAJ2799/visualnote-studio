import React, { useState } from "react";
import { AbsoluteFill, useCurrentFrame, interpolate, Audio, Img } from "@remotion/react";

interface MediaFocusProps {
  scene_id: number;
  visual_props: { primary_text: string; image_url: string };
  audio_url?: string;
  durationInFrames: number;
}

export const MediaFocus: React.FC<MediaFocusProps> = ({
  scene_id,
  visual_props,
  audio_url,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { primary_text, image_url } = visual_props;
  const [imageLoaded, setImageLoaded] = useState(false);

  const scale = interpolate(frame, [0, durationInFrames], [1, 1.15], { extrapolateRight: "clamp" });
  const overlayOpacity = interpolate(frame, [0, 20], [0, 0.6], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#000", overflow: "hidden" }}>
      {audio_url && <Audio src={audio_url} />}
      {image_url && (
        <div style={{
          position: "absolute",
          inset: 0,
          transform: `scale(${scale})`,
          transformOrigin: "center",
        }}>
          <Img
            src={image_url}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              opacity: imageLoaded ? 1 : 0,
            }}
            onLoad={() => setImageLoaded(true)}
          />
        </div>
      )}
      <div style={{
        position: "absolute",
        inset: 0,
        backgroundColor: "#000",
        opacity: overlayOpacity,
      }} />
      <div style={{
        position: "absolute",
        bottom: "10%",
        left: "5%",
        right: "5%",
        backgroundColor: "rgba(15, 15, 26, 0.9)",
        padding: "2rem",
        borderLeft: "4px solid #6366F1",
      }}>
        <p style={{
          color: "#FFFFFF",
          fontSize: "1.8rem",
          margin: 0,
          fontFamily: "Arial, sans-serif",
        }}>
          {primary_text}
        </p>
      </div>
    </AbsoluteFill>
  );
};