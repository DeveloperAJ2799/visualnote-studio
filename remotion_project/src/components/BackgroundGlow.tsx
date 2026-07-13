import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { theme } from "../theme";

interface GlowSpot {
  x: number;
  y: number;
  radius?: number;
  color?: string;
  opacity?: number;
}

interface BackgroundGlowProps {
  glows: GlowSpot[];
  startFrame?: number;
}

/**
 * BackgroundGlow - Subtle colored gradients behind content areas.
 *
 * Creates depth by adding soft color pools behind the main content.
 * Never distracting — just enough to break flat backgrounds.
 *
 * Usage:
 * <BackgroundGlow glows={[
 *   { x: 960, y: 540, radius: 400, color: theme.accentAmber, opacity: 0.04 },
 *   { x: 300, y: 300, radius: 250, color: theme.codeMint, opacity: 0.03 },
 * ]} />
 */
export const BackgroundGlow: React.FC<BackgroundGlowProps> = ({
  glows,
  startFrame = 0,
}) => {
  const frame = useCurrentFrame();

  const fadeIn = interpolate(frame, [startFrame, startFrame + 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        opacity: fadeIn,
      }}
    >
      {glows.map((g, i) => {
        const r = g.radius ?? 300;
        const c = g.color ?? theme.accentAmber;
        const op = g.opacity ?? 0.04;
        // Subtle breathing
        const breathe = 0.85 + 0.15 * Math.sin(frame * 0.012 + i * 1.5);

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: g.x - r,
              top: g.y - r,
              width: r * 2,
              height: r * 2,
              borderRadius: "50%",
              background: `radial-gradient(circle, ${c} 0%, transparent 70%)`,
              opacity: op * breathe,
              filter: `blur(${r * 0.4}px)`,
            }}
          />
        );
      })}
    </div>
  );
};
