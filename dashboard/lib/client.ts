import createClient from "openapi-fetch";
import type { components, paths } from "./openapi";

export const api = createClient<paths>();
export type Schema = components["schemas"];

export function writeHeaders(csrf: string) {
  return { "X-CSRF-Token": csrf };
}

export function errorMessage(error: unknown, fallback: string) {
  if (error && typeof error === "object" && "detail" in error && typeof error.detail === "string") {
    return error.detail;
  }
  return fallback;
}

export function runUrl(id: string) {
  return `/api/v1/runs/${encodeURIComponent(id)}`;
}
