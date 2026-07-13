/**
 * Auto-annotation utilities for IGWANI design system.
 *
 * When no manual annotations exist in the manifest, this module
 * parses narration text to detect emphasis points and generates
 * appropriate annotations.
 */

import type { Annotation } from "../types";

// Common emphasis indicators in educational content
const EMPHASIS_PATTERNS = [
  // Key terms (nouns that are often defined)
  { pattern: /\b(is|are|means|refers to|defined as)\b/gi, type: "underline" as const },

  // Numbers and statistics
  { pattern: /\b\d+(?:\.\d+)?%?\b/g, type: "circle" as const },

  // Important markers
  { pattern: /\b(important|key|critical|essential|note|remember|watch out|gotcha)\b/gi, type: "underline" as const },

  // Technical terms (capitalized words that aren't sentence starts)
  { pattern: /\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b/g, type: "underline" as const },

  // Code references
  { pattern: /`[^`]+`/g, type: "underline" as const },
];

// Words to skip (too common to annotate)
const SKIP_WORDS = new Set([
  "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
  "have", "has", "had", "do", "does", "did", "will", "would", "could",
  "should", "may", "might", "can", "shall", "this", "that", "these",
  "those", "it", "its", "we", "you", "they", "he", "she", "they",
]);

/**
 * Generate automatic annotations from narration text.
 *
 * @param narration - The narration text for a scene
 * @param durationInFrames - Total frames for the scene
 * @returns Array of annotations, or empty if none detected
 */
export function generateAutoAnnotations(
  narration: string,
  durationInFrames: number
): Annotation[] {
  const annotations: Annotation[] = [];
  const words = narration.split(/\s+/);
  const totalWords = words.length;

  if (totalWords === 0) return annotations;

  // Find emphasis points in the narration
  let annotationCount = 0;
  const maxAnnotations = 2; // Keep it sparse - one focal point per slide

  for (const { pattern, type } of EMPHASIS_PATTERNS) {
    if (annotationCount >= maxAnnotations) break;

    const matches = narration.match(pattern);
    if (!matches) continue;

    for (const match of matches) {
      if (annotationCount >= maxAnnotations) break;

      // Skip common words
      const lowerMatch = match.toLowerCase();
      if (SKIP_WORDS.has(lowerMatch)) continue;

      // Skip if too short
      if (match.length < 3) continue;

      // Find approximate position in the narration
      const wordIndex = words.findIndex((w) =>
        w.toLowerCase().includes(lowerMatch)
      );
      if (wordIndex === -1) continue;

      // Convert word index to frame timing
      const wordRatio = wordIndex / totalWords;
      const startFrame = Math.floor(wordRatio * durationInFrames * 0.8) + 15;

      annotations.push({
        type,
        target: match,
        startFrame: Math.min(startFrame, durationInFrames - 30),
      });

      annotationCount++;
    }
  }

  return annotations;
}

/**
 * Determine if a scene needs annotations based on its content.
 */
export function needsAnnotations(narration: string): boolean {
  // Scenes with longer narration are more likely to benefit from annotations
  const wordCount = narration.split(/\s+/).length;
  return wordCount > 30;
}
