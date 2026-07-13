/**
 * IGWANI Design System - Theme Tokens
 *
 * Chalkboard-inspired design for AI/CS course content.
 * Dark, textured, warm — closer to a real lecture hall blackboard.
 */

export const theme = {
  // === Core Colors ===
  bgPrimary: "#16231F",      // Deep blackboard slate-green, not pure black
  bgSecondary: "#1D2D27",    // Slightly lifted panel/card surface
  chalkWhite: "#F2EFE6",     // Primary text — warm chalk, not pure white
  chalkDim: "#A9B5AC",       // Secondary text, captions, muted labels

  // === Accent Colors (one per slide rule) ===
  accentAmber: "#E8A33D",    // Primary annotation — circles, arrows, emphasis
  accentCoral: "#E8654A",    // Secondary — warnings, contrast, gotchas (sparingly)
  codeMint: "#7FD9B0",       // Syntax/terminal accent — code blocks only

  // === Typography ===
  fontFamilyDisplay: "'Inter', 'Source Sans 3', sans-serif",
  fontFamilyBody: "'Inter', 'Source Sans 3', sans-serif",
  fontFamilyMono: "'JetBrains Mono', 'Fira Code', monospace",
  fontFamilyHand: "'Caveat', 'Kalam', cursive",

  // === Layout ===
  padding: 120,              // Generous safe zone (80px min, 120px preferred)
  width: 1920,
  height: 1080,
  fps: 30,
} as const;

/**
 * Spring configuration for natural-feeling motion.
 * Use for: text entrances, annotation draw-ons, emphasis pulses.
 */
export const springConfig = {
  damping: 12,
  stiffness: 100,
  mass: 0.8,
} as const;

/**
 * Typography scale (in pixels).
 */
export const typography = {
  // Display — titles, key terms, big numbers
  displayXL: 80,
  displayL: 64,
  displayM: 56,

  // Body — explanatory text, captions
  bodyL: 36,
  bodyM: 32,
  bodyS: 28,

  // Mono — code, terminal, technical labels
  monoL: 28,
  monoM: 24,
  monoS: 20,

  // Hand — annotation labels only (sparingly)
  handL: 40,
  handM: 32,
} as const;
