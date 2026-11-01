"""RL on bg-sim FMUs (plan/RL_PLAN.md): the batched C environment, the rsl_rl VecEnv, the policy
block generator. Step 0 is the double cart pendulum (`examples/pendulum-double-cart`)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RL = ROOT / "rl"
RUNTIME = ROOT / "julia" / "BGSim" / "export" / "runtime"
EXAMPLE = ROOT / "examples" / "pendulum-double-cart"
