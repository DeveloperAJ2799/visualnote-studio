import React from "react";
import { AbsoluteFill, Sequence, staticFile } from "remotion";
import { Audio } from "@remotion/media";
import { GrainOverlay } from "./components/GrainOverlay";
import { SceneTransition } from "./components/SceneTransition";
import Scene001 from "./scenes/Scene001";
import Scene002 from "./scenes/Scene002";
import type { CourseReelProps, Scene } from "./types";

function renderScene(scene: Scene): React.ReactNode {
  switch (scene.scene_id) {
    case 1: return <Scene001 />;
    case 2: return <Scene002 />;
    default: return <div />;
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
          <Sequence key={scene.scene_id} from={start} durationInFrames={scene.durationInFrames}>
            <Audio src={staticFile(`scenes/scene_${String(scene.scene_id).padStart(3, "0")}_audio.wav`)} />
            <SceneTransition durationInFrames={scene.durationInFrames}>
              {renderScene(scene)}
            </SceneTransition>
          </Sequence>
        );
      })}
      <GrainOverlay />
    </AbsoluteFill>
  );
};
