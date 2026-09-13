import { ApiError, apiGet } from "./client";

export type DependencyState = "ok" | "error";

export interface Health {
  status: "ok" | "degraded";
  db: DependencyState;
  redis: DependencyState;
}

function isHealth(value: unknown): value is Health {
  return typeof value === "object" && value !== null && "status" in value;
}

/** Fetch backend health. A 503 still carries a health report, so it is returned, not thrown. */
export async function fetchHealth(): Promise<Health> {
  try {
    return await apiGet<Health>("/health/");
  } catch (error) {
    if (error instanceof ApiError && error.status === 503 && isHealth(error.body)) {
      return error.body;
    }
    throw error;
  }
}
