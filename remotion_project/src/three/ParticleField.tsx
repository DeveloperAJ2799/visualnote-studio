import React, { useMemo } from "react";
import { useCurrentFrame } from "remotion";
import * as THREE from "three";

interface ParticleFieldProps {
  count?: number;
  spread?: number;
  color?: string;
  size?: number;
  speed?: number;
  seed?: number;
}

interface ParticleData {
  position: THREE.Vector3;
  velocity: THREE.Vector3;
  size: number;
  phase: number;
}

/**
 * ParticleField - 3D floating particles for atmospheric depth.
 *
 * Particles drift slowly in 3D space with depth-based rendering.
 * Creates ambient motion without distracting from content.
 *
 * Usage:
 * <ParticleField count={50} spread={10} color="#F2EFE6" />
 * <ParticleField count={30} color="#E8A33D" speed={0.3} />
 */
export const ParticleField: React.FC<ParticleFieldProps> = ({
  count = 40,
  spread = 8,
  color = "#F2EFE6",
  size = 0.03,
  speed = 0.5,
  seed = 42,
}) => {
  const frame = useCurrentFrame();

  const particles = useMemo(() => {
    const rng = createSeededRandom(seed);
    return Array.from({ length: count }, (): ParticleData => ({
      position: new THREE.Vector3(
        (rng() - 0.5) * spread,
        (rng() - 0.5) * spread,
        (rng() - 0.5) * spread,
      ),
      velocity: new THREE.Vector3(
        (rng() - 0.5) * 0.01 * speed,
        (rng() - 0.5) * 0.01 * speed,
        (rng() - 0.5) * 0.005 * speed,
      ),
      size: size * (0.5 + rng()),
      phase: rng() * Math.PI * 2,
    }));
  }, [count, spread, size, speed, seed]);

  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    particles.forEach((p, i) => {
      // Animate position
      const x = p.position.x + Math.sin(frame * 0.01 + p.phase) * 0.3;
      const y = p.position.y + Math.cos(frame * 0.008 + p.phase) * 0.2;
      const z = p.position.z + Math.sin(frame * 0.006 + p.phase * 0.5) * 0.15;
      arr[i * 3] = x;
      arr[i * 3 + 1] = y;
      arr[i * 3 + 2] = z;
    });
    return arr;
  }, [frame, particles, count]);

  const sizes = useMemo(() => {
    const arr = new Float32Array(count);
    particles.forEach((p, i) => {
      // Subtle size oscillation
      arr[i] = p.size * (0.8 + 0.2 * Math.sin(frame * 0.015 + p.phase));
    });
    return arr;
  }, [frame, particles, count]);

  return (
    <points>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={count}
          array={positions}
          itemSize={3}
        />
        <bufferAttribute
          attach="attributes-size"
          count={count}
          array={sizes}
          itemSize={1}
        />
      </bufferGeometry>
      <pointsMaterial
        color={color}
        size={size}
        transparent
        opacity={0.6}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  );
};

function createSeededRandom(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807 + 0) % 2147483647;
    return (s - 1) / 2147483646;
  };
}
