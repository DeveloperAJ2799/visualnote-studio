import React from "react";
import { Composition } from "remotion";
import { CourseReel } from "./CourseReel";
import type { CourseReelProps } from "./types";

const FPS = 30;

const defaultProps: CourseReelProps = {
  course_title: "Module 4 - Enzymes",
  fps: FPS,
  scenes: [
    {
      scene_id: 1,
      template: "title_intro",
      narration: "Enzymes are biological catalysts that speed up chemical reactions in living things.",
      fields: { title: "Enzymes: Nature's Catalysts", subtitle: "Molecular machines that power life" },
      durationInFrames: 6 * FPS,
    },
  ],
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="CourseReel"
      component={CourseReel as any}
      durationInFrames={90 * FPS}
      fps={FPS}
      width={1920}
      height={1080}
      defaultProps={defaultProps}
    />
  );
};
