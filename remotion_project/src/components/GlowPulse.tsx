import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { theme } from "../theme";

interface GlowPulseProps {
  x: number;
  y: number;
  radius?: number;
  color?: string;
  opacity?: number;
  startFrame?: number;
  breatheSpeed?: number;
}

/**
 * GlowPulse - Radial glow with gentle breathing animation.
 *
 * Creates a soft colored glow behind key elements.
 * Used for depth, emphasis, and visual warmth.
 *
 * Usage:
 * <GlowPulse x={960} y={540} radius={200} color={theme.accentAmber} />
 * <GlowPulse x={300} y={400} radius={150} opacity={0.08} startFrame={30} />
 */
export const GlowPulse: React.FC<GlowPulseProps> = ({
  x,
  y,
  radius = 180,
  color = theme.accentAmber,
  opacity = 0.1,
  startFrame = 0,
  breatheSpeed = 0.02,
}) => {
  const frame = useCurrentFrame();

  // Fade in
  const fadeIn = interpolate(frame, [startFrame, startFrame + 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  // Breathing pulse: oscillates between 0.7 and 1.0 of base opacity
  const breathe = 0.7 + 0.3 * Math.sin(frame * breatheSpeed);

  return (
    <div
      style={{
        position: "absolute",
        left: x - radius,
        top: y - radius,
        width: radius * 2,
        height: radius * 2,
        borderRadius: "50%",
        background: `radial-gradient(circle, ${color} 0%, transparent 70%)`,
        opacity: opacity * fadeIn * breathe,
        pointerEvents: "none",
        filter: `blur(${radius * 0.3}px)`,
      }}
    />
  );
};
