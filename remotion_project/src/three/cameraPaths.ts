import { interpolate, Easing } from "remotion";

/**
 * Predefined camera animation paths for 3D scenes.
 *
 * Each path returns camera position and lookAt target for a given frame.
 * All paths are deterministic and frame-accurate.
 */

export interface CameraState {
  position: [number, number, number];
  lookAt: [number, number, number];
}

export type PathName =
  | "flythrough"
  | "orbit"
  | "pullback"
  | "dolly"
  | "pan"
  | "crane";

/**
 * Flythrough — camera moves forward through space.
 */
export function flythrough(
  frame: number,
  durationInFrames: number,
  start: [number, number, number] = [0, 0, 8],
  end: [number, number, number] = [0, 0, 2],
  target: [number, number, number] = [0, 0, 0],
): CameraState {
  const t = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });

  return {
    position: [
      interpolate(t, [0, 1], [start[0], end[0]]),
      interpolate(t, [0, 1], [start[1], end[1]]),
      interpolate(t, [0, 1], [start[2], end[2]]),
    ],
    lookAt: target,
  };
}

/**
 * Orbit — camera circles around a target.
 */
export function orbit(
  frame: number,
  durationInFrames: number,
  radius: number = 5,
  height: number = 2,
  target: [number, number, number] = [0, 0, 0],
  startAngle: number = 0,
): CameraState {
  const t = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const angle = startAngle + t * Math.PI * 1.5; // 3/4 orbit

  return {
    position: [
      Math.cos(angle) * radius + target[0],
      height + target[1],
      Math.sin(angle) * radius + target[2],
    ],
    lookAt: target,
  };
}

/**
 * Pullback — starts zoomed in, pulls back to reveal.
 */
export function pullback(
  frame: number,
  durationInFrames: number,
  target: [number, number, number] = [0, 0, 0],
): CameraState {
  const t = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  return {
    position: [
      target[0],
      interpolate(t, [0, 1], [0.5, 2]) + target[1],
      interpolate(t, [0, 1], [1, 7]) + target[2],
    ],
    lookAt: target,
  };
}

/**
 * Dolly — camera slides sideways.
 */
export function dolly(
  frame: number,
  durationInFrames: number,
  start: [number, number, number] = [-4, 1, 5],
  end: [number, number, number] = [4, 1, 5],
  target: [number, number, number] = [0, 0, 0],
): CameraState {
  const t = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });

  return {
    position: [
      interpolate(t, [0, 1], [start[0], end[0]]),
      interpolate(t, [0, 1], [start[1], end[1]]),
      interpolate(t, [0, 1], [start[2], end[2]]),
    ],
    lookAt: target,
  };
}

/**
 * Pan — camera looks left to right from a fixed position.
 */
export function pan(
  frame: number,
  durationInFrames: number,
  position: [number, number, number] = [0, 1, 6],
  targetStart: [number, number, number] = [-3, 0, 0],
  targetEnd: [number, number, number] = [3, 0, 0],
): CameraState {
  const t = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });

  return {
    position,
    lookAt: [
      interpolate(t, [0, 1], [targetStart[0], targetEnd[0]]),
      interpolate(t, [0, 1], [targetStart[1], targetEnd[1]]),
      interpolate(t, [0, 1], [targetStart[2], targetEnd[2]]),
    ],
  };
}

/**
 * Crane — camera moves vertically.
 */
export function crane(
  frame: number,
  durationInFrames: number,
  start: [number, number, number] = [0, -1, 5],
  end: [number, number, number] = [0, 4, 5],
  target: [number, number, number] = [0, 1, 0],
): CameraState {
  const t = interpolate(frame, [0, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });

  return {
    position: [
      interpolate(t, [0, 1], [start[0], end[0]]),
      interpolate(t, [0, 1], [start[1], end[1]]),
      interpolate(t, [0, 1], [start[2], end[2]]),
    ],
    lookAt: target,
  };
}

/** Map of path names to functions. */
export const cameraPathFns = {
  flythrough,
  orbit,
  pullback,
  dolly,
  pan,
  crane,
} as const;
