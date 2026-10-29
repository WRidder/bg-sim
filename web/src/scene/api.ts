/** Fetching a project's scene file and meshes (P5.1 endpoints, plan 3.7). */

import { API_BASE } from "../api/client";
import type { MeshSource } from "./build";

/** The scene file could not be fetched; `message` says what to do. */
export class SceneFetchError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "SceneFetchError";
  }
}

/** The last path segment: `scenes/arm.sdf` -> `arm.sdf`, `model://x/meshes/a.glb` -> `a.glb`. */
export function baseName(path: string): string {
  return path.replace(/[?#].*$/, "").split(/[/\\]/).pop() ?? path;
}

function url(project: string, kind: "scenes" | "meshes", file: string): string {
  return `${API_BASE}/api/projects/${encodeURIComponent(project)}/${kind}/${encodeURIComponent(baseName(file))}`;
}

/** `GET /api/projects/{p}/scenes/{file}`: the SDF text. */
export async function fetchSceneText(project: string, file: string, signal?: AbortSignal): Promise<string> {
  const target = url(project, "scenes", file);
  let response: Response;
  try {
    response = await fetch(target, { headers: { accept: "application/xml" }, signal });
  } catch (cause) {
    if (signal?.aborted) throw cause;
    throw new SceneFetchError(`cannot reach the bg-sim backend to load ${file}; check that it is running`, 0);
  }
  if (response.status === 404) {
    throw new SceneFetchError(`${file} does not exist in project ${project}; store the SDF file there, or fix the scene field of the model`, 404);
  }
  if (!response.ok) {
    throw new SceneFetchError(`the backend answered ${response.status} for ${file}; check the file name in the scene field of the model`, response.status);
  }
  return response.text();
}

/** `GET /api/projects/{p}/meshes/{file}` for the `<uri>` of a mesh visual. */
export function meshSource(project: string, signal?: AbortSignal): MeshSource {
  return async (uri) => {
    const response = await fetch(url(project, "meshes", uri), { signal });
    if (!response.ok) throw new Error(`the backend answered ${response.status}`);
    return new Uint8Array(await response.arrayBuffer());
  };
}
