import React, { useRef } from "react";
import { useCurrentFrame, useVideoConfig, spring, interpolate } from "remotion";
import * as THREE from "three";
import { useTexture } from "@react-three/drei";
import { springConfig } from "../theme";

interface ImagePlaneProps {
  src: string;
  position?: [number, number, number];
  rotation?: [number, number, number];
  width?: number;
  height?: number;
  enterFrame?: number;
  float?: boolean;
  floatSpeed?: number;
  floatAmplitude?: number;
}

/**
 * ImagePlane - Image texture on a 3D plane.
 *
 * Loads a PNG/JPG as a texture and displays it on a plane in 3D space.
 * Spring entrance, optional floating animation.
 *
 * Usage:
 * <ImagePlane src="/assets/scene_001.png" position={[0, 0, 0]} width={3} height={1.7} />
 * <ImagePlane src="/assets/chart.png" position={[-2, 0, -1]} enterFrame={30} float />
 */
export const ImagePlane: React.FC<ImagePlaneProps> = ({
  src,
  position = [0, 0, 0],
  rotation = [0, 0, 0],
  width = 3,
  height = 1.7,
  enterFrame = 0,
  float = false,
  floatSpeed = 0.5,
  floatAmplitude = 0.05,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const meshRef = useRef<THREE.Mesh>(null);

  // Load texture
  const texture = useTexture(src);

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

  // Floating animation
  const floatY = float
    ? Math.sin((frame - enterFrame) * 0.02 * floatSpeed) * floatAmplitude
    : 0;

  return (
    <mesh
      ref={meshRef}
      position={[position[0], position[1] + floatY, position[2]]}
      rotation={rotation}
      scale={[scale * width, scale * height, 1]}
    >
      <planeGeometry args={[1, 1]} />
      <meshStandardMaterial
        map={texture}
        transparent
        opacity={opacity}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
};
