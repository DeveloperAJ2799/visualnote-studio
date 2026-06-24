export type TemplateName =
  | "title_intro"
  | "bullet_explainer"
  | "tool_showcase"
  | "comparison_table"
  | "step_process"
  | "quote_highlight"
  | "closing_cta";

export interface Scene {
  scene_id: number;
  template: TemplateName;
  narration: string;
  fields: Record<string, unknown>;
  durationInFrames: number;
}

export interface CourseReelProps {
  course_title: string;
  scenes: Scene[];
  fps: number;
}

export interface TitleIntroProps {
  title: string;
  subtitle?: string;
}

export interface BulletExplainerProps {
  heading: string;
  bullets: string[];
}

export interface ToolShowcaseProps {
  tool_name: string;
  tool_logo_url?: string;
  description: string;
  link?: string;
}

export interface ComparisonTableProps {
  columns: string[];
  rows: string[][];
}

export interface StepProcessProps {
  steps: { label: string; description?: string }[];
}

export interface QuoteHighlightProps {
  quote_text: string;
  attribution?: string;
}

export interface ClosingCTAProps {
  heading: string;
  cta_text: string;
  links?: string[];
}
