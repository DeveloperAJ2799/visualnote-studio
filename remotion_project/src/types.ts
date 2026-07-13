/**
 * IGWANI Design System - Type Definitions
 */

import type { AnnotationType } from "./components/ConceptAnnotation";

// === Template Types ===

export type TemplateName =
  | "title_intro"
  | "concept_diagram"
  | "process_flow"
  | "comparison_visual"
  | "callout_card"
  | "stat_beat"
  | "quote_highlight"
  | "closing_cta";

// === Scene Types ===

export interface Annotation {
  type: AnnotationType;
  target: string;
  startFrame: number;
  duration?: number;
  color?: string;
}

export interface Scene {
  scene_id: number;
  template: TemplateName;
  narration: string;
  fields: Record<string, unknown>;
  durationInFrames: number;
  annotations?: Annotation[];
}

export interface CourseReelProps {
  course_title: string;
  scenes: Scene[];
  fps: number;
}

// === Template Props ===

export interface TitleIntroProps {
  title: string;
  subtitle?: string;
  annotations?: Annotation[];
}

export interface ConceptDiagramProps {
  title: string;
  nodes: {
    x: number;
    y: number;
    label: string;
    sublabel?: string;
    color?: string;
    enterFrame: number;
    shape?: "circle" | "rect" | "diamond";
    size?: number;
  }[];
  connectors: {
    from: number;
    to: number;
    drawFrame: number;
    label?: string;
    dashed?: boolean;
  }[];
  annotations?: Annotation[];
}

export interface ProcessFlowProps {
  title: string;
  steps: {
    label: string;
    sublabel?: string;
    x: number;
    y: number;
    enterFrame: number;
  }[];
  annotations?: Annotation[];
}

export interface ComparisonVisualProps {
  title: string;
  leftLabel: string;
  rightLabel: string;
  leftItems: { label: string; sublabel?: string; color?: string }[];
  rightItems: { label: string; sublabel?: string; color?: string }[];
  annotations?: Annotation[];
}

export interface CalloutCardProps {
  text: string;
  x?: number;
  y?: number;
  enterFrame?: number;
}

export interface StatBeatProps {
  number: string;
  label: string;
  annotationCircle?: { x: number; y: number; width: number; height: number };
  enterFrame?: number;
  annotationFrame?: number;
}

export interface ToolShowcaseProps {
  tool_name: string;
  tool_logo_url?: string;
  description: string;
  link?: string;
  annotations?: Annotation[];
}

export interface ComparisonTableProps {
  columns: string[];
  rows: string[][];
  annotations?: Annotation[];
}

export interface StepProcessProps {
  steps: { label: string; description?: string }[];
  annotations?: Annotation[];
}

export interface QuoteHighlightProps {
  quote_text: string;
  attribution?: string;
  annotations?: Annotation[];
}

export interface ClosingCTAProps {
  heading: string;
  cta_text: string;
  links?: string[];
  annotations?: Annotation[];
}

// === Component Props ===

export interface ConceptAnnotationProps {
  type: AnnotationType;
  x: number;
  y: number;
  width: number;
  height: number;
  startFrame: number;
  drawDuration?: number;
  color?: string;
  strokeWidth?: number;
}

export interface CodeBlockProps {
  code: string;
  language?: string;
  title?: string;
  startFrame?: number;
  lineRevealDelay?: number;
}
