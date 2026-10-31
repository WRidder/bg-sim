/**
 * "Copy to project library" (plan 7.4): fork a library block into
 * `library/<Name>.jl`, then re-point the instance when the refreshed catalog
 * exposes the project block.
 *
 * The write, the catalog re-read and the fake-worker case (the fixed fixture
 * catalog never publishes the fork, so the caller reports that instead of
 * re-pointing) are shared with "Save to project library" of an inline block;
 * see library/projectBlocks.ts.
 */

import type { CatalogBlock } from "../contracts/catalog";
import {
  freeBlockName,
  loadProjectLibraryInfo,
  publishProjectBlock,
  renameBlockDeclaration,
  type PublishOutcome,
} from "../library/projectBlocks";

export type CopyOutcome = PublishOutcome;

/** Rewrite the `@block <oldName>` declaration to the new project block name. */
export function forkedSource(block: CatalogBlock, name: string): string {
  return renameBlockDeclaration(block.source, name, block.name);
}

/**
 * Fork `block` into the project library. The returned `ref` is non-null only
 * when the refreshed catalog already contains `project:<name>`.
 */
export async function copyBlockToProjectLibrary(
  project: string,
  block: CatalogBlock,
): Promise<CopyOutcome> {
  const info = await loadProjectLibraryInfo(project);
  const name = freeBlockName(`${block.name}Copy`, info.libraryNames);
  const source = forkedSource(block, name);
  return publishProjectBlock(project, name, source, {
    libraryDir: info.libraryDir,
    failure: "The block could not be copied",
  });
}
