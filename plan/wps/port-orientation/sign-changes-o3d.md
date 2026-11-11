# Sign changes of WP-O3d (O18, O22)

Every bonded port that declared no orientation already had the bond direction its law assumes, so declaring it
changed no bond and no value. No example model, generator, `expected.json`, golden file, plot, binding or dashboard
changed.

| place | change | signals that change sign |
| --- | --- | --- |
| `contracts/fixtures/model/valid/model.planar.multibond.json`, `model.frame-bridge.json` (inline `FixedTransform2D`) | law: `a.f = -Ad(g) b.f` (was `a.f = Ad(g) b.f`), the into-block form | `Mount/a.f` (`Mount/Transform/a.f` in `frame-bridge`); its value is zero in both fixtures (the `a` side is on a ground), so no recorded number changes |

Deviation: none. No state, position, twist or sensed output changes sign.
