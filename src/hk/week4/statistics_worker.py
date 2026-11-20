"""Call Vibe's DSR from its own namespace without importing research src."""

import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import kurtosis, skew

sys.path.insert(0, str(Path(sys.argv[2]) / "agent"))
from src.quantlib.multipletesting import deflated_sharpe_ratio

p = json.loads(Path(sys.argv[1]).read_text())
r = np.asarray(p["returns"], dtype=float)
t = np.asarray(p["trial_sharpes"], dtype=float)
v = deflated_sharpe_ratio(
    float(r.mean() / r.std(ddof=1)),
    int(p["total_trials"]),
    len(r),
    float(t.std(ddof=1)),
    skew=float(skew(r, bias=False)),
    kurtosis=float(kurtosis(r, fisher=False, bias=False)),
)
print(json.dumps({"deflated_sharpe_ratio": v.deflated_sharpe_ratio}))
