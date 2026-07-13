import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  spring,
  interpolate,
} from "remotion";
import { theme, springConfig, typography } from "../theme";
import { ChalkBackground } from "../components/ChalkBackground";
import { DiagramNode } from "../components/DiagramNode";
import { DiagramConnector } from "../components/DiagramConnector";
import { ConceptAnnotation } from "../components/ConceptAnnotation";
import type { Annotation } from "../types";

interface DiagramNodeData {
  x: number;
  y: number;
  label: string;
  sublabel?: string;
  color?: string;
  enterFrame: number;
  shape?: "circle" | "rect" | "diamond";
  size?: number;
}

interface DiagramConnectorData {
  from: number;
  to: number;
  drawFrame: number;
  label?: string;
  dashed?: boolean;
}

interface ConceptDiagramProps {
  title: string;
  nodes: DiagramNodeData[];
  connectors: DiagramConnectorData[];
  annotations?: Annotation[];
}

/**
 * ConceptDiagram - Visual diagram showing relationships between concepts.
 *
 * Nodes appear with spring physics, connectors draw on with stroke-dashoffset.
 * No bullet lists — visual concepts only.
 */
export const ConceptDiagram: React.FC<ConceptDiagramProps> = ({
  title,
  nodes,
  connectors,
  annotations = [],
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const titleScale = spring({
    frame,
    fps,
    config: springConfig,
  });

  const titleOpacity = interpolate(frame, [0, 12], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <ChalkBackground>
      <AbsoluteFill
        style={{
          padding: theme.padding,
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Title */}
        <div
          style={{
            opacity: titleOpacity,
            transform: `scale(${titleScale})`,
            transformOrigin: "left center",
            marginBottom: 40,
          }}
        >
          <h2
            style={{
              fontSize: typography.displayM,
              fontFamily: theme.fontFamilyDisplay,
              color: theme.chalkWhite,
              margin: 0,
              fontWeight: 700,
            }}
          >
            {title}
          </h2>
        </div>

        {/* Diagram */}
        <svg
          style={{
            position: "absolute",
            top: 140,
            left: theme.padding,
            width: theme.width - theme.padding * 2,
            height: theme.height - 180,
          }}
        >
          {/* Connectors first (behind nodes) */}
          {connectors.map((conn, i) => (
            <DiagramConnector
              key={`conn-${i}`}
              x1={nodes[conn.from].x}
              y1={nodes[conn.from].y}
              x2={nodes[conn.to].x}
              y2={nodes[conn.to].y}
              drawFrame={conn.drawFrame}
              label={conn.label}
              dashed={conn.dashed}
            />
          ))}

          {/* Nodes on top */}
          {nodes.map((node, i) => (
            <DiagramNode
              key={`node-${i}`}
              x={node.x}
              y={node.y}
              label={node.label}
              sublabel={node.sublabel}
              color={node.color}
              enterFrame={node.enterFrame}
              shape={node.shape}
              size={node.size}
            />
          ))}
        </svg>

        {/* Manual annotations */}
        {annotations.map((annotation, i) => (
          <ConceptAnnotation
            key={i}
            type={annotation.type}
            x={400}
            y={400}
            width={200}
            height={100}
            startFrame={annotation.startFrame}
            color={annotation.color}
          />
        ))}
      </AbsoluteFill>
    </ChalkBackground>
  );
};
