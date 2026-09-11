import {
  NAME_FIELD,
  operators,
  type SearchConfig,
  type SearchCriterion,
} from "./search-model";
import { useNodeSearch } from "./use-node-search";
export { useNodeSearch } from "./use-node-search";
const labels: Record<string, string> = {
  contains: "contains",
  eq: "equals",
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  known: "is known",
  unknown: "is unknown",
};

export function NodeSearchPanel({
  search,
  config,
  onNavigate,
  onSubmit,
  onApply,
  onClear,
}: {
  search: ReturnType<typeof useNodeSearch>;
  config: SearchConfig;
  onNavigate: (ids: string[]) => void;
  onSubmit: () => void;
  onApply: () => void;
  onClear: () => void;
}) {
  const { query, setQuery, fields, result, ids, current, setCurrent } = search;
  const edit = (index: number, change: Partial<SearchCriterion>) =>
    setQuery((q) => ({
      ...q,
      criteria: q.criteria.map((c, i) =>
        i === index ? { ...c, ...change } : c,
      ),
    }));
  const newRule = (key: string): SearchCriterion => {
    const f = fields.find((f) => f.key === key)!;
    return {
      field: key,
      operator: operators(f.kind)[0],
      value: f.kind === "choice" ? (f.choices?.[0] ?? "") : "",
    };
  };
  const step = (delta: number) => {
    const index = ids.indexOf(current ?? "");
    const next =
      index < 0
        ? delta > 0
          ? 0
          : ids.length - 1
        : (index + delta + ids.length) % ids.length;
    setCurrent(ids[next]);
    onNavigate([ids[next]]);
  };
  return (
    <details className="sgc-search-root">
      <summary>Find in this view</summary>
      <section
        className="sgc-search-panel nodrag nopan nowheel"
        aria-label="Find in this view"
        onKeyDown={(e) => e.stopPropagation()}
        onWheel={(e) => e.stopPropagation()}
      >
        <div className="sgc-search-row">
          <input
            aria-label="Find node names"
            placeholder="Find names (comma separated)"
            maxLength={256}
            value={query.query}
            onChange={(e) => setQuery((q) => ({ ...q, query: e.target.value }))}
          />
          <button
            type="button"
            onClick={() => {
              setQuery({
                query: "",
                criteria: [],
                matchMode: "all",
                includeContext: false,
              });
              setCurrent(null);
              onClear();
            }}
          >
            Clear search
          </button>
        </div>
        <div role="status" className="sgc-search-count">
          {result.valid
            ? result.active
              ? `${ids.length} matches among ${result.scopeCount} ${query.includeContext ? "displayed" : "active"} nodes`
              : `${result.scopeCount} ${query.includeContext ? "displayed" : "active"} nodes`
            : "Complete each filter with a valid value."}
        </div>
        <div className="sgc-search-row">
          <button type="button" disabled={!ids.length} onClick={() => step(-1)}>
            Previous match
          </button>
          <button type="button" disabled={!ids.length} onClick={() => step(1)}>
            Next match
          </button>
          <button
            type="button"
            disabled={!ids.length}
            onClick={() => onNavigate(ids)}
          >
            Fit matches
          </button>
        </div>
        {config.reorderThreshold != null && (
          <div className="sgc-search-apply">
            <button
              type="button"
              disabled={!result.active || !result.valid}
              onClick={onApply}
            >
              Apply search
            </button>
            <small>
              Typing previews matches. Apply moves matches first within groups
              of at least {config.reorderThreshold} searched nodes, respecting
              dependency direction. Clear restores normal order.
            </small>
          </div>
        )}
        <details>
          <summary>Filter criteria</summary>
          <label>
            Match{" "}
            <select
              aria-label="Filter combination"
              value={query.matchMode}
              onChange={(e) =>
                setQuery((q) => ({
                  ...q,
                  matchMode: e.target.value as "all" | "any",
                }))
              }
            >
              <option value="all">all criteria</option>
              <option value="any">any criteria</option>
            </select>
          </label>
          {query.criteria.map((rule, index) => {
            const f = fields.find((f) => f.key === rule.field) ?? NAME_FIELD;
            return (
              <div className="sgc-search-rule" key={index}>
                <select
                  aria-label={`Filter ${index + 1} field`}
                  value={rule.field}
                  title={f.description}
                  onChange={(e) => edit(index, newRule(e.target.value))}
                >
                  {fields.map((f) => (
                    <option key={f.key} value={f.key}>
                      {f.label}
                    </option>
                  ))}
                </select>
                <select
                  aria-label={`Filter ${index + 1} operator`}
                  value={rule.operator}
                  onChange={(e) => edit(index, { operator: e.target.value })}
                >
                  {operators(f.kind).map((op) => (
                    <option key={op} value={op}>
                      {labels[op]}
                    </option>
                  ))}
                </select>
                {!["known", "unknown"].includes(rule.operator) &&
                  (f.kind === "choice" ? (
                    <select
                      aria-label={`Filter ${index + 1} value`}
                      value={String(rule.value ?? "")}
                      onChange={(e) => edit(index, { value: e.target.value })}
                    >
                      {f.choices?.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      aria-label={`Filter ${index + 1} value`}
                      type={f.kind === "number" ? "number" : "text"}
                      step="any"
                      maxLength={256}
                      value={rule.value ?? ""}
                      onChange={(e) =>
                        edit(index, {
                          value:
                            f.kind === "number" && e.target.value !== ""
                              ? Number(e.target.value)
                              : e.target.value,
                        })
                      }
                    />
                  ))}
                <button
                  type="button"
                  aria-label={`Remove filter ${index + 1}`}
                  onClick={() =>
                    setQuery((q) => ({
                      ...q,
                      criteria: q.criteria.filter((_, i) => i !== index),
                    }))
                  }
                >
                  Remove
                </button>
                {f.description && <small>{f.description}</small>}
              </div>
            );
          })}
          <button
            type="button"
            disabled={query.criteria.length >= 8}
            onClick={() =>
              setQuery((q) => ({
                ...q,
                criteria: [...q.criteria, newRule(fields[1]?.key ?? "$label")],
              }))
            }
          >
            Add filter
          </button>
          <label className="sgc-search-context">
            <input
              type="checkbox"
              checked={query.includeContext}
              onChange={(e) =>
                setQuery((q) => ({ ...q, includeContext: e.target.checked }))
              }
            />
            Include context nodes
          </label>
          <small>
            Search covers displayed individual nodes. Collapsed members are
            excluded.
          </small>
        </details>
        {config.callbackEnabled && (
          <div className="sgc-search-callback">
            <button
              type="button"
              disabled={!result.active || !result.valid}
              onClick={onSubmit}
            >
              Send filters to app
            </button>
            <small>
              This callback reruns Streamlit and may repeat queries,
              calculations, and rendering. Typing and filtering stay local.
            </small>
          </div>
        )}
      </section>
    </details>
  );
}
