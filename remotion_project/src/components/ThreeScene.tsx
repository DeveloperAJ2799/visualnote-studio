import React from "react";
import { AbsoluteFill } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import { theme } from "../theme";

interface ThreeSceneProps {
  children: React.ReactNode;
  camera?: {
    position?: [number, number, number];
    fov?: number;
    near?: number;
    far?: number;
  };
  style?: React.CSSProperties;
}

/**
 * ThreeScene - Wrapper for Three.js scenes in Remotion.
 *
 * Sets up ThreeCanvas with proper sizing, camera, and lighting.
 * All 3D content goes inside this wrapper.
 *
 * Usage:
 * <ThreeScene camera={{ position: [0, 0, 5], fov: 50 }}>
 *   <ImagePlane src="/assets/scene_001.png" position={[0, 0, 0]} />
 *   <CameraRig path="flythrough" />
 * </ThreeScene>
 */
export const ThreeScene: React.FC<ThreeSceneProps> = ({
  children,
  camera = {},
  style,
}) => {
  const {
    position = [0, 0, 5],
    fov = 50,
    near = 0.1,
    far = 100,
  } = camera;

  return (
    <AbsoluteFill style={{ backgroundColor: theme.bgPrimary, ...style }}>
      <ThreeCanvas
        camera={{ position, fov, near, far }}
        style={{ width: "100%", height: "100%" }}
      >
        {/* Default lighting */}
        <ambientLight intensity={0.4} color="#F2EFE6" />
        <directionalLight
          position={[5, 5, 5]}
          intensity={0.8}
          color="#F2EFE6"
        />
        <directionalLight
          position={[-3, 3, -3]}
          intensity={0.3}
          color="#E8A33D"
        />

        {children}
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
