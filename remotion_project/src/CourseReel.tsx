import React from "react";
import { AbsoluteFill, Sequence, staticFile } from "remotion";
import { Audio } from "@remotion/media";
import { TitleIntro } from "./templates/TitleIntro";
import { BulletExplainer } from "./templates/BulletExplainer";
import { ToolShowcase } from "./templates/ToolShowcase";
import { ComparisonTable } from "./templates/ComparisonTable";
import { StepProcess } from "./templates/StepProcess";
import { QuoteHighlight } from "./templates/QuoteHighlight";
import { ClosingCTA } from "./templates/ClosingCTA";
import type { CourseReelProps, Scene } from "./types";

function renderTemplate(scene: Scene): React.ReactNode {
  const f = scene.fields;
  switch (scene.template) {
    case "title_intro":
      return <TitleIntro title={f.title ?? ""} subtitle={f.subtitle} />;
    case "bullet_explainer":
      return (
        <BulletExplainer
          heading={f.heading ?? ""}
          bullets={Array.isArray(f.bullets) ? f.bullets : []}
        />
      );
    case "tool_showcase":
      return (
        <ToolShowcase
          tool_name={f.tool_name ?? ""}
          tool_logo_url={f.tool_logo_url}
          description={f.description ?? ""}
          link={f.link}
        />
      );
    case "comparison_table":
      return (
        <ComparisonTable
          columns={Array.isArray(f.columns) ? f.columns : []}
          rows={Array.isArray(f.rows) ? f.rows : []}
        />
      );
    case "step_process":
      return (
        <StepProcess
          steps={Array.isArray(f.steps) ? f.steps : []}
        />
      );
    case "quote_highlight":
      return (
        <QuoteHighlight
          quote_text={f.quote_text ?? ""}
          attribution={f.attribution}
        />
      );
    case "closing_cta":
      return (
        <ClosingCTA
          heading={f.heading ?? ""}
          cta_text={f.cta_text ?? ""}
          links={Array.isArray(f.links) ? f.links : undefined}
        />
      );
    default:
      return <TitleIntro title={f.title ?? "Untitled"} />;
  }
}

export const CourseReel: React.FC<CourseReelProps> = ({ scenes }) => {
  let fromFrame = 0;

  return (
    <AbsoluteFill>
      {scenes.map((scene) => {
        const start = fromFrame;
        fromFrame += scene.durationInFrames;
        return (
          <Sequence
            key={scene.scene_id}
            from={start}
            durationInFrames={scene.durationInFrames}
          >
            <Audio
              src={staticFile(`scenes/scene_${String(scene.scene_id).padStart(3, "0")}_audio.wav`)}
            />
            {renderTemplate(scene)}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
