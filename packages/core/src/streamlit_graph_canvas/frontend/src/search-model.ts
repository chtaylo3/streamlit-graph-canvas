export type SearchField = {
  key: string;
  label: string;
  kind: "text" | "number" | "choice";
  choices?: string[];
  description?: string;
};
export type SearchConfig = {
  fields: SearchField[];
  activeIds: string[] | null;
  callbackEnabled: boolean;
  reorderThreshold?: number | null;
  nonmatchOpacity?: number | null;
};
export type SearchCriterion = {
  field: string;
  operator: string;
  value: string | number | null;
};
export type SearchQuery = {
  query: string;
  criteria: SearchCriterion[];
  matchMode: "all" | "any";
  includeContext: boolean;
};
export type SearchRequest = SearchQuery & {
  matchingNodeIds: string[];
  sequence: number;
  topologyRevision: number;
  presentationRevision: number;
};
export type SearchNode = {
  id: string;
  label: string;
  data?: Record<string, unknown>;
};
export const NAME_FIELD: SearchField = {
  key: "$label",
  label: "Name",
  kind: "text",
};
export const operators = (kind: SearchField["kind"]) => [
  ...(kind === "number"
    ? ["gte", "gt", "eq", "lte", "lt"]
    : kind === "choice"
      ? ["eq"]
      : ["contains", "eq"]),
  "known",
  "unknown",
];
export function validCriterion(
  rule: SearchCriterion,
  fields: readonly SearchField[],
): boolean {
  const f = fields.find((f) => f.key === rule.field);
  if (!f || !operators(f.kind).includes(rule.operator)) return false;
  if (rule.operator === "known" || rule.operator === "unknown") return true;
  if (f.kind === "number")
    return typeof rule.value === "number" && Number.isFinite(rule.value);
  if (typeof rule.value !== "string" || !rule.value.trim()) return false;
  return f.kind !== "choice" || (f.choices ?? []).includes(rule.value);
}
function criterionMatcher(rule: SearchCriterion, field: SearchField) {
  const expected =
    typeof rule.value === "string"
      ? rule.value.toLocaleLowerCase()
      : rule.value;
  return (node: SearchNode): boolean => {
    const value =
      rule.field === "$label" ? node.label : node.data?.[rule.field];
    const known =
      field.kind === "number"
        ? typeof value === "number" && Number.isFinite(value)
        : typeof value === "string";
    if (rule.operator === "unknown") return !known;
    if (rule.operator === "known") return known;
    if (!known) return false;
    if (field.kind === "number") {
      const a = value as number,
        b = rule.value as number;
      switch (rule.operator) {
        case "gt":
          return a > b;
        case "gte":
          return a >= b;
        case "lt":
          return a < b;
        case "lte":
          return a <= b;
        default:
          return a === b;
      }
    }
    if (field.kind === "choice") return value === rule.value;
    const actual = (value as string).toLocaleLowerCase();
    return rule.operator === "contains"
      ? actual.includes(expected as string)
      : actual === expected;
  };
}

export function matchCriterion(
  node: SearchNode,
  rule: SearchCriterion,
  fields: readonly SearchField[],
): boolean {
  const field = fields.find((field) => field.key === rule.field);
  return (
    !!field &&
    validCriterion(rule, fields) &&
    criterionMatcher(rule, field)(node)
  );
}

/** Compile field lookup, validation and query normalization once per query. */
export function compileSearch(
  fields: readonly SearchField[],
  query: SearchQuery,
) {
  const terms = query.query
    .split(",")
    .map((s) => s.trim().toLocaleLowerCase())
    .filter(Boolean);
  const active = terms.length > 0 || query.criteria.length > 0;
  const valid = query.criteria.every((rule) => validCriterion(rule, fields));
  const predicates = valid
    ? query.criteria.map((rule) =>
        criterionMatcher(
          rule,
          fields.find((field) => field.key === rule.field)!,
        ),
      )
    : [];
  return {
    active,
    valid,
    matches(node: SearchNode): boolean {
      if (!active || !valid) return false;
      const name = terms.length ? node.label.toLocaleLowerCase() : "";
      if (terms.length && !terms.some((term) => name.includes(term)))
        return false;
      if (!predicates.length) return true;
      return query.matchMode === "all"
        ? predicates.every((test) => test(node))
        : predicates.some((test) => test(node));
    },
  };
}

export function searchNodes(
  nodes: readonly SearchNode[],
  fields: readonly SearchField[],
  query: SearchQuery,
  activeIds: ReadonlySet<string> | null,
  compiled = compileSearch(fields, query),
) {
  const scope = nodes.filter(
    (node) =>
      query.includeContext || activeIds === null || activeIds.has(node.id),
  );
  return {
    matches: scope.filter(compiled.matches),
    scopeIds: scope.map((node) => node.id),
    scopeCount: scope.length,
    active: compiled.active,
    valid: compiled.valid,
  };
}

/** Explicitly applied matches rank first only within their existing peer group.
 * A frozen visual order keeps draft edits from shuffling nodes. */
export function searchOrder(
  nodes: readonly { id: string; type: string }[],
  edges: readonly { source: string; target: string }[],
  containers: ReadonlyMap<string, string>,
  hidden: ReadonlySet<string>,
  applied: {
    matchingIds: string[];
    scopeIds: string[];
    visualOrder: string[];
  } | null,
  threshold: number | null | undefined,
): Map<string, number> {
  if (!applied || threshold == null) return new Map();
  const scope = new Set(applied.scopeIds),
    matches = new Set(applied.matchingIds);
  const ranks = new Map(applied.visualOrder.map((id, i) => [id, i]));
  const parents = new Map<string, Set<string>>();
  for (const e of edges) {
    const ids = parents.get(e.target) ?? new Set<string>();
    ids.add(e.source);
    parents.set(e.target, ids);
  }
  const groups = new Map<string, string[]>();
  for (const n of nodes)
    if (!hidden.has(n.id)) {
      const key =
        containers.get(n.id) ??
        JSON.stringify([n.type, [...(parents.get(n.id) ?? [])].sort()]);
      const ids = groups.get(key) ?? [];
      ids.push(n.id);
      groups.set(key, ids);
    }
  const order = new Map<string, number>();
  for (const members of groups.values()) {
    members.sort(
      (a, b) =>
        (ranks.get(a) ?? Infinity) - (ranks.get(b) ?? Infinity) ||
        a.localeCompare(b),
    );
    const eligible = members.filter((id) => scope.has(id));
    if (
      eligible.length < threshold ||
      !eligible.some((id) => matches.has(id)) ||
      eligible.every((id) => matches.has(id))
    )
      continue;
    eligible.sort((a, b) => Number(matches.has(b)) - Number(matches.has(a)));
    let index = 0;
    members
      .map((id) => (scope.has(id) ? eligible[index++] : id))
      .forEach((id, rank) => order.set(id, rank));
  }
  return order;
}
