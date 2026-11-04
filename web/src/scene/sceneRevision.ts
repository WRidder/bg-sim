/** Counts rewrites of scene files, so that the 3D View reads a file again that kept its name. */

import { create } from "zustand";

interface SceneRevision {
  revision: number;
  bump: () => void;
}

export const useSceneRevision = create<SceneRevision>()((set) => ({
  revision: 0,
  bump: () => set((state) => ({ revision: state.revision + 1 })),
}));
