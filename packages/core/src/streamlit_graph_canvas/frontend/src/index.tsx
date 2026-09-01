import type { FrontendRenderer, FrontendRendererArgs } from "@streamlit/component-v2-lib";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  useUpdateNodeInternals,
  type Edge as FlowEdge,
  type Node as FlowNode,
  type NodeProps,
  type Viewport,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import {
  loadCanvasState,
  sameViewport,
  selectNode,
  storeCanvasState,
  type BrowserCanvasState,
  type ServerCanvasState,
} from "./canvas-state";
import { requireCodecVersion } from "./codec";
import { appendPendingAction, clickAction, type CanvasAction } from "./events";
import {
  acquireBrowserAtlasCache,
  releaseBrowserAtlasCache,
  type AtlasPageDelta,
} from "./atlas-cache";
import {
  cleanupJavascriptRenderer,
  RENDERER_REGISTRATION_EVENT,
  requireJavascriptRenderer,
  type JavascriptRendererRegistration,
  type JavascriptRendererRequirement,
} from "./javascript-registry";
import { layoutGraph } from "./layout";
import { tone, type Palette } from "./palette";
import "./style.css";

type State = {
  selected_node_ids: string[];
  viewport: Viewport | null;
  actions: CanvasAction[];
  atlas_theme: "light" | "dark";
  atlas_resolution: number;
  atlas_page_ids: string[];
};

type NodeStyle = {
  width: number;
  height: number;
  fill: string;
  stroke: string;
  text: string;
  radius: number;
};
type Port = {
  name: string;
  side: "top" | "right" | "bottom" | "left";
  label?: string;
};
type CanvasData = {
  codecVersion: number;
  topologyHash: string;
  topologyRevision: number;
  presentationRevision: number;
  state: ServerCanvasState & {
    atlasTheme: "light" | "dark";
    atlasResolution: number;
    atlasPageIds: string[];
  };
  javascriptRenderers: JavascriptRendererRequirement[];
  atlas: {
    pages: AtlasPageDelta[];
    removedPageIds: string[];
    policy: { maxPages: number; maxBytes: number; scope: "session" | "tenant" };
    theme: "light" | "dark";
    resolution: number;
  };
  schema: {
    nodeTypes: Record<string, { style: NodeStyle; ports: Port[] }>;
    edgeTypes: Record<
      string,
      { style: { stroke: string; width: number; dashed: boolean } }
    >;
    palette: Palette;
  };
  topology: {
    nodes: Array<{ id: string; type: string; width?: number; height?: number }>;
    edges: Array<{
      id: string;
      source: string;
      target: string;
      type: string;
      sourcePort?: string;
      targetPort?: string;
    }>;
  };
  presentation: {
    nodes: Array<{
      id: string;
      label: string;
      disabled: boolean;
      dimmed: boolean;
      badges: BadgeView[];
    }>;
    edges: Array<{ id: string; label?: string; dimmed: boolean }>;
  };
  config: {
    selection: "none" | "single" | "multiple";
    fitView: "never" | "initial" | "topology-change";
    height: number | "stretch";
  };
};

type Primitive =
  | {
      kind: "rect";
      x: number;
      y: number;
      width: number;
      height: number;
      radius: number;
      fill: string;
    }
  | { kind: "circle"; cx: number; cy: number; radius: number; fill: string }
  | {
      kind: "text";
      x: number;
      y: number;
      text: string;
      fill: string;
      size: number;
      anchor: "start" | "middle" | "end";
    };
type BadgeView = {
  name: string;
  kind: string;
  transport: "prims" | "javascript" | "atlas";
  layer: "under" | "over";
  region: { x: number; y: number; width: number; height: number };
  primitives?: Primitive[];
  data?: unknown;
  options?: Record<string, unknown>;
  atlas?: {
    pageId: string;
    x: number;
    y: number;
    width: number;
    height: number;
    resolution: number;
  };
};
type NodeData = {
  label: string;
  typeName: string;
  dimmed: boolean;
  disabled: boolean;
  badges: BadgeView[];
  palette: Palette;
  style: NodeStyle;
  ports: Port[];
  accessibleBadgeText: string;
  javascriptRenderers: Map<string, JavascriptRendererRegistration>;
  atlasUrls: Map<string, string>;
  onKeyboardActivate: (event: React.KeyboardEvent<HTMLDivElement>) => void;
};
type CanvasNode = FlowNode<NodeData, "schemaNode">;

