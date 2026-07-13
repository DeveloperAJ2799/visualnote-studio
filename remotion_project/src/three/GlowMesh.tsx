import React from "react";
import { useCurrentFrame, useVideoConfig, spring, interpolate } from "remotion";
import { springConfig } from "../theme";

type MeshShape = "sphere" | "box" | "torus" | "cylinder";

interface GlowMeshProps {
  shape?: MeshShape;
  position?: [number, number, number];
  scale?: number;
  color?: string;
  emissiveColor?: string;
  emissiveIntensity?: number;
  enterFrame?: number;
  pulse?: boolean;
  pulseSpeed?: number;
}

/**
 * GlowMesh - Glowing 3D mesh with pulsing emissive material.
 *
 * Creates a mesh with emissive glow effect for emphasis.
 * Used behind key elements or as atmospheric accents.
 *
 * Usage:
 * <GlowMesh shape="sphere" position={[0, 0, -2]} color="#E8A33D" />
 * <GlowMesh shape="torus" position={[2, 1, 0]} pulse emissiveIntensity={0.5} />
 */
export const GlowMesh: React.FC<GlowMeshProps> = ({
  shape = "sphere",
  position = [0, 0, 0],
  scale = 1,
  color = "#1D2D27",
  emissiveColor = "#E8A33D",
  emissiveIntensity = 0.3,
  enterFrame = 0,
  pulse = false,
  pulseSpeed = 0.5,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Spring entrance
  const entryScale = spring({
    frame: frame - enterFrame,
    fps,
    config: springConfig,
  });

  const opacity = interpolate(frame, [enterFrame, enterFrame + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Pulse effect
  const pulseIntensity = pulse
    ? emissiveIntensity * (0.7 + 0.3 * Math.sin(frame * 0.03 * pulseSpeed))
    : emissiveIntensity;

  const getGeometry = () => {
    switch (shape) {
      case "sphere":
        return <sphereGeometry args={[0.5, 32, 32]} />;
      case "box":
        return <boxGeometry args={[0.8, 0.8, 0.8]} />;
      case "torus":
        return <torusGeometry args={[0.4, 0.15, 16, 32]} />;
      case "cylinder":
        return <cylinderGeometry args={[0.3, 0.3, 0.8, 32]} />;
      default:
        return <sphereGeometry args={[0.5, 32, 32]} />;
    }
  };

  return (
    <mesh
      position={position}
      scale={[entryScale * scale, entryScale * scale, entryScale * scale]}
    >
      {getGeometry()}
      <meshStandardMaterial
        color={color}
        emissive={emissiveColor}
        emissiveIntensity={pulseIntensity}
        transparent
        opacity={opacity}
        roughness={0.3}
        metalness={0.1}
      />
    </mesh>
  );
};
