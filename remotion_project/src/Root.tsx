import React from "react";
import { Composition, CalculateMetadata } from "remotion";
import { CourseReel } from "./CourseReel";
import type { CourseReelProps } from "./types";

const FPS = 30;

const defaultProps: CourseReelProps = {
  course_title: "Untitled Course",
  fps: FPS,
  scenes: [
    {
      scene_id: 1,
      template: "title_intro",
      narration: "",
      fields: { title: "Untitled Course", subtitle: "A VisualNote production" },
      durationInFrames: 3 * FPS,
    },
  ],
};

const calculateDuration: CalculateMetadata<CourseReelProps> = ({
  props,
}) => {
  const totalFrames = props.scenes.reduce(
    (sum, s) => sum + s.durationInFrames,
    0
  );
  return {
    durationInFrames: Math.max(totalFrames, FPS),
    fps: props.fps ?? FPS,
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="CourseReel"
      component={CourseReel}
      durationInFrames={3 * FPS}
      fps={FPS}
      width={1920}
      height={1080}
      calculateMetadata={calculateDuration}
      defaultProps={defaultProps}
    />
  );
};
