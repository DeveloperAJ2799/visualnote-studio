import React from "react";
import { AbsoluteFill } from "remotion";
import { GrainOverlay } from "./GrainOverlay";
import { theme } from "../theme";

/**
 * ChalkBackground - Base layer for all IGWANI templates.
 *
 * Provides the chalkboard slate-green background with subtle grain texture.
 * Use as the first child in any template composition.
 *
 * Usage:
 * <ChalkBackground>
 *   <YourContent />
 * </ChalkBackground>
 */
export const ChalkBackground: React.FC<{
  children?: React.ReactNode;
  color?: string;
}> = ({ children, color = theme.bgPrimary }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: color }}>
      {children}
      <GrainOverlay />
    </AbsoluteFill>
  );
};
