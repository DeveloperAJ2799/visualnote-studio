import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";

type CameraPathType = "flythrough" | "orbit" | "dolly" | "pan" | "pullback";

interface CameraRigProps {
  path?: CameraPathType;
  lookAt?: [number, number, number];
  // Flythrough
  startPos?: [number, number, number];
  endPos?: [number, number, number];
  // Orbit
  orbitRadius?: number;
  orbitHeight?: number;
  // Dolly
  dollyStart?: [number, number, number];
  dollyEnd?: [number, number, number];
}

/**
 * CameraRig - Animated camera controller for 3D scenes.
 *
 * Provides predefined camera paths that animate smoothly over the scene duration.
 * Uses useCurrentFrame() for deterministic, frame-accurate animation.
 *
 * Usage:
 * <CameraRig path="flythrough" startPos={[0, 0, 8]} endPos={[0, 0, 2]} />
 * <CameraRig path="orbit" orbitRadius={5} orbitHeight={2} />
 * <CameraRig path="pullback" />
 */
export const CameraRig: React.FC<CameraRigProps> = ({
  path = "flythrough",
  lookAt = [0, 0, 0],
  startPos = [0, 0, 8],
  endPos = [0, 0, 2],
  orbitRadius = 5,
  orbitHeight = 2,
  dollyStart = [-5, 0, 0],
  dollyEnd = [5, 0, 0],
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const { camera } = useThree();

  const t = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });

  const lookAtVec = new THREE.Vector3(...lookAt);

  switch (path) {
    case "flythrough": {
      const x = interpolate(t, [0, 1], [startPos[0], endPos[0]]);
      const y = interpolate(t, [0, 1], [startPos[1], endPos[1]]);
      const z = interpolate(t, [0, 1], [startPos[2], endPos[2]]);
      camera.position.set(x, y, z);
      camera.lookAt(lookAtVec);
      break;
    }

    case "orbit": {
      const angle = t * Math.PI * 2;
      const x = Math.cos(angle) * orbitRadius;
      const z = Math.sin(angle) * orbitRadius;
      camera.position.set(x, orbitHeight, z);
      camera.lookAt(lookAtVec);
      break;
    }

    case "dolly": {
      const x = interpolate(t, [0, 1], [dollyStart[0], dollyEnd[0]]);
      const y = interpolate(t, [0, 1], [dollyStart[1], dollyEnd[1]]);
      const z = interpolate(t, [0, 1], [dollyStart[2], dollyEnd[2]]);
      camera.position.set(x, y, z);
      camera.lookAt(lookAtVec);
      break;
    }

    case "pan": {
      // Pan left to right while looking at center
      const panX = interpolate(t, [0, 1], [-4, 4]);
      camera.position.set(panX, 1, 5);
      camera.lookAt(lookAtVec);
      break;
    }

    case "pullback": {
      // Start close, pull back to reveal
      const pullZ = interpolate(t, [0, 1], [1, 8]);
      const pullY = interpolate(t, [0, 1], [0.5, 1.5]);
      camera.position.set(0, pullY, pullZ);
      camera.lookAt(lookAtVec);
      break;
    }
  }

  return null;
};
