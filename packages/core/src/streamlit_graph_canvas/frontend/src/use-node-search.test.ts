// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SearchConfig, SearchNode } from "./search-model";
import { useNodeSearch } from "./use-node-search";

const nodes: SearchNode[] = [
  { id: "a", label: "Requests", data: { high: 3, ecosystem: "PyPI" } },
  { id: "b", label: "urllib3", data: { high: 0, ecosystem: "PyPI" } },
  { id: "c", label: "requests-context", data: { high: 9 } },
];
const config = (fields: SearchConfig["fields"], activeIds: string[] | null = null): SearchConfig => ({
  fields,
  activeIds,
  callbackEnabled: false,
});
const high = { key: "high", label: "High", kind: "number" as const };
const ecosystem = { key: "ecosystem", label: "Ecosystem", kind: "choice" as const, choices: ["PyPI"] };

type Props = { config: SearchConfig | null; rendered: string[] };

function setup(initial: Props) {
  return renderHook(({ config, rendered }: Props) => useNodeSearch(config, nodes, rendered), {
    initialProps: initial,
  });
}

describe("useNodeSearch", () => {
  it("is disabled and empty when search is not configured", () => {
    const { result } = setup({ config: null, rendered: ["a", "b", "c"] });
    act(() => result.current.setQuery((q) => ({ ...q, query: "requests" })));
    expect(result.current.enabled).toBe(false);
    expect(result.current.ids).toEqual([]);
    expect(result.current.result.active).toBe(false);
  });

  it("matches only rendered nodes and follows membership changes", () => {
    const { result, rerender } = setup({ config: config([high]), rendered: ["a", "b"] });
    act(() => result.current.setQuery((q) => ({ ...q, query: "requests" })));
    expect(result.current.ids).toEqual(["a"]);
    rerender({ config: config([high]), rendered: ["a", "b", "c"] });
    expect(result.current.ids).toEqual(["a", "c"]);
  });

  it("prunes criteria for fields the app removed", () => {
    const { result, rerender } = setup({ config: config([high, ecosystem]), rendered: ["a", "b", "c"] });
    act(() =>
      result.current.setQuery((q) => ({
        ...q,
        criteria: [
          { field: "high", operator: "gt", value: 1 },
          { field: "ecosystem", operator: "eq", value: "PyPI" },
        ],
      })),
    );
    expect(result.current.ids).toEqual(["a"]);
    rerender({ config: config([high]), rendered: ["a", "b", "c"] });
    expect(result.current.query.criteria).toEqual([{ field: "high", operator: "gt", value: 1 }]);
    expect(result.current.ids).toEqual(["a", "c"]);
  });
});
