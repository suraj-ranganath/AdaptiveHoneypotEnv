/** Workspace rooms from DESIGN §2.1 / §10. Positions are tool targets, not a seventh invented room. */

export const AREA_IDS = [
  "source",
  "ci",
  "deploy",
  "runbooks",
  "integrations",
  "service",
] as const;

export type AreaId = (typeof AREA_IDS)[number];

/**
 * Where an attacker stands. `bench` and `ops` are viewpoints, not extra rooms.
 * `withheld` means a file tool completed and the operator projection did not
 * include a path, so the token is not placed in a guessed room.
 */
export type StandId = AreaId | "bench" | "ops" | "withheld";

export const AREA_LABEL: Record<AreaId, string> = {
  source: "Source",
  ci: "CI",
  deploy: "Deploy",
  runbooks: "Runbooks",
  integrations: "Integrations",
  service: "Service",
};

/** Slot ids from DESIGN §3.1. */
export const SLOT_AREA: Record<string, AreaId> = {
  ci_records: "ci",
  deployment_notes: "deploy",
  runbooks: "runbooks",
  integration_records: "integrations",
};

export function isAreaId(value: string): value is AreaId {
  return (AREA_IDS as readonly string[]).includes(value);
}

export function standLabel(stand: StandId): string {
  if (stand === "bench") return "No tool target yet";
  if (stand === "withheld") return "Path withheld";
  if (stand === "ops") return "ops/";
  return AREA_LABEL[stand];
}

/** Map a workspace-relative path to a stand. Service tools do not use this. */
export function standForPath(path: string): StandId | null {
  const trimmed = path.trim().replace(/^\.\//, "").replace(/\/+$/, "");
  if (!trimmed || trimmed === ".") return "bench";
  if (trimmed === "ops") return "ops";
  if (trimmed === "source" || trimmed.startsWith("source/") || trimmed.startsWith("src/")) {
    return "source";
  }
  if (trimmed === "ops/ci" || trimmed.startsWith("ops/ci/")) return "ci";
  if (trimmed === "ops/deploy" || trimmed.startsWith("ops/deploy/")) return "deploy";
  if (trimmed === "ops/runbooks" || trimmed.startsWith("ops/runbooks/")) return "runbooks";
  if (trimmed === "ops/integrations" || trimmed.startsWith("ops/integrations/")) {
    return "integrations";
  }
  if (trimmed.startsWith("ops/")) return "ops";
  return "source";
}

export function areaForPath(path: string): AreaId | null {
  const stand = standForPath(path);
  if (stand === "bench" || stand === "ops" || stand === "withheld" || stand === null) return null;
  return stand;
}
