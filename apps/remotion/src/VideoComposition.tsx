import React, { useEffect, useState } from "react";
import { Sequence } from "@remotion/react";
import { TitleCard } from "./scenes/TitleCard";
import { SplitComparison } from "./scenes/SplitComparison";
import { ListCascade } from "./scenes/ListCascade";
import { DataCallout } from "./scenes/DataCallout";
import { MediaFocus } from "./scenes/MediaFocus";
import { ConceptMap } from "./scenes/ConceptMap";

interface Scene {
  scene_id: string;
  audio_duration_s: number;
  frame_style: string;
  narration?: string;
  audio_url?: string;
  title?: string;
  primary_text?: string;
  secondary_text?: string;
  items?: string[];
  metric?: string;
  image_url?: string;
  visual_props?: Record<string, any>;
}

interface Manifest {
  scenes: Scene[];
}

const FRAME_RATE = 30;

export const VideoComposition: React.FC<{ manifest_url: string }> = ({
  manifest_url,
}) => {
  const [manifest, setManifest] = useState<Manifest | null>(null);

  useEffect(() => {
    fetch(manifest_url)
      .then((res) => res.json())
      .then((data) => setManifest(data))
      .catch(console.error);
  }, [manifest_url]);

  if (!manifest) return null;

  const renderScene = (scene: Scene, index: number) => {
    const durationInFrames = Math.round(scene.audio_duration_s * FRAME_RATE);
    const commonProps = {
      durationInFrames,
      audio_url: scene.audio_url,
    };

    const props = scene.visual_props || {};

    switch (scene.frame_style) {
      case "title_card":
        return (
          <TitleCard
            key={scene.scene_id}
            title={scene.title || props.primary_text || ""}
            visual_props={props}
            {...commonProps}
          />
        );
      case "split_comparison":
        return (
          <SplitComparison
            key={scene.scene_id}
            visual_props={{
              primary_text: props.primary_text || scene.primary_text || "",
              secondary_text: props.secondary_text || scene.secondary_text || "",
              items: props.items || scene.items || [],
            }}
            {...commonProps}
          />
        );
      case "list_cascade":
        return (
          <ListCascade
            key={scene.scene_id}
            title={scene.title || props.primary_text || ""}
            visual_props={{ items: props.items || scene.items || [] }}
            {...commonProps}
          />
        );
      case "data_callout":
        return (
          <DataCallout
            key={scene.scene_id}
            visual_props={{
              metric: props.metric || scene.metric || "",
              primary_text: props.primary_text || scene.primary_text || "",
            }}
            {...commonProps}
          />
        );
      case "qwen_image":
        return (
          <MediaFocus
            key={scene.scene_id}
            scene_id={parseInt(scene.scene_id, 10)}
            visual_props={{
              primary_text: props.primary_text || scene.primary_text || "",
              image_url: props.image_url || scene.image_url || "",
            }}
            {...commonProps}
          />
        );
      case "concept_map":
        return (
          <ConceptMap
            key={scene.scene_id}
            visual_props={{
              primary_text: props.primary_text || scene.primary_text || "",
              items: props.items || scene.items || [],
            }}
            {...commonProps}
          />
        );
      default:
        return (
          <TitleCard
            key={scene.scene_id}
            title={scene.title || scene.frame_style || "Scene"}
            visual_props={{ primary_text: scene.narration?.slice(0, 100) }}
            {...commonProps}
          />
        );
    }
  };

  return (
    <>
      {manifest.scenes.map((scene, index) => (
        <Sequence
          key={scene.scene_id}
          from={0}
          durationInFrames={Math.round(scene.audio_duration_s * FRAME_RATE)}
          name={scene.frame_style}
        >
          {renderScene(scene, index)}
        </Sequence>
      ))}
    </>
  );
};