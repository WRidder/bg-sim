/**
 * The rendered Markdown of a docs page (W5.6): GFM (tables, task lists, footnotes), `$math$`
 * and `$$display$$` math through KaTeX, no raw HTML (react-markdown drops it, rehype-sanitize
 * guards the rest), model-aware links and copyable inline images.
 */

import { createContext, useContext, useMemo, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

import { API_BASE } from "../api/client";
import { normalizeDisplayMath } from "./displayMath";
import { copyImageToClipboard } from "./imageClipboard";
import { assetUrl, imageMarkdown, parseImageAlt } from "./docsImages";
import { describeLink, resolveLink, type LinkContext, type LinkTarget } from "./docsLinks";

export interface LinkActions {
  openPage: (id: string) => void;
  showBlock: (target: Extract<LinkTarget, { kind: "block" }>) => void;
  plotSignal: (id: string) => void;
  /** A short status message ("Image copied", or why a copy failed). */
  notify: (message: string) => void;
}

export interface MarkdownViewProps {
  text: string;
  project: string;
  model: string;
  links: LinkContext;
  actions: LinkActions;
}

const MATH_CLASSES = ["math-inline", "math-display"];

/** The default sanitize schema plus the model-aware link protocols and the math markers. */
const sanitizeSchema = {
  ...defaultSchema,
  protocols: {
    ...defaultSchema.protocols,
    href: [...(defaultSchema.protocols?.href ?? []), "page", "block", "signal"],
  },
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code ?? []), ["className", ...MATH_CLASSES]],
    span: [...(defaultSchema.attributes?.span ?? []), ["className", ...MATH_CLASSES]],
    div: [...(defaultSchema.attributes?.div ?? []), ["className", ...MATH_CLASSES]],
  },
};

const REMARK_PLUGINS = [remarkGfm, remarkMath];
// Sanitize first (it would strip KaTeX's markup), then typeset the math.
const REHYPE_PLUGINS = [[rehypeSanitize, sanitizeSchema], rehypeKatex] as never;

/** Keep the model-aware protocols; everything else goes through the default allow-list. */
function urlTransform(url: string): string {
  return /^(?:page|block|signal):/i.test(url) ? url : defaultUrlTransform(url);
}

interface ViewContext {
  project: string;
  model: string;
  links: LinkContext;
  actions: LinkActions;
}

const ViewCtx = createContext<ViewContext | null>(null);

function useView(): ViewContext {
  const value = useContext(ViewCtx);
  if (value === null) {
    throw new Error("MarkdownView components render inside MarkdownView");
  }
  return value;
}

function Link({ href, children }: { href: string | undefined; children?: ReactNode }) {
  const { links: context, actions } = useView();
  const target = resolveLink(href, context);
  if (target.kind === "broken") {
    return (
      <span className="docs-link docs-link--broken" title={target.reason} data-testid="docs-broken-link" tabIndex={0}>
        {children}
        <span className="visually-hidden"> (broken link: {target.reason})</span>
      </span>
    );
  }
  if (target.kind === "external" || target.kind === "anchor") {
    return (
      <a
        className="docs-link"
        href={target.href}
        {...(target.kind === "external" ? { target: "_blank", rel: "noopener noreferrer" } : {})}
        title={describeLink(target) || undefined}
      >
        {children}
      </a>
    );
  }
  const run = (event: MouseEvent | KeyboardEvent): void => {
    event.preventDefault();
    if (target.kind === "page") {
      actions.openPage(target.id);
    } else if (target.kind === "block") {
      actions.showBlock(target);
    } else {
      actions.plotSignal(target.id);
    }
  };
  return (
    <a
      className={`docs-link docs-link--${target.kind}`}
      href={href}
      data-link-kind={target.kind}
      title={describeLink(target)}
      onClick={run}
    >
      {children}
    </a>
  );
}

function Image({ src, alt }: { src: string | undefined; alt: string | undefined }) {
  const { project, model, actions } = useView();
  const [failed, setFailed] = useState(false);
  const { alt: text, width } = parseImageAlt(alt ?? "");
  const asset = /^assets\/([0-9a-f]{12}\.(?:png|jpg|gif|webp|svg))$/.exec(src ?? "");
  const external = /^https?:\/\//i.test(src ?? "");

  if (src === undefined || (asset === null && !external)) {
    return (
      <span className="docs-image docs-image--broken" data-testid="docs-broken-image">
        Image not available: "{src ?? ""}" is not an assets/ image or an https URL. Paste the image again to add it.
      </span>
    );
  }
  const url = asset?.[1] !== undefined ? assetUrl(project, model, asset[1], API_BASE) : src;
  if (failed) {
    return (
      <span className="docs-image docs-image--broken" data-testid="docs-broken-image">
        Image not found: {src}. {external ? "Check the address or your connection." : "The file is missing from this model's docs; paste the image again."}
      </span>
    );
  }
  const copy = (): void => {
    const markdown = asset?.[1] !== undefined ? imageMarkdown(asset[1], text) : `![${text}](${src})`;
    void copyImageToClipboard(url, markdown, { project, model }).then(
      () => actions.notify("Image copied to the clipboard."),
      (error: unknown) =>
        actions.notify(error instanceof Error ? error.message : "The image could not be copied."),
    );
  };
  const onKeyDown = (event: KeyboardEvent<HTMLSpanElement>): void => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c") {
      event.preventDefault();
      copy();
    }
  };
  return (
    <span
      className={`docs-image${external ? " docs-image--external" : ""}`}
      role="group"
      aria-label={text === "" ? "Image" : `Image: ${text}`}
      tabIndex={0}
      onKeyDown={onKeyDown}
      data-testid="docs-image"
    >
      <img
        src={url}
        alt={text}
        loading="lazy"
        style={width === null ? undefined : { width: `${width}px`, maxWidth: "100%" }}
        onError={() => setFailed(true)}
      />
      {external ? (
        <span className="docs-image__badge" data-testid="docs-image-external">
          external image
        </span>
      ) : null}
      <button type="button" className="docs-image__copy" aria-label="Copy image" onClick={copy}>
        Copy image
      </button>
    </span>
  );
}

// Defined once: new component types on every render would remount the images.
const COMPONENTS: Components = {
  a: ({ href, children }) => <Link href={href}>{children}</Link>,
  img: ({ src, alt }) => <Image key={typeof src === "string" ? src : ""} src={typeof src === "string" ? src : undefined} alt={alt} />,
};

export function MarkdownView({ text, project, model, links, actions }: MarkdownViewProps) {
  const value = useMemo(() => ({ project, model, links, actions }), [project, model, links, actions]);
  const source = useMemo(() => normalizeDisplayMath(text), [text]);
  return (
    <ViewCtx.Provider value={value}>
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
        urlTransform={urlTransform}
        components={COMPONENTS}
      >
        {source}
      </ReactMarkdown>
    </ViewCtx.Provider>
  );
}