const portPositions = {
  top: Position.Top,
  right: Position.Right,
  bottom: Position.Bottom,
  left: Position.Left,
};

function JavascriptBadge({
  badge,
  palette,
  registration,
}: {
  badge: BadgeView;
  palette: Palette;
  registration: JavascriptRendererRegistration;
}) {
  const target = useRef<SVGSVGElement>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!target.current) return;
    const element = target.current;
    element.replaceChildren();
    try {
      const cleanup = registration.render({
        target: element,
        data: badge.data,
        options: badge.options ?? {},
        palette: Object.fromEntries(
          Object.keys(palette).map((name) => [name, tone(palette, name)]),
        ),
        region: badge.region,
      });
      setError(false);
      return () => {
        cleanupJavascriptRenderer(cleanup, element);
      };
    } catch {
      element.replaceChildren();
      setError(true);
      return undefined;
    }
  }, [badge, palette, registration]);
  return (
    <svg
      ref={target}
      className="sgc-badge"
      data-sgc-badge={badge.name}
      data-sgc-transport="javascript"
      data-sgc-render-error={error ? "true" : undefined}
      aria-hidden="true"
      style={{
        left: badge.region.x,
        top: badge.region.y,
        width: badge.region.width,
        height: badge.region.height,
      }}
      viewBox={`0 0 ${badge.region.width} ${badge.region.height}`}
    />
  );
}

function AtlasBadge({ badge, url }: { badge: BadgeView; url: string }) {
  if (!badge.atlas) return null;
  return (
    <svg
      className="sgc-badge"
      data-sgc-badge={badge.name}
      data-sgc-transport="atlas"
      aria-hidden="true"
      style={{
        left: badge.region.x,
        top: badge.region.y,
        width: badge.region.width,
        height: badge.region.height,
      }}
      viewBox={`0 0 ${badge.region.width} ${badge.region.height}`}
    >
      <image
        href={url}
        width={badge.region.width}
        height={badge.region.height}
        preserveAspectRatio="none"
      />
    </svg>
  );
}

function BadgeLayer({
  badge,
  palette,
  javascriptRenderers,
  atlasUrls,
}: {
  badge: BadgeView;
  palette: Palette;
  javascriptRenderers: Map<string, JavascriptRendererRegistration>;
  atlasUrls: Map<string, string>;
}) {
  if (badge.transport === "javascript") {
    const registration = javascriptRenderers.get(badge.kind);
    return registration ? (
      <JavascriptBadge badge={badge} palette={palette} registration={registration} />
    ) : null;
  }
  if (badge.transport === "atlas") {
    const url = badge.atlas ? atlasUrls.get(badge.atlas.pageId) : undefined;
    return url ? <AtlasBadge badge={badge} url={url} /> : null;
  }
  if (!badge.primitives) return null;
  return (
    <svg
      className="sgc-badge"
      data-sgc-badge={badge.name}
      data-sgc-transport="prims"
      aria-hidden="true"
      style={{
        left: badge.region.x,
        top: badge.region.y,
        width: badge.region.width,
        height: badge.region.height,
      }}
      viewBox={`0 0 ${badge.region.width} ${badge.region.height}`}
    >
      {badge.primitives.map((primitive, index) => {
        if (primitive.kind === "rect") {
          return (
            <rect
              key={index}
              x={primitive.x}
              y={primitive.y}
              width={primitive.width}
              height={primitive.height}
              rx={primitive.radius}
              fill={tone(palette, primitive.fill)}
            />
          );
        }
        if (primitive.kind === "circle") {
          return (
            <circle
              key={index}
              cx={primitive.cx}
              cy={primitive.cy}
              r={primitive.radius}
              fill={tone(palette, primitive.fill)}
            />
          );
        }
        return (
          <text
            key={index}
            x={primitive.x}
            y={primitive.y}
            fill={tone(palette, primitive.fill)}
            fontSize={primitive.size}
            textAnchor={primitive.anchor}
          >
            {primitive.text}
          </text>
        );
      })}
    </svg>
  );
}

function NodeHandles({ ports }: { ports: Port[] }) {
  if (ports.length === 0) {
    return (
      <>
        <Handle type="target" position={Position.Top} />
        <Handle type="source" position={Position.Bottom} />
      </>
    );
  }
  return ports.flatMap((port) => [
    <Handle
      key={`target:${port.name}`}
      id={port.name}
      type="target"
      position={portPositions[port.side]}
      aria-label={port.label ?? port.name}
    />,
    <Handle
      key={`source:${port.name}`}
      id={port.name}
      type="source"
      position={portPositions[port.side]}
      aria-label={port.label ?? port.name}
    />,
  ]);
}

