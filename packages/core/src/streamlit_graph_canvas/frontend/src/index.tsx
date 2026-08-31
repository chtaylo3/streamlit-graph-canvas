import type { FrontendRenderer, FrontendRendererArgs } from "@streamlit/component-v2-lib";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge as FlowEdge,
  type Node as FlowNode,
  type NodeProps,
  type Viewport,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { layoutGraph } from "./layout";
import "./style.css";

type State = {
  selected_node_ids: string[];
  viewport: Viewport | null;
  actions: CanvasAction[];
};

type CanvasAction = {
  protocolVersion: 1;
  seq: number;
  operationId: string;
  gesture: "click";
  nodeId: string;
  nodeType: string;
  topologyRevision: number;
  target: { kind: "node" };
  modifiers: { shift: boolean; meta: boolean; alt: boolean };
};

type CanvasData = {
  topologyHash: string;
  topologyRevision: number;
  presentationRevision: number;
  schema: {
    nodeTypes: Record<string, { style: { width: number; height: number; fill: string; stroke: string; text: string; radius: number } }>;
    edgeTypes: Record<string, { style: { stroke: string; width: number; dashed: boolean } }>;
    palette: Record<string, { light: string; dark?: string }>;
  };
  topology: {
    nodes: Array<{ id: string; type: string; width?: number; height?: number }>;
    edges: Array<{ id: string; source: string; target: string; type: string }>;
  };
  presentation: {
    nodes: Array<{ id: string; label: string; disabled: boolean; dimmed: boolean; badges: BadgeView[] }>;
    edges: Array<{ id: string; label?: string; dimmed: boolean }>;
  };
  config: { selection: "none" | "single" | "multiple"; fitView: "never" | "initial" | "topology-change"; height: number | "stretch" };
};

type Primitive =
  | { kind: "rect"; x: number; y: number; width: number; height: number; radius: number; fill: string }
  | { kind: "circle"; cx: number; cy: number; radius: number; fill: string }
  | { kind: "text"; x: number; y: number; text: string; fill: string; size: number; anchor: "start" | "middle" | "end" };
type BadgeView = {
  name: string;
  layer: "under" | "over";
  region: { x: number; y: number; width: number; height: number };
  primitives?: Primitive[];
};
type NodeData = {
  label: string;
  typeName: string;
  dimmed: boolean;
  disabled: boolean;
  badges: BadgeView[];
  palette: CanvasData["schema"]["palette"];
  onKeyboardActivate: (event: React.KeyboardEvent<HTMLDivElement>) => void;
};
type CanvasNode = FlowNode<NodeData, "schemaNode">;

function BadgeLayer({ badge, palette }: { badge: BadgeView; palette: NodeData["palette"] }) {
  const tone = (name: string) => palette[name]?.light ?? "transparent";
  if (!badge.primitives) return null;
  return (
    <svg
      className="sgc-badge"
      data-sgc-badge={badge.name}
      aria-hidden="true"
      style={{ left: badge.region.x, top: badge.region.y, width: badge.region.width, height: badge.region.height }}
      viewBox={`0 0 ${badge.region.width} ${badge.region.height}`}
    >
      {badge.primitives.map((primitive, index) => {
        if (primitive.kind === "rect") return <rect key={index} x={primitive.x} y={primitive.y} width={primitive.width} height={primitive.height} rx={primitive.radius} fill={tone(primitive.fill)} />;
        if (primitive.kind === "circle") return <circle key={index} cx={primitive.cx} cy={primitive.cy} r={primitive.radius} fill={tone(primitive.fill)} />;
        return <text key={index} x={primitive.x} y={primitive.y} fill={tone(primitive.fill)} fontSize={primitive.size} textAnchor={primitive.anchor}>{primitive.text}</text>;
      })}
    </svg>
  );
}

const SchemaNode = memo(({ data, selected }: NodeProps<CanvasNode>) => (
  <div className="sgc-node-container">
    {data.badges.filter((badge) => badge.layer === "under").map((badge) => <BadgeLayer key={badge.name} badge={badge} palette={data.palette} />)}
    <div
      className={`sgc-node ${selected ? "selected" : ""} ${data.dimmed ? "dimmed" : ""}`}
      aria-disabled={data.disabled}
      aria-label={`${data.typeName} ${data.label}`}
      role="button"
      tabIndex={data.disabled ? -1 : 0}
      onKeyDown={(event) => {
        if (!data.disabled && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          data.onKeyboardActivate(event);
        }
      }}
    >
      <Handle type="target" position={Position.Top} />
      <span className="sgc-node-type">{data.typeName}</span>
      <strong>{data.label}</strong>
      <Handle type="source" position={Position.Bottom} />
    </div>
    {data.badges.filter((badge) => badge.layer === "over").map((badge) => <BadgeLayer key={badge.name} badge={badge} palette={data.palette} />)}
  </div>
));

const nodeTypes = { schemaNode: SchemaNode };

type SetStateValue = FrontendRendererArgs<State, CanvasData>["setStateValue"];
type SetTriggerValue = FrontendRendererArgs<State, CanvasData>["setTriggerValue"];

