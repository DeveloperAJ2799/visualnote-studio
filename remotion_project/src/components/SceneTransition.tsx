import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { theme } from "../theme";

interface SceneTransitionProps {
  children: React.ReactNode;
  durationInFrames: number;
  fadeInDuration?: number;
  fadeOutDuration?: number;
}

/**
 * SceneTransition - Fade in/out wrapper for scenes.
 *
 * Provides smooth fade-from-black at start and fade-to-black at end.
 * Creates a cinematic feel instead of hard cuts between scenes.
 *
 * Usage:
 * <SceneTransition durationInFrames={180}>
 *   <YourScene />
 * </SceneTransition>
 */
export const SceneTransition: React.FC<SceneTransitionProps> = ({
  children,
  durationInFrames,
  fadeInDuration = 15,
  fadeOutDuration = 15,
}) => {
  const frame = useCurrentFrame();

  // Fade in from black
  const fadeInOpacity = interpolate(
    frame,
    [0, fadeInDuration],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    }
  );

  // Fade out to black
  const fadeOutOpacity = interpolate(
    frame,
    [durationInFrames - fadeOutDuration, durationInFrames],
    [1, 0],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.in(Easing.cubic),
    }
  );

  return (
    <AbsoluteFill>
      {/* Content */}
      <AbsoluteFill style={{ opacity: fadeInOpacity * fadeOutOpacity }}>
        {children}
      </AbsoluteFill>

      {/* Black overlay for fades */}
      {fadeInOpacity < 1 && (
        <AbsoluteFill
          style={{
            backgroundColor: theme.bgPrimary,
            opacity: 1 - fadeInOpacity,
            pointerEvents: "none",
          }}
        />
      )}
      {fadeOutOpacity < 1 && (
        <AbsoluteFill
          style={{
            backgroundColor: theme.bgPrimary,
            opacity: 1 - fadeOutOpacity,
            pointerEvents: "none",
          }}
        />
      )}
    </AbsoluteFill>
  );
};