const SchemaNode = memo(({ data, selected }: NodeProps<CanvasNode>) => (
  <div className="sgc-node-container">
    {data.badges
      .filter((badge) => badge.layer === "under")
      .map((badge) => (
        <BadgeLayer
          key={badge.name}
          badge={badge}
          palette={data.palette}
          javascriptRenderers={data.javascriptRenderers}
          atlasUrls={data.atlasUrls}
        />
      ))}
    <div
      className={`sgc-node ${selected ? "selected" : ""} ${data.dimmed ? "dimmed" : ""}`}
      aria-disabled={data.disabled}
      aria-label={`${data.typeName} ${data.label}${data.accessibleBadgeText}`}
      role="button"
      tabIndex={data.disabled ? -1 : 0}
      style={{
        background: tone(data.palette, data.style.fill),
        borderColor: tone(data.palette, data.style.stroke),
        color: tone(data.palette, data.style.text),
        borderRadius: data.style.radius,
      }}
      onKeyDown={(event) => {
        if (!data.disabled && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          data.onKeyboardActivate(event);
        }
      }}
    >
      <NodeHandles ports={data.ports} />
      <span className="sgc-node-type">{data.typeName}</span>
      <strong>{data.label}</strong>
    </div>
    {data.badges
      .filter((badge) => badge.layer === "over")
      .map((badge) => (
        <BadgeLayer
          key={badge.name}
          badge={badge}
          palette={data.palette}
          javascriptRenderers={data.javascriptRenderers}
          atlasUrls={data.atlasUrls}
        />
      ))}
  </div>
));

const nodeTypes = { schemaNode: SchemaNode };
type SetStateValue = FrontendRendererArgs<State, CanvasData>["setStateValue"];
type SetTriggerValue = FrontendRendererArgs<State, CanvasData>["setTriggerValue"];
type ManagedRoot = { root: Root; generation: number };
const managedRoots = new WeakMap<HTMLElement, ManagedRoot>();

function acquireManagedRoot(host: HTMLElement): {
  entry: ManagedRoot;
  generation: number;
} {
  let entry = managedRoots.get(host);
  if (!entry) {
    entry = { root: createRoot(host), generation: 0 };
    managedRoots.set(host, entry);
  }
  entry.generation += 1;
  return { entry, generation: entry.generation };
}

function releaseManagedRoot(
  host: HTMLElement,
  entry: ManagedRoot,
  generation: number,
): void {
  if (managedRoots.get(host) !== entry || entry.generation !== generation) return;
  host.dataset.sgcStatus = "unmounted";
  entry.root.unmount();
  managedRoots.delete(host);
}

