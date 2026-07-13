import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, spring, interpolate, Easing } from "remotion";
import { theme, springConfig, typography } from "../theme";
import { ChalkBackground } from "../components/ChalkBackground";
import { ConceptAnnotation } from "../components/ConceptAnnotation";
import { DiagramNode } from "../components/DiagramNode";
import { DiagramConnector } from "../components/DiagramConnector";

export default function Scene001() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Title entrance animation
  const titleOpacity = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  const titleY = interpolate(frame, [0, 30], [50, 0], { extrapolateRight: "clamp" });

  // Diagram elements timing
  const enzymeEnter = 40;
  const substrateEnter = 70;
  const connectorDraw = 100;
  const catalystAnnotation = 130;
  const speedupAnnotation = 180;

  return (
    <ChalkBackground>
      <AbsoluteFill style={{ padding: 80, display: "flex", flexDirection: "column" }}>
        {/* Title */}
        <div style={{ 
          opacity: titleOpacity, 
          transform: `translateY(${titleY}px)`,
          marginBottom: 60 
        }}>
          <h2 style={{ 
            fontSize: typography.displayL, 
            fontFamily: theme.fontFamilyDisplay, 
            color: theme.chalkWhite, 
            margin: 0, 
            fontWeight: 700 
          }}>
            Enzymes
          </h2>
        </div>

        {/* Main visualization area */}
        <svg style={{ position: "relative", width: "100%", height: 480 }}>
          {/* Reaction pathway showing catalysis */}
          <DiagramConnector 
            x1={250} 
            y1={240} 
            x2={750} 
            y2={240} 
            drawFrame={connectorDraw} 
            drawDuration={25}
            color={theme.accentAmber}
            dashed={true}
          />
          
          {/* Arrow showing catalyzed reaction */}
          <DiagramConnector 
            x1={650} 
            y1={220} 
            x2={730} 
            y2={240} 
            drawFrame={connectorDraw + 30} 
            drawDuration={15}
            color={theme.accentAmber}
          />

          {/* Enzyme node */}
          <DiagramNode 
            x={150} 
            y={240} 
            label="Enzyme" 
            enterFrame={enzymeEnter}
            shape="circle" 
            size={140}
            color={theme.accentAmber}
          />

          {/* Substrate/Reactant */}
          <DiagramNode 
            x={350} 
            y={150} 
            label="Substrate" 
            enterFrame={substrateEnter}
            shape="rect" 
            size={100}
          />

          {/* Product */}
          <DiagramNode 
            x={650} 
            y={150} 
            label="Product" 
            enterFrame={substrateEnter + 20}
            shape="rect" 
            size={100}
          />

          {/* Catalyst annotation - highlighting the enzyme's role */}
          <ConceptAnnotation 
            type="underline" 
            x={120} 
            y={370} 
            width={180} 
            height={8} 
            startFrame={catalystAnnotation}
            drawDuration={20}
            color={theme.accentAmber}
          />

          {/* Speedup annotation */}
          <ConceptAnnotation 
            type="arrow" 
            x={480} 
            y={260} 
            width={120} 
            height={40} 
            startFrame={speedupAnnotation}
            drawDuration={25}
            color={theme.accentAmber}
          />
        </svg>
      </AbsoluteFill>
    </ChalkBackground>
  );
}