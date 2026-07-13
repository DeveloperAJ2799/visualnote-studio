import React, { useMemo } from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { theme } from "../theme";

interface Particle {
  id: number;
  baseX: number;
  baseY: number;
  size: number;
  opacity: number;
  speedX: number;
  speedY: number;
  phaseX: number;
  phaseY: number;
}

interface FloatingDustProps {
  count?: number;
  color?: string;
  seed?: number;
}

/**
 * FloatingDust - Ambient floating particles for atmospheric depth.
 *
 * Subtle dust motes that drift slowly across the frame.
 * Adds life to otherwise static scenes without distracting from content.
 *
 * Usage:
 * <FloatingDust /> — default 18 particles
 * <FloatingDust count={25} color={theme.accentAmber} />
 */
export const FloatingDust: React.FC<FloatingDustProps> = ({
  count = 18,
  color = theme.chalkWhite,
  seed = 42,
}) => {
  const frame = useCurrentFrame();

  const particles = useMemo(() => {
    const rng = createSeededRandom(seed);
    return Array.from({ length: count }, (_, i): Particle => ({
      id: i,
      baseX: rng() * theme.width,
      baseY: rng() * theme.height,
      size: 1 + rng() * 2.5,
      opacity: 0.025 + rng() * 0.055,
      speedX: 0.15 + rng() * 0.35,
      speedY: 0.08 + rng() * 0.2,
      phaseX: rng() * Math.PI * 2,
      phaseY: rng() * Math.PI * 2,
    }));
  }, [count, seed]);

  // Fade in over first 20 frames
  const fadeIn = interpolate(frame, [0, 20], [0, 1], {
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
      {particles.map((p) => {
        const x = p.baseX + Math.sin(frame * 0.008 * p.speedX + p.phaseX) * 30;
        const y = p.baseY + Math.cos(frame * 0.006 * p.speedY + p.phaseY) * 20;
        // Subtle opacity oscillation
        const opMod = 0.7 + 0.3 * Math.sin(frame * 0.015 + p.id);

        return (
          <div
            key={p.id}
            style={{
              position: "absolute",
              left: x,
              top: y,
              width: p.size,
              height: p.size,
              borderRadius: "50%",
              backgroundColor: color,
              opacity: p.opacity * opMod,
            }}
          />
        );
      })}
    </div>
  );
};

/** Simple seeded PRNG for deterministic particle positions. */
function createSeededRandom(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807 + 0) % 2147483647;
    return (s - 1) / 2147483646;
  };
}
