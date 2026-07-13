import React from "react";
import { useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";
import { theme, springConfig, typography } from "../theme";

interface TextRevealProps {
  text: string;
  startFrame?: number;
  charsPerFrame?: number;
  fontSize?: number;
  fontFamily?: string;
  color?: string;
  fontWeight?: number;
  showCursor?: boolean;
}

/**
 * TextReveal - Typewriter-style character-by-character text reveal.
 *
 * More engaging than simple fade-in for key terms, definitions,
 * or important statements. Optional blinking cursor.
 *
 * Usage:
 * <TextReveal text="Enzymes are biological catalysts" startFrame={20} />
 * <TextReveal text="ATP" fontSize={typography.displayXL} showCursor={false} />
 */
export const TextReveal: React.FC<TextRevealProps> = ({
  text,
  startFrame = 0,
  charsPerFrame = 1.5,
  fontSize = typography.displayM,
  fontFamily = theme.fontFamilyDisplay,
  color = theme.chalkWhite,
  fontWeight = 700,
  showCursor = true,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const elapsed = Math.max(0, frame - startFrame);
  const charsVisible = Math.min(Math.floor(elapsed * charsPerFrame), text.length);
  const displayedText = text.slice(0, charsVisible);
  const isComplete = charsVisible >= text.length;

  // Container opacity (spring entrance)
  const containerOpacity = interpolate(
    frame,
    [startFrame, startFrame + 5],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Cursor blink
  const cursorOpacity = isComplete
    ? (Math.floor(frame / 12) % 2 === 0 ? 0.8 : 0)
    : 0.8;

  return (
    <div
      style={{
        opacity: containerOpacity,
        display: "inline-block",
      }}
    >
      <span
        style={{
          fontSize,
          fontFamily,
          color,
          fontWeight,
          letterSpacing: "-0.02em",
        }}
      >
        {displayedText}
      </span>
      {showCursor && (
        <span
          style={{
            fontSize,
            fontFamily,
            color: theme.accentAmber,
            fontWeight: 300,
            opacity: cursorOpacity,
            marginLeft: 2,
          }}
        >
          |
        </span>
      )}
    </div>
  );
};
