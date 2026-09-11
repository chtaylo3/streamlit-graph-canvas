import { useEffect, useMemo, useState } from "react";
import {
  NAME_FIELD,
  compileSearch,
  searchNodes,
  type SearchConfig,
  type SearchNode,
  type SearchQuery,
} from "./search-model";

export function useNodeSearch(
  config: SearchConfig | null | undefined,
  nodes: SearchNode[],
  renderedIds: string[],
) {
  const [query, setQuery] = useState<SearchQuery>({
    query: "",
    criteria: [],
    matchMode: "all",
    includeContext: false,
  });
  const [current, setCurrent] = useState<string | null>(null);
  const fieldsKey = JSON.stringify(config?.fields ?? []);
  const fields = useMemo(
    () => [NAME_FIELD, ...(config?.fields ?? [])],
    [fieldsKey],
  );
  const activeKey = JSON.stringify(config?.activeIds ?? null);
  const activeIds = useMemo(
    () => (config?.activeIds == null ? null : new Set(config.activeIds)),
    [activeKey],
  );
  const corpus = useMemo(
    () => new Map(nodes.map((node) => [node.id, node])),
    [nodes],
  );
  // A geometry frame replaces node objects but leaves this membership key equal.
  const membershipKey = JSON.stringify(renderedIds);
  const visible = useMemo(
    () =>
      renderedIds.flatMap((id) => {
        const node = corpus.get(id);
        return node ? [node] : [];
      }),
    [corpus, membershipKey],
  );
  useEffect(() => {
    setQuery((q) =>
      q.criteria.every((c) => fields.some((f) => f.key === c.field))
        ? q
        : {
            ...q,
            criteria: q.criteria.filter((c) =>
              fields.some((f) => f.key === c.field),
            ),
          },
    );
  }, [fields]);
  const compiled = useMemo(() => compileSearch(fields, query), [fields, query]);
  const result = useMemo(
    () =>
      config == null
        ? {
            matches: [],
            scopeIds: [],
            scopeCount: 0,
            active: false,
            valid: true,
          }
        : searchNodes(visible, fields, query, activeIds, compiled),
    [config != null, visible, fields, query, activeIds, compiled],
  );
  const ids = useMemo(() => result.matches.map((node) => node.id), [result]);
  return {
    query,
    setQuery,
    current,
    setCurrent,
    fields,
    ids,
    result,
    enabled: config != null,
  };
}
