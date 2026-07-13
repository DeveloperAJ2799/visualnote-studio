import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";

/**
 * GrainOverlay - Animated noise texture for chalkboard effect.
 *
 * Adds visible grain that drifts slowly, separating "chalkboard" from "dark mode app."
 * Sits above background, below content. Pointer-events: none.
 *
 * Usage: Place as last child in AbsoluteFill to layer on top of background.
 */
export const GrainOverlay: React.FC = () => {
  const frame = useCurrentFrame();

  // Slow drift — shifts the noise pattern over time
  const driftX = interpolate(frame, [0, 900], [0, 50], {
    extrapolateRight: "extend",
  });
  const driftY = interpolate(frame, [0, 1200], [0, 30], {
    extrapolateRight: "extend",
  });

  return (
    <AbsoluteFill
      style={{
        pointerEvents: "none",
        opacity: 0.07,
        mixBlendMode: "overlay",
      }}
    >
      <svg
        width="100%"
        height="100%"
        xmlns="http://www.w3.org/2000/svg"
        style={{ transform: `translate(${driftX % 100}px, ${driftY % 100}px)` }}
      >
        <defs>
          <filter id="grain">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.65"
              numOctaves="3"
              stitchTiles="stitch"
            />
            <feColorMatrix type="saturate" values="0" />
          </filter>
        </defs>
        <rect width="120%" height="120%" x="-10%" y="-10%" filter="url(#grain)" />
      </svg>
    </AbsoluteFill>
  );
};
