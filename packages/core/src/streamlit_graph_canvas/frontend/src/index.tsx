import { NodeLabel, LabelContainer } from "./node-label";
import { defaultLabelPolicy, type LabelPolicy } from "./label-layout";
import { searchOrder } from "./search-model";
import { absoluteNodes } from "./transition";
import { useNodeSearch, NodeSearchPanel } from "./node-search";
import type { SearchConfig, SearchRequest } from "./search-model";
import { applyDisplayBudget } from "./display-budget";
import type {
  FrontendRenderer,
  FrontendRendererArgs,
} from "@streamlit/component-v2-lib";
import {
  Background,
  BaseEdge,
  getSmoothStepPath,
  Controls,
  Handle,
  MiniMap,
  MarkerType,
  Position,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useUpdateNodeInternals,
  type Edge as FlowEdge,
  type EdgeProps,
  type Node as FlowNode,
  type NodeProps,
  type Viewport,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import React, {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
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
  type AtlasPageDescriptor,
  type AtlasPageDelta,
} from "./atlas-cache";
import {
  cleanupJavascriptRenderer,
  RENDERER_REGISTRATION_EVENT,
  requireJavascriptRenderer,
  type JavascriptRendererRegistration,
  type JavascriptRendererRequirement,
} from "./javascript-registry";
import {
  planChildGroups,
  type ChildGroupSpec,
  type ResolvedGroup,
} from "./child-groups";
import { layoutGraph, type LayoutSize } from "./layout";
import { useMeasuredNodes } from "./use-measured-nodes";
import { useSceneTransition } from "./use-scene-transition";
import { tone, type Palette } from "./palette";
import { createTelemetry, type BrowserTelemetry } from "./telemetry";
import {
  imageLayerLocation,
  spriteCrop,
  validateSpriteLocation,
  type ImageLayer,
  type SpriteLocation,
} from "./sprite-location";
import "./style.css";

type State = {
  selected_node_ids: string[];
  viewport: Viewport | null;
  actions: CanvasAction[];
  search_request: SearchRequest | null;
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
  layoutHash?: string;
  topologyRevision: number;
  presentationRevision: number;
  state: ServerCanvasState & {
    atlasTheme: "light" | "dark";
    atlasResolution: number;
    atlasPageIds: string[];
    searchAcknowledgedSeq?: number;
  };
  javascriptRenderers: JavascriptRendererRequirement[];
  atlas: {
    pages: AtlasPageDelta[];
    removedPageIds: string[];
    policy: { maxPages: number; maxBytes: number };
    theme: "light" | "dark";
    resolution: number;
  };
  schema: {
    nodeTypes: Record<
      string,
      {
        style: NodeStyle;
        labelPolicy?: LabelPolicy;
        ports: Port[];
        childGroups?: ChildGroupSpec[];
      }
    >;
    edgeTypes: Record<
      string,
      {
        style: {
          stroke: string;
          width: number;
          dashed: boolean;
          arrow?: "none" | "source" | "target" | "both";
        };
      }
    >;
    palette: Palette;
  };
  topology: {
    nodes: Array<{
      id: string;
      type: string;
      width?: number;
      height?: number;
      layoutOrder?: number | null;
    }>;
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
      displayLabel?: string | null;
      data?: Record<string, unknown>;
      disabled: boolean;
      dimmed: boolean;
      opacity?: number | null;
      badges: BadgeView[];
    }>;
    edges: Array<{
      id: string;
      label?: string;
      dimmed: boolean;
      opacity?: number | null;
      emphasized?: boolean;
      optional?: boolean;
    }>;
  };
  config: {
    selection: "none" | "single" | "multiple";
    fitView: "never" | "initial" | "topology-change";
    transitionMs?: number;
    maxElements?: number;
    search?: SearchConfig | null;
    navigationAnchor?: string | null;
    height: number | "stretch";
    telemetryEndpoint?: string | null;
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
  transport: "prims" | "javascript" | "raster" | "atlas" | "sprite";
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
  sprite?: {
    pageId: string;
    x: number;
    y: number;
    width: number;
    height: number;
    resolution: number;
  };
  accessibleText?: string | null;
};
type NodeData = {
  label: string;
  displayLabel?: string | null;
  labelPolicy: LabelPolicy;
  typeName: string;
  dimmed: boolean;
  opacity?: number | null;
  disabled: boolean;
  badges: BadgeView[];
  palette: Palette;
  style: NodeStyle;
  ports: Port[];
  accessibleBadgeText: string;
  javascriptRenderers: Map<string, JavascriptRendererRegistration>;
  atlasPages: Map<string, AtlasPageDescriptor>;
  onKeyboardActivate: (event: React.KeyboardEvent<HTMLDivElement>) => void;
  groups: ResolvedGroup[];
  onToggleGroup: (groupId: string) => void;
};
type GroupData = {
  label: string;
  count: number;
  displayed?: number;
  expanded: boolean;
  onToggleGroup: (groupId: string) => void;
};
type SchemaFlowNode = FlowNode<NodeData, "schemaNode">;
type GroupFlowNode = FlowNode<GroupData, "groupNode">;
type CanvasNode = SchemaFlowNode | GroupFlowNode;

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

function SpriteBadge({
  badge,
  page,
  location,
}: {
  badge: BadgeView;
  page: AtlasPageDescriptor;
  location: SpriteLocation;
}) {
  const crop = spriteCrop(location, page);
  return (
    <svg
      className="sgc-badge"
      data-sgc-badge={badge.name}
      data-sgc-transport={badge.transport}
      data-sgc-page-id={location.pageId}
      aria-hidden="true"
      style={{
        left: badge.region.x,
        top: badge.region.y,
        width: badge.region.width,
        height: badge.region.height,
        overflow: "hidden",
      }}
      viewBox={crop.viewBox}
    >
      <image
        href={page.url}
        width={crop.imageWidth}
        height={crop.imageHeight}
        preserveAspectRatio="none"
      />
    </svg>
  );
}

function BadgeLayer({
  badge,
  palette,
  javascriptRenderers,
  atlasPages,
}: {
  badge: BadgeView;
  palette: Palette;
  javascriptRenderers: Map<string, JavascriptRendererRegistration>;
  atlasPages: Map<string, AtlasPageDescriptor>;
}) {
  if (badge.transport === "javascript") {
    const registration = javascriptRenderers.get(badge.kind);
    return registration ? (
      <JavascriptBadge
        badge={badge}
        palette={palette}
        registration={registration}
      />
    ) : null;
  }
  if (
    badge.transport === "raster" ||
    badge.transport === "atlas" ||
    badge.transport === "sprite"
  ) {
    const unvalidated = imageLayerLocation(badge as ImageLayer);
    const pageId =
      unvalidated &&
      typeof unvalidated === "object" &&
      "pageId" in unvalidated &&
      typeof unvalidated.pageId === "string"
        ? unvalidated.pageId
        : "";
    const page = atlasPages.get(pageId);
    if (!page) return null;
    const location = validateSpriteLocation(unvalidated, page, badge.region);
    return <SpriteBadge badge={badge} page={page} location={location} />;
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

const SchemaNode = memo(({ data, selected }: NodeProps<SchemaFlowNode>) => (
  <LabelContainer
    label={data.label}
    policy={data.labelPolicy}
    opacity={data.opacity ?? undefined}
  >
    {data.badges
      .filter((badge) => badge.layer === "under")
      .map((badge) => (
        <BadgeLayer
          key={badge.name}
          badge={badge}
          palette={data.palette}
          javascriptRenderers={data.javascriptRenderers}
          atlasPages={data.atlasPages}
        />
      ))}
    <div
      className={`sgc-node ${selected ? "selected" : ""} ${data.dimmed && data.opacity == null ? "dimmed" : ""}`}
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
      <svg className="sgc-node-outline" aria-hidden="true">
        <rect
          x="1"
          y="1"
          style={{
            width: "calc(100% - 2px)",
            height: "calc(100% - 2px)",
            strokeWidth: `calc(${selected ? 2.5 : 1.5}px / var(--sgc-zoom, 1))`,
          }}
          rx={data.style.radius}
          fill="none"
          stroke={
            selected
              ? "var(--st-primary-color)"
              : tone(data.palette, data.style.stroke)
          }
          strokeWidth={selected ? 2.5 : 1.5}
        />
      </svg>
      <NodeHandles ports={data.ports} />
      <span className="sgc-node-type">{data.typeName}</span>
      <NodeLabel
        text={data.displayLabel ?? data.label}
        policy={data.labelPolicy}
      />
    </div>
    <GroupMarkers groups={data.groups} onToggleGroup={data.onToggleGroup} />
    {data.badges
      .filter((badge) => badge.layer === "over")
      .map((badge) => (
        <BadgeLayer
          key={badge.name}
          badge={badge}
          palette={data.palette}
          javascriptRenderers={data.javascriptRenderers}
          atlasPages={data.atlasPages}
        />
      ))}
  </LabelContainer>
));

function GroupMarkers({
  groups,
  onToggleGroup,
}: {
  groups: ResolvedGroup[];
  onToggleGroup: (groupId: string) => void;
}) {
  if (groups.length === 0) return null;
  return (
    <div className="sgc-group-markers">
      {groups.map((group) => (
        <button
          key={group.id}
          type="button"
          className={`sgc-group-marker ${group.expanded ? "expanded" : ""}`}
          data-sgc-group={group.edgeType}
          data-sgc-expanded={group.expanded ? "true" : "false"}
          aria-expanded={group.expanded}
          aria-label={`${group.expanded ? "Collapse" : "Expand"} ${group.label}, ${group.memberIds.length} items`}
          title={`${group.label} (${group.memberIds.length} loaded${group.expanded ? `, ${group.renderedMemberCount ?? group.memberIds.length} shown` : ""})`}
          onClick={(event) => {
            // The node itself is a click target for selection, so a marker press
            // must not also register as selecting the node.
            event.stopPropagation();
            onToggleGroup(group.id);
          }}
          onKeyDown={(event) => event.stopPropagation()}
        >
          {group.expanded &&
          group.renderedMemberCount !== undefined &&
          group.renderedMemberCount < group.memberIds.length
            ? `${group.renderedMemberCount} / ${group.memberIds.length}`
            : group.memberIds.length}
        </button>
      ))}
    </div>
  );
}

const GroupNode = memo(({ id, data }: NodeProps<GroupFlowNode>) => (
  <div
    className="sgc-group"
    data-sgc-expanded={data.expanded ? "true" : "false"}
  >
    <Handle type="target" position={Position.Left} />
    <button
      type="button"
      className="sgc-group-header"
      aria-expanded={data.expanded}
      aria-label={`${data.expanded ? "Collapse" : "Expand"} ${data.label}, ${data.count} items`}
      onClick={(event) => {
        event.stopPropagation();
        data.onToggleGroup(id);
      }}
    >
      {data.label} ·{" "}
      {data.expanded &&
      data.displayed !== undefined &&
      data.displayed < data.count
        ? `${data.displayed} of ${data.count}`
        : data.count}
    </button>
  </div>
));

type RoutedFlowEdge = FlowEdge<{ route?: { x: number; y: number }[] }>;
function RoutedEdge(props: EdgeProps<RoutedFlowEdge>) {
  const route = props.data?.route;
  const fallback = getSmoothStepPath(props);
  const path = route?.length
    ? route
        .map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`)
        .join(" ")
    : fallback[0];
  const labelPoint = route?.[Math.floor(route.length / 2)];
  return (
    <BaseEdge
      id={props.id}
      path={path}
      style={props.style}
      markerEnd={props.markerEnd}
      markerStart={props.markerStart}
      label={props.label}
      labelX={labelPoint?.x ?? fallback[1]}
      labelY={labelPoint?.y ?? fallback[2]}
    />
  );
}
const edgeTypes = { routed: RoutedEdge };

const nodeTypes = { schemaNode: SchemaNode, groupNode: GroupNode };
type SetStateValue = FrontendRendererArgs<State, CanvasData>["setStateValue"];
type SetTriggerValue = FrontendRendererArgs<
  State,
  CanvasData
>["setTriggerValue"];
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
): boolean {
  if (managedRoots.get(host) !== entry || entry.generation !== generation)
    return false;
  host.dataset.sgcStatus = "unmounted";
  entry.root.unmount();
  managedRoots.delete(host);
  return true;
}

const telemetryByKey = new Map<string, BrowserTelemetry>();

function acquireTelemetry(
  key: string,
  endpoint: string | null | undefined,
): BrowserTelemetry | null {
  const existing = telemetryByKey.get(key);
  if (existing) return existing;
  const created = createTelemetry(endpoint, {
    "service.name": "streamlit-graph-canvas",
    "sgc.component.key": key,
  });
  if (created) telemetryByKey.set(key, created);
  return created;
}

function releaseTelemetry(key: string): void {
  const existing = telemetryByKey.get(key);
  if (!existing) return;
  telemetryByKey.delete(key);
  existing.dispose();
}

function isImageTransport(
  transport: BadgeView["transport"],
): transport is "raster" | "atlas" | "sprite" {
  return (
    transport === "raster" || transport === "atlas" || transport === "sprite"
  );
}

function imagePageIds(data: CanvasData): Set<string> {
  const pageIds = new Set<string>();
  for (const node of data.presentation.nodes) {
    for (const layer of node.badges) {
      for (const location of [layer.sprite, layer.atlas]) {
        if (location?.pageId) pageIds.add(location.pageId);
      }
    }
  }
  return pageIds;
}

function validateImageLayers(
  data: CanvasData,
  atlas: ReturnType<typeof acquireBrowserAtlasCache>,
): void {
  for (const node of data.presentation.nodes) {
    for (const layer of node.badges) {
      if (!isImageTransport(layer.transport)) continue;
      const location = imageLayerLocation(layer as ImageLayer);
      const pageId =
        location !== null &&
        typeof location === "object" &&
        "pageId" in location &&
        typeof location.pageId === "string"
          ? location.pageId
          : "";
      validateSpriteLocation(location, atlas.get(pageId), layer.region);
    }
  }
}

function atlasPageSnapshot(
  atlas: ReturnType<typeof acquireBrowserAtlasCache>,
): Map<string, AtlasPageDescriptor> {
  return new Map(
    atlas.ids().flatMap((pageId) => {
      const page = atlas.get(pageId);
      return page ? [[pageId, page] as const] : [];
    }),
  );
}

function CanvasContents({
  componentKey,
  data,
  initialState,
  topologyChanged,
  javascriptRenderers,
  atlasPages,
  setStateValue,
  setTriggerValue,
  onFatal,
  onSceneSettled,
  host,
}: {
  componentKey: string;
  data: CanvasData;
  initialState: BrowserCanvasState;
  topologyChanged: boolean;
  javascriptRenderers: Map<string, JavascriptRendererRegistration>;
  atlasPages: Map<string, AtlasPageDescriptor>;
  setStateValue: SetStateValue;
  setTriggerValue: SetTriggerValue;
  onFatal: (diagnostic: string) => void;
  onSceneSettled: (revision: string) => void;
  host: HTMLElement;
}) {
  const flow = useReactFlow();
  useEffect(() => {
    host.style.setProperty(
      "--sgc-zoom",
      String(initialState.viewport?.zoom ?? 1),
    );
  }, [host, initialState.viewport?.zoom]);
  const updateNodeInternals = useUpdateNodeInternals();
  const [selectedNodeIds, setSelectedNodeIds] = useState(
    initialState.selectedNodeIds,
  );
  const selectedNodeIdsRef = useRef(initialState.selectedNodeIds);
  const viewportRef = useRef(initialState.viewport);
  const actionSequence = useRef(initialState.nextSeq);
  const pendingActions = useRef(initialState.pendingActions);
  const [positions, setPositions] = useState(
    new Map<string, { x: number; y: number }>(),
  );
  // ELK sizes a container from its contents, so React Flow needs the measured
  // box rather than the declared one.
  const [routes, setRoutes] = useState(
    new Map<string, { x: number; y: number }[]>(),
  );
  const [layoutReadyKey, setLayoutReadyKey] = useState<string | null>(null);
  const [groupSizes, setGroupSizes] = useState(new Map<string, LayoutSize>());
  // Group ids the viewer flipped away from their declared default. Expansion is
  // browser-only: every child is already in the envelope, so opening a group
  // costs no rerun.
  const [toggledGroups, setToggledGroups] = useState<ReadonlySet<string>>(
    () => new Set<string>(),
  );
  const toggleGroup = useCallback((id: string) => {
    setToggledGroups((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }, []);
  const [appliedSearch, setAppliedSearch] = useState<{
    matchingIds: string[];
    scopeIds: string[];
    visualOrder: string[];
    anchor: string | null | undefined;
  } | null>(null);
  const geometryHash = data.layoutHash ?? data.topologyHash;
  const groupSpecs = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(data.schema.nodeTypes).map(([name, declaration]) => [
          name,
          declaration.childGroups ?? [],
        ]),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- geometryHash covers
    // geometry and grouping, so keying on it keeps this stable across reruns that
    // changed neither, which in turn keeps node positions from churning.
    [geometryHash],
  );
  const geometryPlan = useMemo(
    () =>
      applyDisplayBudget(
        data.topology.nodes,
        data.topology.edges,
        planChildGroups(
          data.topology.nodes,
          data.topology.edges,
          groupSpecs,
          toggledGroups,
        ),
        data.config.maxElements ?? 700,
        data.config.navigationAnchor,
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see above.
    [
      geometryHash,
      groupSpecs,
      toggledGroups,
      data.config.maxElements,
      data.config.navigationAnchor,
    ],
  );

  const plan = useMemo(() => {
    const types = new Map(
      data.topology.nodes.map((node) => [node.id, node.type]),
    );
    const groups = geometryPlan.groups.map((group) => ({
      ...group,
      label:
        data.schema.nodeTypes[types.get(group.parentId)!].childGroups?.find(
          (spec) => spec.edgeType === group.edgeType,
        )?.label || group.edgeType,
    }));
    const byParent = new Map<string, typeof groups>();
    for (const group of groups) {
      const siblings = byParent.get(group.parentId);
      if (siblings) siblings.push(group);
      else byParent.set(group.parentId, [group]);
    }
    return { ...geometryPlan, groups, byParent };
  }, [geometryPlan, data.schema.nodeTypes]);

  const appliedOrder = useMemo(
    () =>
      searchOrder(
        data.topology.nodes,
        data.topology.edges,
        plan.containerOf,
        plan.hiddenNodeIds,
        appliedSearch?.anchor === data.config.navigationAnchor
          ? appliedSearch
          : null,
        data.config.search?.reorderThreshold,
      ),
    [
      data.topologyHash,
      plan,
      appliedSearch,
      data.config.navigationAnchor,
      data.config.search?.reorderThreshold,
    ],
  );
  const movableContextIds = useMemo(
    () => new Set(appliedOrder.keys()),
    [appliedOrder],
  );
  const layoutKey =
    geometryHash +
    ":" +
    JSON.stringify([...toggledGroups].sort()) +
    ":" +
    data.config.maxElements +
    ":" +
    data.config.navigationAnchor +
    ":" +
    JSON.stringify([...appliedOrder]);

  useEffect(() => {
    const ids = new Set(data.topology.nodes.map((n) => n.id));
    const selected = selectedNodeIdsRef.current.filter((id) => ids.has(id));
    selectedNodeIdsRef.current = selected;
    setSelectedNodeIds(selected);
  }, [data.topologyHash]);

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
        pendingActions.current = appendPendingAction(
          pendingActions.current,
          action,
        );
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
  const nodes = useMemo<CanvasNode[]>(() => {
    // React Flow requires a container to appear before the members it owns.
    const containers: CanvasNode[] = plan.groups.map((group) => {
      const size = groupSizes.get(group.id);
      const width = size?.width ?? 220;
      const height = size?.height ?? 64;
      return {
        id: group.id,
        type: "groupNode" as const,
        position: positions.get(group.id) ?? { x: 0, y: 0 },
        width,
        height,
        measured: { width, height },
        style: { width, height },
        data: {
          label: group.label,
          count: group.memberIds.length,
          displayed: group.renderedMemberCount,
          expanded: group.expanded,
          onToggleGroup: toggleGroup,
        },
        selectable: false,
      };
    });
    const members = data.topology.nodes
      .filter((node) => !plan.hiddenNodeIds.has(node.id))
      .map((node): SchemaFlowNode => {
        const declaration = data.schema.nodeTypes[node.type];
        const presentation = presentationNodes.get(node.id)!;
        const width = node.width ?? declaration.style.width;
        const height = node.height ?? declaration.style.height;
        const accessibleBadgeText = presentation.badges
          .flatMap((badge) => [
            ...(badge.primitives ?? [])
              .filter(
                (
                  primitive,
                ): primitive is Extract<Primitive, { kind: "text" }> =>
                  primitive.kind === "text",
              )
              .map((primitive) => primitive.text),
            ...(badge.accessibleText ? [badge.accessibleText] : []),
          ])
          .join(" ");
        return {
          id: node.id,
          type: "schemaNode" as const,
          position: positions.get(node.id) ?? { x: 0, y: 0 },
          width,
          height,
          // React Flow discards internals.handleBounds when it re-adopts a node
          // object it has not seen before, unless the node reports `measured`.
          // Streamlit reruns hand us a freshly parsed envelope every time, so
          // without this the handle geometry is wiped on every rerun and every
          // edge is dropped until a ResizeObserver round trip restores it.
          measured: { width, height },
          style: {
            width,
            height,
          },
          data: {
            label: presentation.label,
            displayLabel: presentation.displayLabel,
            labelPolicy: declaration.labelPolicy ?? defaultLabelPolicy,
            typeName: node.type,
            dimmed: presentation.dimmed,
            opacity: presentation.opacity,
            disabled: presentation.disabled,
            badges: presentation.badges,
            palette: data.schema.palette,
            style: declaration.style,
            ports: declaration.ports,
            accessibleBadgeText: accessibleBadgeText
              ? `, ${accessibleBadgeText}`
              : "",
            javascriptRenderers,
            atlasPages,
            groups: plan.byParent.get(node.id) ?? [],
            onToggleGroup: toggleGroup,
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
          ...(plan.containerOf.has(node.id)
            ? { parentId: plan.containerOf.get(node.id) }
            : {}),
        };
      });
    return [...containers, ...members];
  }, [
    activateNode,
    atlasPages,
    data,
    groupSizes,
    javascriptRenderers,
    plan,
    positions,
    presentationNodes,
    selectedNodeIds,
    toggleGroup,
  ]);
  const edges = useMemo<FlowEdge[]>(() => {
    const groupEdges: FlowEdge[] = plan.groups.map((group) => ({
      id: group.id,
      source: group.parentId,
      target: group.id,
      type: "routed",
      data: { route: routes.get(group.id) },
      ...edgeMarkers(
        data.schema.edgeTypes[group.edgeType].style.arrow,
        tone(data.schema.palette, "muted"),
      ),
      style: {
        stroke: tone(data.schema.palette, "muted"),
        strokeWidth: 1.5,
        vectorEffect: "non-scaling-stroke",
        strokeDasharray: "4 4",
      },
    }));
    const drawn = data.topology.edges
      .filter(
        (edge) =>
          !plan.hiddenEdgeIds.has(edge.id) &&
          !plan.hiddenNodeIds.has(edge.source) &&
          !plan.hiddenNodeIds.has(edge.target),
      )
      .map((edge): FlowEdge => {
        const style = data.schema.edgeTypes[edge.type].style;
        const presentation = presentationEdges.get(edge.id)!;
        return {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          sourceHandle: edge.sourcePort,
          targetHandle: edge.targetPort,
          type: "routed",
          data: {
            route:
              edge.sourcePort || edge.targetPort
                ? undefined
                : routes.get(edge.id),
          },
          label: presentation.label,
          ...edgeMarkers(
            style.arrow,
            tone(
              data.schema.palette,
              presentation.emphasized ? "accent" : style.stroke,
            ),
          ),
          style: {
            stroke: tone(
              data.schema.palette,
              presentation.emphasized ? "accent" : style.stroke,
            ),
            strokeWidth: presentation.emphasized
              ? Math.max(2.5, style.width)
              : style.width,
            vectorEffect: "non-scaling-stroke",
            opacity: presentation.opacity ?? (presentation.dimmed ? 0.25 : 1),
            strokeDasharray: presentation.optional
              ? "2 5"
              : style.dashed
                ? "6 4"
                : undefined,
          },
        };
      });
    return [...groupEdges, ...drawn];
  }, [data, plan, presentationEdges, routes]);

  useEffect(() => {
    let active = true;
    host.dataset.sgcLayoutCount = String(
      Number(host.dataset.sgcLayoutCount ?? 0) + 1,
    );
    host
      .querySelector(".react-flow")
      ?.dispatchEvent(new Event("sgc:scene-change"));
    setLayoutReadyKey(null);
    const laidOut = [
      ...plan.groups.map((group) => ({
        id: group.id,
        // A declared size is only a floor: ELK grows the container to fit.
        width: 220,
        height: 64,
        direction: group.direction,
        orderComponents: group.memberIds.some((id) => appliedOrder.has(id)),
      })),
      ...data.topology.nodes
        .filter((node) => !plan.hiddenNodeIds.has(node.id))
        .map((node) => {
          const style = data.schema.nodeTypes[node.type].style;
          return {
            id: node.id,
            width: node.width ?? style.width,
            height: node.height ?? style.height,
            layoutOrder: appliedOrder.get(node.id) ?? node.layoutOrder,
            ...(plan.containerOf.has(node.id)
              ? { parentId: plan.containerOf.get(node.id) }
              : {}),
          };
        }),
    ];
    const laidOutIds = new Set(laidOut.map((node) => node.id));
    layoutGraph(
      laidOut,
      [
        ...plan.groups.map((group) => ({
          id: group.id,
          source: group.parentId,
          target: group.id,
        })),
        ...data.topology.edges
          .filter(
            (edge) =>
              !plan.hiddenEdgeIds.has(edge.id) &&
              laidOutIds.has(edge.source) &&
              laidOutIds.has(edge.target),
          )
          .map((edge) => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
          })),
      ],
      {
        orderComponents: [...appliedOrder.keys()].some(
          (id) => !plan.containerOf.has(id),
        ),
      },
    )
      .then(({ positions: nextPositions, sizes, routes: nextRoutes }) => {
        if (!active) return;
        setPositions(nextPositions);
        setGroupSizes(sizes);
        setRoutes(nextRoutes);
        setLayoutReadyKey(layoutKey);
        requestAnimationFrame(() => {
          if (active) updateNodeInternals([...laidOutIds]);
        });
      })
      .catch((error: unknown) => {
        if (active)
          onFatal(error instanceof Error ? error.message : String(error));
      });
    return () => {
      active = false;
    };
  }, [
    layoutKey,
    // geometryPlan stays stable across appearance-only schema updates.
    geometryPlan,
    updateNodeInternals,
  ]);

  useEffect(() => {
    // Surfaced for conformance tests and for diagnosing a schema whose declared
    // groups never fire.
    host.dataset.sgcGroupSpecs = String(
      Object.values(groupSpecs).reduce((total, list) => total + list.length, 0),
    );
    host.dataset.sgcGroups = String(plan.groups.length);
    host.dataset.sgcRenderedElements = String(plan.renderedElements);
    host.dataset.sgcBudgetOmittedNodes = String(plan.omittedNodes);
    host.dataset.sgcGroupedNodes = String(plan.hiddenNodeIds.size);
  }, [data.topology, groupSpecs, host, plan]);

  const animated = useSceneTransition(
    { nodes, edges },
    {
      ready: layoutReadyKey === layoutKey,
      maxElements: data.config.maxElements ?? 700,
      movableContextIds,
      hasSavedViewport: initialState.viewport !== null,
      layoutKey,
      revision: layoutKey + ":" + data.presentationRevision,
      duration: data.config.transitionMs ?? 250,
      anchor: data.config.navigationAnchor,
      fitView: data.config.fitView,
      flow,
      host,
      onSettled: (viewport) => {
        updateNodeInternals(nodes.map((n) => n.id));
        if (!sameViewport(viewportRef.current, viewport)) {
          viewportRef.current = viewport;
          persist({ viewport });
          setStateValue("viewport", viewport);
        }
        onSceneSettled(data.topologyRevision + ":" + data.presentationRevision);
      },
    },
  );

  const searchCorpus = useMemo(
    () =>
      data.config.search == null
        ? []
        : data.presentation.nodes.map((node) => ({
            id: node.id,
            label: node.label,
            data: node.data,
          })),
    [data.presentationRevision, data.config.search != null],
  );
  const renderedSearchIds =
    data.config.search == null
      ? []
      : animated.scene.nodes
          .filter(
            (node) =>
              !node.data.__transitionExiting && presentationNodes.has(node.id),
          )
          .map((node) => node.id);
  const search = useNodeSearch(
    data.config.search,
    searchCorpus,
    renderedSearchIds,
  );
  useEffect(() => {
    host.dataset.sgcSearchEvaluations = String(
      Number(host.dataset.sgcSearchEvaluations ?? 0) + 1,
    );
  }, [search.result, host]);
  const searchSequence = useRef(data.state.searchAcknowledgedSeq ?? 0);
  const matchingIds = new Set(search.enabled ? search.ids : []);
  const searchScope = new Set(search.result.scopeIds);
  const searchedNodes = !search.enabled
    ? animated.scene.nodes
    : animated.scene.nodes.map((node) => ({
        ...node,
        ...(search.enabled &&
        search.result.active &&
        search.result.valid &&
        searchScope.has(node.id) &&
        !matchingIds.has(node.id) &&
        data.config.search?.nonmatchOpacity != null
          ? {
              style: {
                ...node.style,
                opacity:
                  Number(node.style?.opacity ?? 1) *
                  data.config.search.nonmatchOpacity,
              },
            }
          : {}),
        className: [
          node.className,
          matchingIds.has(node.id) ? "sgc-search-match" : "",
          matchingIds.has(node.id) && search.current === node.id
            ? "sgc-search-current"
            : "",
        ]
          .filter(Boolean)
          .join(" "),
      }));
  const measured = useMeasuredNodes(searchedNodes);
  return (
    <ReactFlow
      nodes={measured.nodes}
      onNodesChange={measured.onNodesChange}
      edges={animated.scene.edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      nodesDraggable={false}
      nodesConnectable={false}
      minZoom={0.08}
      maxZoom={2.5}
      fitView={false}
      defaultViewport={initialState.viewport ?? undefined}
      onNodeClick={(event, node) => {
        // A group container is presentation, not graph data: it must never be
        // reported to the host as a node selection.
        if (
          node.type === "groupNode" ||
          node.data.__transitionExiting ||
          !data.topology.nodes.some((n) => n.id === node.id)
        )
          return;
        const nodeData = node.data as NodeData;
        if (nodeData.disabled) return;
        activateNode(node.id, nodeData.typeName, {
          shift: event.shiftKey,
          meta: event.metaKey,
          alt: event.altKey,
        });
      }}
      onPointerDownCapture={() => animated.interruptViewport()}
      onWheelCapture={() => animated.interruptViewport()}
      onMoveStart={(event) => {
        if (event) animated.interruptViewport();
      }}
      onMove={(_, viewport) => {
        host
          .querySelector(".react-flow")
          ?.dispatchEvent(new Event("sgc:scene-change"));
        // CSS transforms outside an SVG still scale its stroke. Updating one
        // inherited variable keeps screen-pixel borders without rerendering nodes.
        host.style.setProperty("--sgc-zoom", String(viewport.zoom));
      }}
      onMoveEnd={(_, viewport) => {
        if (animated.running.current) return;
        if (sameViewport(viewportRef.current, viewport)) return;
        viewportRef.current = viewport;
        persist({ viewport });
        setStateValue("viewport", viewport);
      }}
    >
      {(plan.omittedNodes > 0 || plan.omittedCollections > 0) && (
        <div className="sgc-budget-notice" role="status">
          Display budget ({data.config.maxElements ?? 700} elements):{" "}
          {plan.omittedNodes} nodes
          {plan.omittedCollections
            ? ` and ${plan.omittedCollections} collections`
            : ""}{" "}
          not shown. Collection totals include all loaded members. Collapse
          another collection to make room.
        </div>
      )}
      {data.config.search && (
        <Panel position="top-left">
          <NodeSearchPanel
            search={search}
            config={data.config.search}
            onApply={() =>
              setAppliedSearch({
                matchingIds: search.ids,
                scopeIds: search.result.scopeIds,
                visualOrder: absoluteNodes(flow.getNodes())
                  .sort(
                    (a, b) =>
                      a.position.y - b.position.y ||
                      a.position.x - b.position.x,
                  )
                  .map((n) => n.id),
                anchor: data.config.navigationAnchor,
              })
            }
            onClear={() => setAppliedSearch(null)}
            onNavigate={(ids) => {
              void flow.fitView({
                nodes: ids.map((id) => ({ id })),
                duration: 250,
                padding: 0.25,
                minZoom: 0.08,
                maxZoom: 1.5,
              });
            }}
            onSubmit={() => {
              searchSequence.current =
                Math.max(
                  searchSequence.current,
                  data.state.searchAcknowledgedSeq ?? 0,
                ) + 1;
              setTriggerValue("search_request", {
                ...search.query,
                matchingNodeIds: search.ids,
                sequence: searchSequence.current,
                topologyRevision: data.topologyRevision,
                presentationRevision: data.presentationRevision,
              });
            }}
          />
        </Panel>
      )}
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
  telemetry: BrowserTelemetry | null;
}) {
  const [runtimeRevision, setRuntimeRevision] = useState(0);
  const [fatalDiagnostic, setFatalDiagnostic] = useState<string | null>(null);
  const [activeData, setActiveData] = useState<CanvasData | null>(null);
  const [activeAtlasPages, setActiveAtlasPages] = useState<
    Map<string, AtlasPageDescriptor>
  >(new Map());
  const activePageIds = useRef<Set<string>>(new Set());
  const retiredPages = useRef<Set<string>[]>([]);
  const activeRevision = useRef("");
  activeRevision.current = activeData
    ? activeData.topologyRevision + ":" + activeData.presentationRevision
    : "";
  const stateData = activeData ?? props.data;
  const validNodeIds = useMemo(
    () => new Set(stateData.topology.nodes.map((node) => node.id)),
    [stateData.topologyHash],
  );
  const initial = useMemo(
    () =>
      loadCanvasState(
        props.componentKey,
        stateData.state,
        stateData.topologyHash,
        validNodeIds,
      ),
    [props.componentKey, stateData.topologyHash],
  );
  const [atlas] = useState(() => acquireBrowserAtlasCache(props.componentKey));
  useEffect(() => {
    let current = true;
    const protectedPageIds = imagePageIds(props.data);
    for (const pageId of activePageIds.current) protectedPageIds.add(pageId);
    const applyStarted = performance.now();
    void atlas
      .apply(
        props.data.atlas.pages,
        props.data.atlas.removedPageIds,
        props.data.atlas.policy,
        protectedPageIds,
        () => current,
      )
      .then((applied) => {
        if (!applied || !current) return;
        // Decoding, digesting and Blob-URL creation for incoming page deltas.
        props.telemetry?.record(
          "sgc.browser.atlas.apply.duration",
          (performance.now() - applyStarted) / 1000,
          { pages: props.data.atlas.pages.length },
        );
        validateImageLayers(props.data, atlas);
        const nextPageIds = imagePageIds(props.data);
        atlas.retain(nextPageIds);
        const previousPageIds = activePageIds.current;
        if (
          previousPageIds.size === nextPageIds.size &&
          [...previousPageIds].every((id) => nextPageIds.has(id))
        ) {
          atlas.release(previousPageIds);
        } else {
          retiredPages.current.push(previousPageIds);
        }
        activePageIds.current = nextPageIds;
        const pageIds = atlas.ids();
        if (
          JSON.stringify(pageIds) !==
          JSON.stringify(props.data.state.atlasPageIds)
        ) {
          props.setStateValue("atlas_page_ids", pageIds);
        }
        setActiveAtlasPages(atlasPageSnapshot(atlas));
        setActiveData(props.data);
        setRuntimeRevision((value) => value + 1);
      })
      .catch((error: unknown) => {
        if (current) {
          const message =
            error instanceof Error ? error.message : String(error);
          // The diagnostic prefix is a bounded vocabulary, so it is safe as a
          // metric attribute; the message itself is not and is never sent.
          props.telemetry?.count("sgc.browser.failures", {
            code: message.split(":", 1)[0] || "SGC_UNKNOWN",
          });
          setFatalDiagnostic(message);
        }
      });
    return () => {
      current = false;
    };
  }, [
    props.data.atlas.pages,
    props.data.config,
    props.data.atlas.policy,
    props.data.atlas.removedPageIds,
    props.data.topologyHash,
    props.data.presentation.edges,
    props.data.presentation.nodes,
  ]);

  useEffect(
    () => () => {
      atlas.release(activePageIds.current);
      for (const pages of retiredPages.current) atlas.release(pages);
      retiredPages.current = [];
      activePageIds.current = new Set();
    },
    [atlas],
  );

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
      const resolution =
        devicePixelRatio <= 1 ? 1 : devicePixelRatio <= 1.5 ? 1.5 : 2;
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
        setFatalDiagnostic(
          error instanceof Error ? error.message : String(error),
        );
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
        : !activeData
          ? "loading-atlas"
          : "ready";
  }, [
    activeData,
    effectiveFatal,
    missingRegistration,
    props.host,
    runtimeRevision,
  ]);

  if (effectiveFatal) {
    return (
      <div className="sgc-fatal" role="alert">
        {effectiveFatal}
      </div>
    );
  }
  if (missingRegistration) {
    return (
      <div className="sgc-loading" role="status">
        Loading renderer modules…
      </div>
    );
  }
  if (!activeData) {
    return (
      <div className="sgc-loading" role="status">
        Loading canvas images…
      </div>
    );
  }
  return (
    <ReactFlowProvider key={props.componentKey}>
      <CanvasContents
        {...props}
        data={activeData}
        initialState={initial.state}
        topologyChanged={initial.topologyChanged}
        javascriptRenderers={javascriptRenderers}
        atlasPages={activeAtlasPages}
        onSceneSettled={(revision) => {
          if (revision !== activeRevision.current) return;
          for (const pages of retiredPages.current) atlas.release(pages);
          retiredPages.current = [];
          props.host.dataset.sgcRenderedRevision = revision;
          const ids = atlas.ids();
          if (
            JSON.stringify(ids) !==
            JSON.stringify(props.data.state.atlasPageIds)
          )
            props.setStateValue("atlas_page_ids", ids);
        }}
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
  const telemetry = acquireTelemetry(key, data.config.telemetryEndpoint);
  telemetry?.count("sgc.browser.mounts", {
    generation: generation > 1 ? "update" : "initial",
  });
  telemetry?.record(
    "sgc.browser.graph.size",
    data.topology.nodes.length,
    {
      element: "node",
    },
    "Loaded node count",
    "{node}",
  );
  entry.root.render(
    <Canvas
      key={key}
      componentKey={key}
      data={data}
      setStateValue={setStateValue}
      setTriggerValue={setTriggerValue}
      host={host}
      telemetry={telemetry}
    />,
  );
  return () => {
    // Telemetry outlives individual data updates and is disposed only when the
    // React root is genuinely torn down, so its final flush happens once.
    if (releaseManagedRoot(host, entry, generation)) releaseTelemetry(key);
  };
};

export default renderer;

function edgeMarkers(arrow: string | undefined, color: string) {
  const marker = { type: MarkerType.ArrowClosed, color, width: 16, height: 16 };
  return {
    markerStart: arrow === "source" || arrow === "both" ? marker : undefined,
    markerEnd: arrow === "target" || arrow === "both" ? marker : undefined,
  };
}