function CanvasContents({
  componentKey,
  data,
  initialState,
  topologyChanged,
  javascriptRenderers,
  atlasUrls,
  setStateValue,
  setTriggerValue,
  onFatal,
}: {
  componentKey: string;
  data: CanvasData;
  initialState: BrowserCanvasState;
  topologyChanged: boolean;
  javascriptRenderers: Map<string, JavascriptRendererRegistration>;
  atlasUrls: Map<string, string>;
  setStateValue: SetStateValue;
  setTriggerValue: SetTriggerValue;
  onFatal: (diagnostic: string) => void;
}) {
  const flow = useReactFlow();
  const nodesInitialized = useNodesInitialized();
  const updateNodeInternals = useUpdateNodeInternals();
  const [selectedNodeIds, setSelectedNodeIds] = useState(initialState.selectedNodeIds);
  const selectedNodeIdsRef = useRef(initialState.selectedNodeIds);
  const viewportRef = useRef(initialState.viewport);
  const actionSequence = useRef(initialState.nextSeq);
  const pendingActions = useRef(initialState.pendingActions);
  const [positions, setPositions] = useState(
    new Map<string, { x: number; y: number }>(),
  );
  const [laidOutTopologyHash, setLaidOutTopologyHash] = useState<string | null>(null);
  const viewportAppliedTopology = useRef<string | null>(null);

  const persist = useCallback(
    (updates: Partial<BrowserCanvasState>) => {
      storeCanvasState(componentKey, {
        selectedNodeIds: selectedNodeIdsRef.current,
        viewport: viewportRef.current,
        acknowledgedSeq: data.state.acknowledgedSeq,
        nextSeq: actionSequence.current,
        pendingActions: pendingActions.current,
        topologyHash: data.topologyHash,
        ...updates,
      });
    },
    [componentKey, data.state.acknowledgedSeq, data.topologyHash],
  );

  useEffect(() => {
    actionSequence.current = Math.max(
      actionSequence.current,
      data.state.acknowledgedSeq,
    );
    pendingActions.current = pendingActions.current.filter(
      (action) => action.seq > data.state.acknowledgedSeq,
    );
    persist({
      acknowledgedSeq: data.state.acknowledgedSeq,
      nextSeq: actionSequence.current,
      pendingActions: pendingActions.current,
    });
    if (pendingActions.current.length > 0) {
      setTriggerValue("actions", pendingActions.current);
    }
  }, [data.state.acknowledgedSeq, persist, setTriggerValue]);

  const activateNode = useCallback(
    (
      nodeId: string,
      nodeType: string,
      modifiers: CanvasAction["modifiers"],
    ) => {
      if (data.config.selection === "none") return;
      const next = selectNode(
        selectedNodeIdsRef.current,
        nodeId,
        data.config.selection,
      );
      const nextSequence = actionSequence.current + 1;
      try {
        const action = clickAction(
          nextSequence,
          nodeId,
          nodeType,
          data.topologyRevision,
          modifiers,
        );
        pendingActions.current = appendPendingAction(pendingActions.current, action);
      } catch (error) {
        onFatal(error instanceof Error ? error.message : String(error));
        return;
      }
      selectedNodeIdsRef.current = next;
      setSelectedNodeIds(next);
      setStateValue("selected_node_ids", next);
      actionSequence.current = nextSequence;
      persist({
        selectedNodeIds: next,
        nextSeq: actionSequence.current,
        pendingActions: pendingActions.current,
      });
      setTriggerValue("actions", pendingActions.current);
    },
    [
      data.config.selection,
      data.topologyRevision,
      onFatal,
      persist,
      setStateValue,
      setTriggerValue,
    ],
  );

  const presentationNodes = useMemo(
    () => new Map(data.presentation.nodes.map((node) => [node.id, node])),
    [data.presentation.nodes],
  );
  const presentationEdges = useMemo(
    () => new Map(data.presentation.edges.map((edge) => [edge.id, edge])),
    [data.presentation.edges],
  );
  const nodes = useMemo<CanvasNode[]>(
    () =>
      data.topology.nodes.map((node) => {
        const declaration = data.schema.nodeTypes[node.type];
        const presentation = presentationNodes.get(node.id)!;
        const width = node.width ?? declaration.style.width;
        const height = node.height ?? declaration.style.height;
        const accessibleBadgeText = presentation.badges
          .flatMap((badge) => badge.primitives ?? [])
          .filter(
            (primitive): primitive is Extract<Primitive, { kind: "text" }> =>
              primitive.kind === "text",
          )
          .map((primitive) => primitive.text)
          .join(" ");
        return {
          id: node.id,
          type: "schemaNode",
          position: positions.get(node.id) ?? { x: 0, y: 0 },
          width,
          height,
          style: {
            width,
            height,
          },
          data: {
            label: presentation.label,
            typeName: node.type,
            dimmed: presentation.dimmed,
            disabled: presentation.disabled,
            badges: presentation.badges,
            palette: data.schema.palette,
            style: declaration.style,
            ports: declaration.ports,
            accessibleBadgeText: accessibleBadgeText
              ? `, ${accessibleBadgeText}`
              : "",
            javascriptRenderers,
            atlasUrls,
            onKeyboardActivate: (event) =>
              activateNode(node.id, node.type, {
                shift: event.shiftKey,
                meta: event.metaKey,
                alt: event.altKey,
              }),
          },
          selected: selectedNodeIds.includes(node.id),
          selectable:
            !presentation.disabled && data.config.selection !== "none",
        };
      }),
    [
      activateNode,
      atlasUrls,
      data,
      javascriptRenderers,
      positions,
      presentationNodes,
      selectedNodeIds,
    ],
  );
  const edges = useMemo<FlowEdge[]>(
    () =>
      data.topology.edges.map((edge) => {
        const style = data.schema.edgeTypes[edge.type].style;
        const presentation = presentationEdges.get(edge.id)!;
        return {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          sourceHandle: edge.sourcePort,
          targetHandle: edge.targetPort,
          type: "smoothstep",
          label: presentation.label,
          style: {
            stroke: tone(data.schema.palette, style.stroke),
            strokeWidth: style.width,
            opacity: presentation.dimmed ? 0.25 : 1,
            strokeDasharray: style.dashed ? "6 4" : undefined,
          },
        };
      }),
    [data, presentationEdges],
  );

  useEffect(() => {
    let active = true;
    layoutGraph(
      data.topology.nodes.map((node) => {
        const style = data.schema.nodeTypes[node.type].style;
        return {
          id: node.id,
          width: node.width ?? style.width,
          height: node.height ?? style.height,
        };
      }),
      data.topology.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
      })),
    ).then((nextPositions) => {
      if (!active) return;
      setPositions(nextPositions);
      requestAnimationFrame(() => {
        if (!active) return;
        updateNodeInternals(data.topology.nodes.map((node) => node.id));
        requestAnimationFrame(() => {
          if (active) setLaidOutTopologyHash(data.topologyHash);
        });
      });
    });
    return () => {
      active = false;
    };
  }, [data.topologyHash]);

  useEffect(() => {
    if (
      !nodesInitialized
      || laidOutTopologyHash !== data.topologyHash
      || viewportAppliedTopology.current === data.topologyHash
    ) return;
    const frame = requestAnimationFrame(() => {
      viewportAppliedTopology.current = data.topologyHash;
      if (initialState.viewport && !topologyChanged) {
        void flow.setViewport(initialState.viewport);
      } else if (
        data.config.fitView === "topology-change"
        || data.config.fitView === "initial"
      ) {
        void flow.fitView();
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [
    data.config.fitView,
    data.topologyHash,
    flow,
    initialState.viewport,
    laidOutTopologyHash,
    nodesInitialized,
    topologyChanged,
  ]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      nodesDraggable={false}
      nodesConnectable={false}
      minZoom={0.08}
      maxZoom={2.5}
      fitView={false}
      defaultViewport={initialState.viewport ?? undefined}
      onNodeClick={(event, node) => {
        if (node.data.disabled) return;
        activateNode(node.id, node.data.typeName, {
          shift: event.shiftKey,
          meta: event.metaKey,
          alt: event.altKey,
        });
      }}
      onMoveEnd={(_, viewport) => {
        if (sameViewport(viewportRef.current, viewport)) return;
        viewportRef.current = viewport;
        persist({ viewport });
        setStateValue("viewport", viewport);
      }}
    >
      <Background gap={22} size={1} />
      <Controls />
      <MiniMap pannable zoomable />
    </ReactFlow>
  );
}

function Canvas(props: {
  componentKey: string;
  data: CanvasData;
  setStateValue: SetStateValue;
  setTriggerValue: SetTriggerValue;
  host: HTMLElement;
}) {
  const [runtimeRevision, setRuntimeRevision] = useState(0);
  const [fatalDiagnostic, setFatalDiagnostic] = useState<string | null>(null);
  const validNodeIds = useMemo(
    () => new Set(props.data.topology.nodes.map((node) => node.id)),
    [props.data.topology.nodes],
  );
  const initial = useMemo(
    () =>
      loadCanvasState(
        props.componentKey,
        props.data.state,
        props.data.topologyHash,
        validNodeIds,
      ),
    [props.componentKey],
  );
  const [atlas] = useState(() => acquireBrowserAtlasCache(props.componentKey));
  useEffect(() => {
    let current = true;
    const protectedPageIds = new Set(
      props.data.presentation.nodes.flatMap((node) =>
        node.badges.flatMap((badge) => badge.atlas ? [badge.atlas.pageId] : []),
      ),
    );
    void atlas.apply(
        props.data.atlas.pages,
        props.data.atlas.removedPageIds,
        props.data.atlas.policy,
        protectedPageIds,
        () => current,
      )
      .then((applied) => {
        if (!applied || !current) return;
        const pageIds = atlas.ids();
        if (
          JSON.stringify(pageIds)
          !== JSON.stringify(props.data.state.atlasPageIds)
        ) {
          props.setStateValue("atlas_page_ids", pageIds);
        }
        setRuntimeRevision((value) => value + 1);
      })
      .catch((error: unknown) => {
        if (current) {
          setFatalDiagnostic(error instanceof Error ? error.message : String(error));
        }
      });
    return () => {
      current = false;
    };
  }, [
    props.data.atlas.pages,
    props.data.atlas.policy,
    props.data.atlas.removedPageIds,
    props.data.presentation.nodes,
  ]);

  useEffect(
    () => () => releaseBrowserAtlasCache(props.componentKey),
    [props.componentKey],
  );

  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const update = () => {
      const theme = media.matches ? "dark" : "light";
      if (theme !== props.data.state.atlasTheme) {
        props.setStateValue("atlas_theme", theme);
      }
      const resolution = devicePixelRatio <= 1 ? 1 : devicePixelRatio <= 1.5 ? 1.5 : 2;
      if (resolution !== props.data.state.atlasResolution) {
        props.setStateValue("atlas_resolution", resolution);
      }
    };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [props.data.state.atlasResolution, props.data.state.atlasTheme]);

  useEffect(() => {
    const update = () => setRuntimeRevision((value) => value + 1);
    globalThis.addEventListener(RENDERER_REGISTRATION_EVENT, update);
    const timeout = globalThis.setTimeout(() => {
      try {
        const missing = props.data.javascriptRenderers.filter(
          (requirement) => !requireJavascriptRenderer(requirement),
        );
        if (missing.length > 0) {
          setFatalDiagnostic(
            `SGC_JAVASCRIPT_REGISTRATION_MISSING: ${missing.map((item) => item.kind).join(", ")}`,
          );
        }
      } catch (error) {
        setFatalDiagnostic(error instanceof Error ? error.message : String(error));
      }
    }, 5_000);
    return () => {
      globalThis.removeEventListener(RENDERER_REGISTRATION_EVENT, update);
      globalThis.clearTimeout(timeout);
    };
  }, [props.data.javascriptRenderers]);

  let javascriptRenderers = new Map<string, JavascriptRendererRegistration>();
  let registryDiagnostic: string | null = null;
  try {
    javascriptRenderers = new Map(
      props.data.javascriptRenderers.flatMap((requirement) => {
        const registration = requireJavascriptRenderer(requirement);
        return registration ? [[requirement.kind, registration] as const] : [];
      }),
    );
  } catch (error) {
    registryDiagnostic = error instanceof Error ? error.message : String(error);
  }
  const effectiveFatal = fatalDiagnostic ?? registryDiagnostic;
  const missingRegistration =
    javascriptRenderers.size !== props.data.javascriptRenderers.length;
  useEffect(() => {
    props.host.dataset.sgcStatus = effectiveFatal
      ? "fatal"
      : missingRegistration
        ? "waiting-renderers"
        : "ready";
  }, [effectiveFatal, missingRegistration, props.host, runtimeRevision]);

  if (effectiveFatal) {
    return <div className="sgc-fatal" role="alert">{effectiveFatal}</div>;
  }
  if (missingRegistration) {
    return <div className="sgc-loading" role="status">Loading renderer modules…</div>;
  }
  const atlasUrls = new Map(
    atlas.ids().flatMap((pageId) => {
      const url = atlas.get(pageId);
      return url ? [[pageId, url] as const] : [];
    }),
  );
  return (
    <ReactFlowProvider>
      <CanvasContents
        {...props}
        initialState={initial.state}
        topologyChanged={initial.topologyChanged}
        javascriptRenderers={javascriptRenderers}
        atlasUrls={atlasUrls}
        onFatal={setFatalDiagnostic}
      />
    </ReactFlowProvider>
  );
}

const renderer: FrontendRenderer<State, CanvasData> = ({
  key,
  parentElement,
  data,
  setStateValue,
  setTriggerValue,
}) => {
  const host = parentElement.querySelector<HTMLElement>(".sgc-root");
  if (!host) {
    throw new Error("SGC_MOUNT_ROOT: component root was not found");
  }
  const { entry, generation } = acquireManagedRoot(host);
  try {
    requireCodecVersion(data.codecVersion);
  } catch (error) {
    host.dataset.sgcStatus = "fatal";
    entry.root.render(
      <div className="sgc-fatal" role="alert">
        {error instanceof Error ? error.message : String(error)}
      </div>,
    );
    return () => releaseManagedRoot(host, entry, generation);
  }
  host.dataset.sgcStatus = "mounting";
  host.dataset.sgcRenderGeneration = String(generation);
  host.dataset.sgcTopologyRevision = String(data.topologyRevision);
  host.dataset.sgcPresentationRevision = String(data.presentationRevision);
  host.style.height =
    typeof data.config.height === "number" ? `${data.config.height}px` : "100%";
  entry.root.render(
    <Canvas
      key={generation}
      componentKey={key}
      data={data}
      setStateValue={setStateValue}
      setTriggerValue={setTriggerValue}
      host={host}
    />,
  );
  return () => releaseManagedRoot(host, entry, generation);
};

export default renderer;
