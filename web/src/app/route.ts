/**
 * Whether the URL names a project (`?project=`). Without one the app shows the
 * start page instead of opening the default `demo` project, so the first screen
 * is the example gallery rather than an empty canvas.
 */
export function hasProjectRoute(search?: string): boolean {
  const raw = search ?? (typeof window === "undefined" ? "" : window.location.search);
  const project = new URLSearchParams(raw).get("project");
  return project !== null && project.trim().length > 0;
}
