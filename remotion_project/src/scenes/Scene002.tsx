import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate, Easing } from "remotion";
import { theme, springConfig, typography } from "../theme";
import { ChalkBackground } from "../components/ChalkBackground";
import { ConceptAnnotation } from "../components/ConceptAnnotation";
import { DiagramNode } from "../components/DiagramNode";
import { DiagramConnector } from "../components/DiagramConnector";

export default function Scene002() {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  const titleScale = spring({ frame, fps, config: springConfig });
  const titleOpacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });

  const enzymeEnter = spring({ frame: frame - 30, fps, config: springConfig });
  const enzymeOpacity = interpolate(frame, [30, 45], [0, 1], { extrapolateRight: "clamp" });

  const substrateEnter = spring({ frame: frame - 100, fps, config: springConfig });
  const substrateOpacity = interpolate(frame, [100, 115], [0, 1], { extrapolateRight: "clamp" });

  const substrateX = interpolate(frame, [100, 180], [width - 200, 580], { easing: Easing.out(Easing.cubic), extrapolateRight: "clamp" });
  const substrateY = interpolate(frame, [100, 180], [height * 0.25, height * 0.5], { easing: Easing.out(Easing.cubic), extrapolateRight: "clamp" });

  const connectorOpacity = interpolate(frame, [180, 200], [0, 1], { extrapolateRight: "clamp" });

  const annotationOpacity = interpolate(frame, [80, 100], [0, 1], { extrapolateRight: "clamp" });

  return (
    <ChalkBackground>
      <AbsoluteFill style={{ padding: theme.padding, display: "flex", flexDirection: "column" }}>
        <div style={{ opacity: titleOpacity, transform: `scale(${titleScale})`, transformOrigin: "left center", marginBottom: 40 }}>
          <h2 style={{ fontSize: typography.displayM, fontFamily: theme.fontFamilyDisplay, color: theme.chalkWhite, margin: 0, fontWeight: 700 }}>
            Enzyme Specificity
          </h2>
        </div>

        <svg style={{ position: "absolute", top: 140, left: theme.padding, width: width - theme.padding * 2, height: height - 180 }}>
          <DiagramConnector
            x1={580}
            y1={height * 0.5}
            x2={400}
            y2={height * 0.5}
            drawFrame={180}
            drawDuration={30}
            color={theme.chalkDim}
            dashed
          />

          <DiagramNode
            x={400}
            y={height * 0.5}
            label="Enzyme"
            sublabel="specific 3D shape"
            enterFrame={30}
            shape="circle"
            size={180}
            color={theme.accentAmber}
          />

          <DiagramNode
            x={substrateX}
            y={substrateY}
            label="Substrate"
            sublabel="complementary fit"
            enterFrame={100}
            shape="rect"
            size={100}
            color={theme.codeMint}
          />

          <ConceptAnnotation
            type="circle"
            x={320}
            y={height * 0.5 - 80}
            width={160}
            height={160}
            startFrame={80}
            drawDuration={30}
            color={theme.accentAmber}
            strokeWidth={5}
          />

          <text
            x={320}
            y={height * 0.5 - 110}
            textAnchor="middle"
            fontFamily={theme.fontFamilyHand}
            fontSize={28}
            fill={theme.accentAmber}
            opacity={annotationOpacity}
            style={{ pointerEvents: "none" }}
          >
            active site
          </text>
        </svg>
      </AbsoluteFill>
    </ChalkBackground>
  );
}