import { describe, expect, it, vi } from "vitest";
import { BrowserTelemetry, createTelemetry } from "./telemetry";

type Sent = { url: string; body: Record<string, any> };

function collector() {
  const sent: Sent[] = [];
  const send = (url: string, body: string) => {
    sent.push({ url, body: JSON.parse(body) });
  };
  return { sent, send };
}

function metricsOf(sent: Sent): any[] {
  return sent.body.resourceMetrics[0].scopeMetrics[0].metrics;
}

function named(sent: Sent, name: string): any {
  return metricsOf(sent).find((metric) => metric.name === name);
}

describe("browser telemetry", () => {
  it("is absent unless the application configures an endpoint", () => {
    expect(createTelemetry(null)).toBeNull();
    expect(createTelemetry(undefined)).toBeNull();
    expect(createTelemetry("")).toBeNull();
    expect(createTelemetry("https://otel.example/v1/metrics")).not.toBeNull();
  });

  it("emits OTLP JSON with resource and scope envelopes", () => {
    const { sent, send } = collector();
    const telemetry = new BrowserTelemetry(
      "https://otel.example/v1/metrics",
      { "service.name": "streamlit-graph-canvas" },
      send,
    );
    telemetry.count("sgc.browser.mounts", { generation: "initial" });
    telemetry.dispose();

    expect(sent).toHaveLength(1);
    expect(sent[0].url).toBe("https://otel.example/v1/metrics");
    const resource = sent[0].body.resourceMetrics[0];
    expect(resource.resource.attributes).toContainEqual({
      key: "service.name",
      value: { stringValue: "streamlit-graph-canvas" },
    });
    expect(resource.scopeMetrics[0].scope.name).toBe("streamlit-graph-canvas");
  });

  it("accumulates repeated counts into one delta data point", () => {
    const { sent, send } = collector();
    const telemetry = new BrowserTelemetry("https://otel.example", {}, send);
    telemetry.count("sgc.browser.failures", { code: "SGC_ATLAS_PNG" });
    telemetry.count("sgc.browser.failures", { code: "SGC_ATLAS_PNG" });
    telemetry.count("sgc.browser.failures", { code: "SGC_SPRITE_PAGE_MISSING" });
    telemetry.dispose();

    const failures = named(sent[0], "sgc.browser.failures");
    expect(failures.sum.dataPoints).toHaveLength(2);
    expect(failures.sum.aggregationTemporality).toBe(1);
    const png = failures.sum.dataPoints.find((point: any) =>
      point.attributes.some((attribute: any) =>
        attribute.value.stringValue === "SGC_ATLAS_PNG"
      )
    );
    expect(png.asDouble).toBe(2);
  });

  it("summarises durations as a histogram in seconds", () => {
    const { sent, send } = collector();
    const telemetry = new BrowserTelemetry("https://otel.example", {}, send);
    telemetry.record("sgc.browser.atlas.apply.duration", 0.25);
    telemetry.record("sgc.browser.atlas.apply.duration", 0.75);
    telemetry.dispose();

    const histogram = named(sent[0], "sgc.browser.atlas.apply.duration");
    const point = histogram.histogram.dataPoints[0];
    expect(histogram.unit).toBe("s");
    expect(point.count).toBe(2);
    expect(point.sum).toBeCloseTo(1);
    expect(point.min).toBeCloseTo(0.25);
    expect(point.max).toBeCloseTo(0.75);
  });

  it("drains its buffer on flush so an interval is never double counted", () => {
    const { sent, send } = collector();
    const telemetry = new BrowserTelemetry("https://otel.example", {}, send);
    telemetry.count("sgc.browser.mounts");
    telemetry.flush();
    telemetry.flush();
    expect(sent).toHaveLength(1);
  });

  it("never lets a failing collector break a render", () => {
    const failing = () => {
      throw new Error("collector unreachable");
    };
    const telemetry = new BrowserTelemetry("https://otel.example", {}, failing);
    telemetry.count("sgc.browser.mounts");
    expect(() => telemetry.dispose()).not.toThrow();
  });

  it("records the duration of a timed block and returns its value", () => {
    const { sent, send } = collector();
    const telemetry = new BrowserTelemetry("https://otel.example", {}, send);
    const result = telemetry.time("sgc.browser.layout.duration", () => 42);
    telemetry.dispose();

    expect(result).toBe(42);
    const histogram = named(sent[0], "sgc.browser.layout.duration");
    expect(histogram.histogram.dataPoints[0].count).toBe(1);
  });

  it("ignores non-finite durations rather than emitting NaN", () => {
    const { sent, send } = collector();
    const telemetry = new BrowserTelemetry("https://otel.example", {}, send);
    telemetry.record("sgc.browser.atlas.apply.duration", Number.NaN);
    telemetry.dispose();
    expect(sent).toHaveLength(0);
  });

  it("stops recording once disposed", () => {
    const { sent, send } = collector();
    const telemetry = new BrowserTelemetry("https://otel.example", {}, send);
    telemetry.dispose();
    telemetry.count("sgc.browser.mounts");
    telemetry.flush();
    expect(sent).toHaveLength(0);
  });

  it("buffers until the flush delay rather than posting per event", () => {
    vi.useFakeTimers();
    try {
      const { sent, send } = collector();
      const telemetry = new BrowserTelemetry("https://otel.example", {}, send);
      telemetry.count("sgc.browser.mounts");
      telemetry.count("sgc.browser.mounts");
      expect(sent).toHaveLength(0);
      vi.advanceTimersByTime(5_000);
      expect(sent).toHaveLength(1);
      expect(named(sent[0], "sgc.browser.mounts").sum.dataPoints[0].asDouble).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });
});

it("records graph size with a node-count unit instead of seconds", () => {
  const {sent, send} = collector();
  const telemetry = new BrowserTelemetry("https://otel.example", {}, send);
  telemetry.record("sgc.browser.graph.size", 2000, {element: "node"}, "Loaded node count", "{node}");
  telemetry.dispose();
  expect(named(sent[0], "sgc.browser.graph.size").unit).toBe("{node}");
  expect(named(sent[0], "sgc.browser.graph.size").histogram.dataPoints[0].sum).toBe(2000);
});
