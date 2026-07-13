import React from "react";
import { useCurrentFrame, useVideoConfig, spring, interpolate } from "remotion";
import { Text } from "@react-three/drei";
import { springConfig } from "../theme";

interface Text3DProps {
  text: string;
  position?: [number, number, number];
  rotation?: [number, number, number];
  fontSize?: number;
  color?: string;
  fontWeight?: number;
  enterFrame?: number;
  maxWidth?: number;
  textAlign?: "left" | "center" | "right";
  anchorX?: "left" | "center" | "right";
  anchorY?: "middle" | "top" | "bottom";
}

/**
 * Text3D - 3D text with spring entrance animation.
 *
 * Uses @react-three/drei Text for high-quality SDF text rendering.
 * Spring entrance with optional rotation and depth.
 *
 * Usage:
 * <Text3D text="Enzymes" position={[0, 1, 0]} fontSize={1.5} />
 * <Text3D text="Key insight" position={[0, -1, 0]} color="#E8A33D" enterFrame={30} />
 */
export const Text3D: React.FC<Text3DProps> = ({
  text,
  position = [0, 0, 0],
  rotation = [0, 0, 0],
  fontSize = 0.5,
  color = "#F2EFE6",
  fontWeight = 700,
  enterFrame = 0,
  maxWidth,
  textAlign = "center",
  anchorX = "center",
  anchorY = "middle",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Spring entrance
  const scale = spring({
    frame: frame - enterFrame,
    fps,
    config: springConfig,
  });

  const opacity = interpolate(frame, [enterFrame, enterFrame + 10], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Subtle float
  const floatY = Math.sin(frame * 0.015) * 0.02;

  return (
    <Text
      position={[position[0], position[1] + floatY, position[2]]}
      rotation={rotation}
      fontSize={fontSize}
      color={color}
      font="https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTeHuS_nVMrMxCp50SjIw2boKoduKmMEVuLyfAZ9hiJ-Ek-_EeA.woff2"
      fontWeight={fontWeight}
      maxWidth={maxWidth}
      textAlign={textAlign}
      anchorX={anchorX}
      anchorY={anchorY}
      scale={[scale, scale, scale]}
      fillOpacity={opacity}
    >
      {text}
    </Text>
  );
};