function Canvas({ data, setStateValue, setTriggerValue }: { data: CanvasData; setStateValue: SetStateValue; setTriggerValue: SetTriggerValue }) {
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const selectedNodeIdsRef = useRef<string[]>([]);
  const actionSequence = useRef(0);
  const activateNode = useCallback((
    nodeId: string,
    nodeType: string,
    modifiers: CanvasAction["modifiers"],
  ) => {
    if (data.config.selection === "none") return;
    const current = new Set(selectedNodeIdsRef.current);
    const next = data.config.selection === "multiple"
      ? current.has(nodeId) ? [...current].filter((id) => id !== nodeId) : [...current, nodeId]
      : [nodeId];
    selectedNodeIdsRef.current = next;
    setSelectedNodeIds(next);
    setStateValue("selected_node_ids", next);
    actionSequence.current += 1;
    setTriggerValue("actions", [{
      protocolVersion: 1,
      seq: actionSequence.current,
      operationId: crypto.randomUUID(),
      gesture: "click",
      nodeId,
      nodeType,
      topologyRevision: data.topologyRevision,
      target: { kind: "node" },
      modifiers,
    }]);
  }, [data.config.selection, data.topologyRevision, setStateValue, setTriggerValue]);
  const presentationNodes = useMemo(() => new Map(data.presentation.nodes.map((node) => [node.id, node])), [data.presentation.nodes]);
  const presentationEdges = useMemo(() => new Map(data.presentation.edges.map((edge) => [edge.id, edge])), [data.presentation.edges]);
  const baseNodes = useMemo<CanvasNode[]>(() => data.topology.nodes.map((node) => {
    const declaration = data.schema.nodeTypes[node.type];
    const presentation = presentationNodes.get(node.id)!;
    return {
      id: node.id,
      type: "schemaNode",
      position: { x: 0, y: 0 },
      style: { width: node.width ?? declaration.style.width, height: node.height ?? declaration.style.height },
      data: {
        label: presentation.label,
        typeName: node.type,
        dimmed: presentation.dimmed,
        disabled: presentation.disabled,
        badges: presentation.badges,
        palette: data.schema.palette,
        onKeyboardActivate: (event) => activateNode(node.id, node.type, {
          shift: event.shiftKey,
          meta: event.metaKey,
          alt: event.altKey,
        }),
      },
      selectable: !presentation.disabled && data.config.selection !== "none",
    };
  }), [activateNode, data, presentationNodes]);
  const edges = useMemo<FlowEdge[]>(() => data.topology.edges.map((edge) => {
    const style = data.schema.edgeTypes[edge.type].style;
    const presentation = presentationEdges.get(edge.id)!;
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: "smoothstep",
      label: presentation.label,
      style: { strokeWidth: style.width, opacity: presentation.dimmed ? 0.25 : 1, strokeDasharray: style.dashed ? "6 4" : undefined },
    };
  }), [data, presentationEdges]);
  const [nodes, setNodes] = useState(baseNodes);
  useEffect(() => {
    let active = true;
    layoutGraph(
      baseNodes.map((node) => ({ id: node.id, width: Number(node.style?.width ?? 180), height: Number(node.style?.height ?? 92) })),
      edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target })),
    ).then((positions) => {
      if (active) setNodes(baseNodes.map((node) => ({ ...node, position: positions.get(node.id) ?? node.position })));
    });
    return () => { active = false; };
  }, [data.topologyHash]);

  const selected = new Set(selectedNodeIds);
  return (
    <ReactFlowProvider>
      <ReactFlow
        nodes={nodes.map((node) => ({ ...node, selected: selected.has(node.id) }))}
        edges={edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        minZoom={0.08}
        maxZoom={2.5}
        fitView={data.config.fitView !== "never"}
        onNodeClick={(event, node) => {
          if (node.data.disabled) return;
          activateNode(node.id, node.data.typeName, {
            shift: event.shiftKey,
            meta: event.metaKey,
            alt: event.altKey,
          });
        }}
        onMoveEnd={(_, viewport) => setStateValue("viewport", viewport)}
      >
        <Background gap={22} size={1} />
        <Controls />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </ReactFlowProvider>
  );
}

const renderer: FrontendRenderer<State, CanvasData> = ({ parentElement, data, setStateValue, setTriggerValue }) => {
  const host = parentElement.querySelector<HTMLElement>(".sgc-root");
  if (!host) throw new Error("SGC_MOUNT_ROOT: component root was not found");
  host.dataset.sgcStatus = "mounting";
  host.dataset.sgcTopologyRevision = String(data.topologyRevision);
  host.dataset.sgcPresentationRevision = String(data.presentationRevision);
  host.style.height = typeof data.config.height === "number" ? `${data.config.height}px` : "100%";
  const root: Root = createRoot(host);
  root.render(<Canvas data={data} setStateValue={setStateValue} setTriggerValue={setTriggerValue} />);
  requestAnimationFrame(() => { host.dataset.sgcStatus = "ready"; });
  return () => {
    host.dataset.sgcStatus = "unmounted";
    root.unmount();
  };
};

export default renderer;
