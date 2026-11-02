/**
 * The three screens of the app, chosen by the URL:
 *
 * - no `?project=`: the start page (recent projects and the example gallery);
 * - `?project=p` without a model: the model picker of project `p` (a card per model);
 * - `?project=p&model=m`: the editor with model `m` open (a linkable, deep-linkable URL).
 *
 * Both project screens take `tab=` and `page=` (`readScreenTab`): `tab=docs` opens the project
 * page on its Docs tab and the editor on the Docs tab; `page=` names a docs page in the link
 * syntax (`project:<id>`, `model:<name>/<id>`; in the editor a bare `<id>` is a page of the open
 * model's docs).
 */

export type AppRoute =
  | { kind: "start" }
  | { kind: "picker"; project: string }
  | { kind: "editor"; project: string; model: string };

function currentSearch(search?: string): string {
  return search ?? (typeof window === "undefined" ? "" : window.location.search);
}

function param(params: URLSearchParams, name: string): string {
  return params.get(name)?.trim() ?? "";
}

export function readAppRoute(search?: string): AppRoute {
  const params = new URLSearchParams(currentSearch(search));
  const project = param(params, "project");
  if (project.length === 0) {
    return { kind: "start" };
  }
  const model = param(params, "model");
  return model.length === 0 ? { kind: "picker", project } : { kind: "editor", project, model };
}

/**
 * Whether the URL names a project (`?project=`). Without one the app shows the
 * start page instead of opening the default `demo` project, so the first screen
 * is the example gallery rather than an empty canvas.
 */
export function hasProjectRoute(search?: string): boolean {
  return readAppRoute(search).kind !== "start";
}

function currentHref(href?: string): string {
  return href ?? window.location.href;
}

/** The `tab=` and `page=` of the URL (`null` when absent or empty). */
export function readScreenTab(search?: string): { tab: string | null; page: string | null } {
  const params = new URLSearchParams(currentSearch(search));
  const tab = param(params, "tab");
  const page = param(params, "page");
  return { tab: tab === "" ? null : tab, page: page === "" ? null : page };
}

function withTab(url: URL, tab: string | null, page: string | null): string {
  url.searchParams.delete("tab");
  url.searchParams.delete("page");
  if (tab !== null) {
    url.searchParams.set("tab", tab);
  }
  if (page !== null) {
    url.searchParams.set("page", page);
  }
  return url.toString();
}

/** The URL of the model picker of `project` (the current URL with `model` removed). */
export function projectUrl(project: string, href?: string): string {
  const url = new URL(currentHref(href));
  url.searchParams.set("project", project);
  url.searchParams.delete("model");
  return withTab(url, null, null);
}

/**
 * The project page of `project` on the tab `tab` (`null` is the default Models tab), with the
 * docs page `page` (link syntax: `project:<id>`, `model:<name>/<id>`) selected.
 */
export function projectTabUrl(project: string, tab: string | null, page: string | null, href?: string): string {
  const url = new URL(currentHref(href));
  url.searchParams.set("project", project);
  url.searchParams.delete("model");
  return withTab(url, tab, page);
}

/** The editor URL of `project`/`model`. */
export function modelUrl(project: string, model: string, href?: string): string {
  const url = new URL(currentHref(href));
  url.searchParams.set("project", project);
  url.searchParams.set("model", model);
  return withTab(url, null, null);
}

/**
 * The editor URL of `project`/`model` on its Docs tab with `page` selected: a page id of the
 * model's docs, `project:<id>` for a project page, or `null` for the model's first page.
 */
export function modelDocsUrl(project: string, model: string, page: string | null, href?: string): string {
  const url = new URL(currentHref(href));
  url.searchParams.set("project", project);
  url.searchParams.set("model", model);
  return withTab(url, "docs", page);
}
