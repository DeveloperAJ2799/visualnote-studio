import React from "react";
import {
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Easing,
} from "remotion";
import { theme, springConfig, typography } from "../theme";

interface CodeBlockProps {
  code: string;
  language?: string;
  title?: string;
  startFrame?: number;
  lineRevealDelay?: number;
}

/**
 * CodeBlock - Terminal-style code display for IGWANI.
 *
 * Real terminal chrome with:
 * - Faux window dots and title bar
 * - Line-by-line reveal synced to timing
 * - JetBrains Mono font
 * - codeMint for syntax, chalkWhite for text
 *
 * Usage:
 * <CodeBlock
 *   code="model = Sequential([\n  Dense(128, activation='relu'),\n  Dense(10, activation='softmax')\n])"
 *   language="python"
 *   title="model.py"
 *   startFrame={30}
 * />
 */
export const CodeBlock: React.FC<CodeBlockProps> = ({
  code,
  language = "python",
  title = "code",
  startFrame = 0,
  lineRevealDelay = 8,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const lines = code.split("\n");

  const containerScale = spring({
    frame: frame - startFrame,
    fps,
    config: springConfig,
  });

  const containerOpacity = interpolate(
    frame,
    [startFrame, startFrame + 10],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  return (
    <div
      style={{
        opacity: containerOpacity,
        transform: `scale(${containerScale})`,
        backgroundColor: theme.bgSecondary,
        borderRadius: 12,
        overflow: "hidden",
        border: `1px solid ${theme.chalkDim}20`,
        boxShadow: "0 8px 32px rgba(0, 0, 0, 0.3)",
      }}
    >
      {/* Window chrome */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          padding: "12px 16px",
          backgroundColor: `${theme.bgPrimary}cc`,
          borderBottom: `1px solid ${theme.chalkDim}20`,
        }}
      >
        {/* Traffic light dots */}
        <div style={{ display: "flex", gap: 8 }}>
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: "50%",
              backgroundColor: theme.accentCoral,
            }}
          />
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: "50%",
              backgroundColor: "#fdd835",
            }}
          />
          <div
            style={{
              width: 12,
              height: 12,
              borderRadius: "50%",
              backgroundColor: theme.codeMint,
            }}
          />
        </div>
        {/* Title */}
        <div
          style={{
            flex: 1,
            textAlign: "center",
            fontFamily: theme.fontFamilyMono,
            fontSize: typography.monoS,
            color: theme.chalkDim,
          }}
        >
          {title}
        </div>
      </div>

      {/* Code content */}
      <div
        style={{
          padding: "20px 24px",
          fontFamily: theme.fontFamilyMono,
          fontSize: typography.monoM,
          lineHeight: 1.6,
        }}
      >
        {lines.map((line, i) => {
          const lineDelay = startFrame + 15 + i * lineRevealDelay;
          const lineOpacity = interpolate(
            frame,
            [lineDelay, lineDelay + 6],
            [0, 1],
            {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }
          );
          const lineX = interpolate(
            frame,
            [lineDelay, lineDelay + 8],
            [-10, 0],
            {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.out(Easing.cubic),
            }
          );

          return (
            <div
              key={i}
              style={{
                opacity: lineOpacity,
                transform: `translateX(${lineX}px)`,
                display: "flex",
              }}
            >
              <span
                style={{
                  color: theme.chalkDim,
                  marginRight: 16,
                  userSelect: "none",
                  minWidth: 30,
                }}
              >
                {i + 1}
              </span>
              <span style={{ color: highlightSyntax(line, language) }}>
                {line}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/**
 * Simple syntax highlighting for common keywords.
 */
function highlightSyntax(line: string, language: string): string {
  const trimmed = line.trimStart();

  // Keywords
  if (
    /^(def|class|import|from|return|if|else|for|while|in|and|or|not|True|False|None|async|await|with|as|try|except|finally|raise|yield|lambda|pass|break|continue|global|nonlocal|del|assert)$/.test(
      trimmed.split(/[(\s:]/)[0]
    )
  ) {
    return theme.accentAmber;
  }

  // Strings
  if (trimmed.startsWith('"') || trimmed.startsWith("'") || trimmed.startsWith("`")) {
    return theme.codeMint;
  }

  // Comments
  if (trimmed.startsWith("#") || trimmed.startsWith("//")) {
    return theme.chalkDim;
  }

  // Function calls
  if (/\w+\(/.test(trimmed)) {
    return theme.chalkWhite;
  }

  return theme.chalkWhite;
}
