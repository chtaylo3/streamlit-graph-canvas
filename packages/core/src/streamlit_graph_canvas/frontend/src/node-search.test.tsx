// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NodeSearchPanel, useNodeSearch } from "./node-search";
import type { SearchConfig, SearchNode } from "./search-model";

afterEach(cleanup);

const nodes: SearchNode[] = [
  { id: "a", label: "alpha", data: { count: 1, tier: "gold" } },
  { id: "b", label: "beta", data: { count: 2, tier: "silver" } },
  { id: "c", label: "gamma", data: { count: 3, tier: "gold" } },
];
const config: SearchConfig = {
  fields: [
    { key: "count", label: "Count", kind: "number" },
    { key: "tier", label: "Tier", kind: "choice", choices: ["gold", "silver"] },
  ],
  activeIds: null,
  callbackEnabled: false,
  reorderThreshold: 2,
};

function Harness(props: { onNavigate: (ids: string[]) => void; onApply?: () => void; onClear?: () => void }) {
  const search = useNodeSearch(config, nodes, ["a", "b", "c"]);
  return (
    <div>
      <NodeSearchPanel
        search={search}
        config={config}
        onNavigate={props.onNavigate}
        onSubmit={() => {}}
        onApply={props.onApply ?? (() => {})}
        onClear={props.onClear ?? (() => {})}
      />
      <span data-testid="current">{search.current ?? ""}</span>
    </div>
  );
}

const nameInput = () => screen.getByRole("textbox", { name: "Find node names" });
const status = () => screen.getByRole("status").textContent;

describe("NodeSearchPanel", () => {
  it("keeps keystrokes inside the panel so canvas shortcuts do not fire", () => {
    const canvasKeys = vi.fn();
    const { container } = render(
      <div onKeyDown={canvasKeys}>
        <Harness onNavigate={() => {}} />
      </div>,
    );
    fireEvent.keyDown(nameInput(), { key: "Delete" });
    fireEvent.keyDown(nameInput(), { key: "+" });
    expect(canvasKeys).not.toHaveBeenCalled();
    // Outside the panel, keys still reach the canvas.
    fireEvent.keyDown(container.firstElementChild!, { key: "+" });
    expect(canvasKeys).toHaveBeenCalledTimes(1);
  });

  it("cycles through matches in both directions and wraps", () => {
    const onNavigate = vi.fn();
    render(<Harness onNavigate={onNavigate} />);
    const next = screen.getByRole("button", { name: "Next match" });
    const previous = screen.getByRole("button", { name: "Previous match" });
    expect(next).toHaveProperty("disabled", true);
    fireEvent.change(nameInput(), { target: { value: "a" } });
    expect(status()).toBe("3 matches among 3 active nodes");
    fireEvent.click(next);
    expect(screen.getByTestId("current").textContent).toBe("a");
    fireEvent.click(next);
    fireEvent.click(next);
    fireEvent.click(next);
    expect(screen.getByTestId("current").textContent).toBe("a");
    fireEvent.click(previous);
    expect(screen.getByTestId("current").textContent).toBe("c");
    expect(onNavigate).toHaveBeenLastCalledWith(["c"]);
    fireEvent.click(screen.getByRole("button", { name: "Fit matches" }));
    expect(onNavigate).toHaveBeenLastCalledWith(["a", "b", "c"]);
  });

  it("starts from the last match when stepping backwards with no current match", () => {
    const onNavigate = vi.fn();
    render(<Harness onNavigate={onNavigate} />);
    fireEvent.change(nameInput(), { target: { value: "a" } });
    fireEvent.click(screen.getByRole("button", { name: "Previous match" }));
    expect(onNavigate).toHaveBeenLastCalledWith(["c"]);
  });

  it("combines filters with all/any and removes individual filters", () => {
    render(<Harness onNavigate={() => {}} />);
    const add = screen.getByRole("button", { name: "Add filter" });
    fireEvent.click(add);
    fireEvent.change(screen.getByRole("spinbutton", { name: "Filter 1 value" }), {
      target: { value: "3" },
    });
    fireEvent.click(add);
    fireEvent.change(screen.getByRole("combobox", { name: "Filter 2 field" }), {
      target: { value: "tier" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Filter 2 value" }), {
      target: { value: "silver" },
    });
    // count >= 3 AND tier == silver matches nothing; OR matches gamma and beta.
    expect(status()).toBe("0 matches among 3 active nodes");
    fireEvent.change(screen.getByRole("combobox", { name: "Filter combination" }), {
      target: { value: "any" },
    });
    expect(status()).toBe("2 matches among 3 active nodes");
    fireEvent.click(screen.getByRole("button", { name: "Remove filter 2" }));
    expect(screen.queryByRole("combobox", { name: "Filter 2 field" })).toBeNull();
    expect(status()).toBe("1 matches among 3 active nodes");
  });

  it("switches operators and reports incomplete filters as invalid", () => {
    const onApply = vi.fn();
    render(<Harness onNavigate={() => {}} onApply={onApply} />);
    fireEvent.click(screen.getByRole("button", { name: "Add filter" }));
    expect(status()).toBe("Complete each filter with a valid value.");
    expect(screen.getByRole("button", { name: "Apply search" })).toHaveProperty("disabled", true);
    fireEvent.change(screen.getByRole("combobox", { name: "Filter 1 operator" }), {
      target: { value: "known" },
    });
    expect(screen.queryByRole("spinbutton", { name: "Filter 1 value" })).toBeNull();
    expect(status()).toBe("3 matches among 3 active nodes");
    fireEvent.click(screen.getByRole("button", { name: "Apply search" }));
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it("caps the number of filters at eight", () => {
    render(<Harness onNavigate={() => {}} />);
    const add = screen.getByRole("button", { name: "Add filter" });
    for (let i = 0; i < 8; i++) fireEvent.click(add);
    expect(add).toHaveProperty("disabled", true);
  });

  it("clears the query, filters, and current match", () => {
    const onClear = vi.fn();
    render(<Harness onNavigate={() => {}} onClear={onClear} />);
    fireEvent.change(nameInput(), { target: { value: "beta" } });
    fireEvent.click(screen.getByRole("button", { name: "Next match" }));
    fireEvent.click(screen.getByRole("button", { name: "Add filter" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(onClear).toHaveBeenCalledTimes(1);
    expect((nameInput() as HTMLInputElement).value).toBe("");
    expect(screen.queryByRole("button", { name: "Remove filter 1" })).toBeNull();
    expect(screen.getByTestId("current").textContent).toBe("");
    expect(status()).toBe("3 active nodes");
  });
});
