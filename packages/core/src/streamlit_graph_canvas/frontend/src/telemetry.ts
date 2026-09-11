/**
 * Browser metrics delivered as OTLP/HTTP JSON.
 *
 * Streamlit components v2 gives a component only `setStateValue` and
 * `setTriggerValue`, and both force a full script rerun. Routing metrics through
 * either would reintroduce exactly the rerun storms this canvas works to avoid,
 * so the browser posts straight to a collector the application configures. The
 * host CSP must allow that origin in `connect-src`; see `csp.telemetry_origin`.
 *
 * The payload is hand-built rather than pulled from the OpenTelemetry JS SDK.
 * The SDK would add several hundred kilobytes to a bundle that already ships
 * React Flow and ELK, and only counters and histograms are needed here.
 */

const SCOPE_NAME = "streamlit-graph-canvas";
const FLUSH_DELAY_MS = 5_000;
const MAX_BUFFERED_POINTS = 512;

type Attributes = Record<string, string | number | boolean>;

type CounterPoint = {
  kind: "counter";
  name: string;
  unit: string;
  description: string;
  attributes: Attributes;
  value: number;
};

type HistogramPoint = {
  kind: "histogram";
  name: string;
  unit: string;
  description: string;
  attributes: Attributes;
  values: number[];
};

type Point = CounterPoint | HistogramPoint;

function attributeValue(value: string | number | boolean) {
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? { intValue: value }
      : { doubleValue: value };
  }
  if (typeof value === "boolean") return { boolValue: value };
  return { stringValue: value };
}

function attributeList(attributes: Attributes) {
  return Object.entries(attributes).map(([key, value]) => ({
    key,
    value: attributeValue(value),
  }));
}

function dataPoint(point: Point, startNanos: string, nowNanos: string) {
  const base = {
    attributes: attributeList(point.attributes),
    startTimeUnixNano: startNanos,
    timeUnixNano: nowNanos,
  };
  if (point.kind === "counter") return { ...base, asDouble: point.value };
  const count = point.values.length;
  return {
    ...base,
    count,
    sum: point.values.reduce((total, value) => total + value, 0),
    min: Math.min(...point.values),
    max: Math.max(...point.values),
    bucketCounts: [count],
    explicitBounds: [],
  };
}

/**
 * Build one OTLP metric per name, carrying every attribute set as a separate
 * data point. Emitting the same metric name twice in one scope is invalid OTLP,
 * so points must be grouped rather than mapped one-to-one.
 */
function metricPayload(points: Point[], startNanos: string, nowNanos: string) {
  const first = points[0];
  const dataPoints = points.map((point) =>
    dataPoint(point, startNanos, nowNanos),
  );
  const shared = {
    name: first.name,
    unit: first.unit,
    description: first.description,
  };
  if (first.kind === "counter") {
    return {
      ...shared,
      sum: {
        // Delta temporality: each flush reports only what happened since the
        // previous one, so a dropped request loses one interval, not the series.
        aggregationTemporality: 1,
        isMonotonic: true,
        dataPoints,
      },
    };
  }
  return { ...shared, histogram: { aggregationTemporality: 1, dataPoints } };
}

function pointKey(name: string, attributes: Attributes): string {
  return `${name}|${JSON.stringify(attributes, Object.keys(attributes).sort())}`;
}

export class BrowserTelemetry {
  private readonly points = new Map<string, Point>();
  private timer: ReturnType<typeof setTimeout> | undefined;
  private readonly startNanos = `${Date.now()}000000`;
  private disposed = false;

  constructor(
    private readonly endpoint: string,
    private readonly resourceAttributes: Attributes = {},
    private readonly send: (url: string, body: string) => void = defaultSend,
  ) {}

  count(
    name: string,
    attributes: Attributes = {},
    unit = "1",
    description = "",
  ): void {
    if (this.disposed) return;
    const key = pointKey(name, attributes);
    const existing = this.points.get(key);
    if (existing && existing.kind === "counter") existing.value += 1;
    else if (!existing) {
      this.points.set(key, {
        kind: "counter",
        name,
        unit,
        description,
        attributes,
        value: 1,
      });
    }
    this.schedule();
  }

  record(
    name: string,
    seconds: number,
    attributes: Attributes = {},
    description = "",
    unit = "s",
  ): void {
    if (this.disposed || !Number.isFinite(seconds)) return;
    const key = pointKey(name, attributes);
    const existing = this.points.get(key);
    if (existing && existing.kind === "histogram") {
      // Bound memory if a collector is unreachable for a long time.
      if (existing.values.length < MAX_BUFFERED_POINTS)
        existing.values.push(seconds);
    } else if (!existing) {
      this.points.set(key, {
        kind: "histogram",
        name,
        unit,
        description,
        attributes,
        values: [seconds],
      });
    }
    this.schedule();
  }

  /** Time a synchronous block and record its duration in seconds. */
  time<T>(name: string, work: () => T, attributes: Attributes = {}): T {
    const started = performance.now();
    try {
      return work();
    } finally {
      this.record(name, (performance.now() - started) / 1000, attributes);
    }
  }

  private schedule(): void {
    if (this.timer !== undefined || this.disposed) return;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      this.flush();
    }, FLUSH_DELAY_MS);
  }

  flush(): void {
    if (this.points.size === 0) return;
    const nowNanos = `${Date.now()}000000`;
    const byName = new Map<string, Point[]>();
    for (const point of this.points.values()) {
      const group = byName.get(point.name);
      if (group) group.push(point);
      else byName.set(point.name, [point]);
    }
    const metrics = [...byName.values()].map((group) =>
      metricPayload(group, this.startNanos, nowNanos),
    );
    this.points.clear();
    const body = JSON.stringify({
      resourceMetrics: [
        {
          resource: { attributes: attributeList(this.resourceAttributes) },
          scopeMetrics: [{ scope: { name: SCOPE_NAME }, metrics }],
        },
      ],
    });
    try {
      this.send(this.endpoint, body);
    } catch {
      // Telemetry must never break a render. A failed flush drops one interval.
    }
  }

  dispose(): void {
    if (this.timer !== undefined) clearTimeout(this.timer);
    this.timer = undefined;
    this.flush();
    this.disposed = true;
  }
}

function defaultSend(url: string, body: string): void {
  // sendBeacon survives page unload, which is when the final flush usually runs.
  const beacon = navigator.sendBeacon?.bind(navigator);
  if (beacon && beacon(url, new Blob([body], { type: "application/json" })))
    return;
  void fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => undefined);
}

export function createTelemetry(
  endpoint: string | null | undefined,
  resourceAttributes: Attributes = {},
): BrowserTelemetry | null {
  return endpoint ? new BrowserTelemetry(endpoint, resourceAttributes) : null;
}
