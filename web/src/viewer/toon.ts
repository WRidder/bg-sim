import type { Material } from "@babylonjs/core/Materials/material";
import type { MaterialDefines } from "@babylonjs/core/Materials/materialDefines";
import { MaterialPluginBase } from "@babylonjs/core/Materials/materialPluginBase";
import { ShaderLanguage } from "@babylonjs/core/Materials/shaderLanguage";
import { RegisterClass } from "@babylonjs/core/Misc/typeStore";

/** Share of the banded luminance blended into the lit colour: a hint of cel, not a cartoon. */
export const TOON_AMOUNT = 0.3;

/**
 * A soft three-band luminance ramp applied after lighting, blended with the normal shading
 * and hue-preserving.  One plugin per (shared) material; Standard and PBR both.
 */
export class ToonPlugin extends MaterialPluginBase {
  constructor(material: Material) {
    super(material, "McfToon", 250, { MCF_TOON: false });
    this._enable(true);
  }

  override getClassName(): string {
    return "ToonPlugin";
  }

  override isCompatible(shaderLanguage: ShaderLanguage): boolean {
    return shaderLanguage === ShaderLanguage.GLSL;
  }

  override prepareDefines(defines: MaterialDefines): void {
    defines["MCF_TOON"] = true;
  }

  override getCustomCode(shaderType: string): { [pointName: string]: string } | null {
    if (shaderType !== "fragment") return null;
    const c = this._material.getClassName() === "PBRMaterial" ? "finalColor" : "color";
    return {
      CUSTOM_FRAGMENT_BEFORE_FRAGCOLOR: `
#ifdef MCF_TOON
{
  float l = dot(${c}.rgb, vec3(0.299, 0.587, 0.114));
  float q = 0.16 + 0.26 * smoothstep(0.16, 0.24, l) + 0.38 * smoothstep(0.50, 0.60, l);
  ${c}.rgb *= mix(1.0, q / max(l, 1e-4), ${TOON_AMOUNT.toFixed(2)});
}
#endif
`,
    };
  }
}

// A material clone (the selected item's depth-raised copy) re-creates its plugins by class name.
RegisterClass("BABYLON.ToonPlugin", ToonPlugin);
