# Microduck policies

Six files of the official microduck policy set, unchanged, with the set's own `manifest.json`.

- Source: https://huggingface.co/pollen-robotics/microduck-policies
- Revision: `283771bcb3690a0a94a288c108365d9b630d21e4` (the Hub's `main` on 2026-11-12, last modified 2026-11-06)
- Licence: Apache-2.0, as the Hub repository declares (`license: apache-2.0` in its card). The robot's code, from which the app's policy loop is re-implemented, is https://github.com/pollen-robotics/microduck, also Apache-2.0.

| File | Slot in the app | SHA-256 |
|---|---|---|
| `velstand.onnx` | walk (stands still at zero command) | `ce894d30b3343036d499bfac1102bdaa58d59a21c1b58401ecb70fb6a2f63e0a` |
| `alpha_sitstand.onnx` | sitstand | `a6f102d9fd655782ba85bfffe18175c34621da719cffcdd673be7982a06fc254` |
| `alpha_ground_pick.onnx` | ground_pick | `ffbf5109982ff999b0ba53afe86b9ae731bbec679d67fb7f8ab4c52152c88872` |
| `roulade.onnx` | roulade | `3d60da08fc13f29c1b57f41977aa898132c0d60042100149d8e775affcbca32b` |
| `ball_kick_left.onnx` | kick_left | `d6928284dccd3dd61e08bf2f760effa74309fbefd97b2b31afb2a60f526d196a` |
| `ball_kick_right.onnx` | kick_right | `147a32c388c6b19111b3ac3b550a9a6dc8b8bf267118af4d8c3712522eedb5af` |

The hashes match the Hub's LFS ids at that revision. Every file is `obs [1, 61]` → `actions [1, 14]`, feed-forward. Not copied: `alpha_walking.onnx` and `alpha_stand.onnx` (the pre-v5 walk and stand pair), `roller.onnx` and `roller_crouch.onnx` (the wheeled mode).

To fetch them again, or another revision:

```
REV=283771bcb3690a0a94a288c108365d9b630d21e4
for f in manifest.json velstand.onnx alpha_sitstand.onnx alpha_ground_pick.onnx roulade.onnx ball_kick_left.onnx ball_kick_right.onnx; do
  curl -sSL -o "$f" "https://huggingface.co/pollen-robotics/microduck-policies/resolve/$REV/$f"
done
```

A policy with a different observation layout will not work: the app builds the 61-wide observation of `duck-control/src/obs.rs` and nothing else.
