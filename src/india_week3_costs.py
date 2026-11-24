"""Persistent isolated binding to original Vibe India fee/slippage methods."""

import hashlib
import json
import select
import subprocess
import sys
from pathlib import Path

_WORKER = """
import contextlib,json,sys
sys.path.insert(0,sys.argv[1])
with contextlib.redirect_stdout(sys.stderr):
    from backtest.engines.india_equity import IndiaEquityEngine
    engine=IndiaEquityEngine(json.loads(sys.argv[2]))
print(json.dumps({'ready':True}),flush=True)
for line in sys.stdin:
    req=json.loads(line)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result=getattr(engine,req['method'])(*req['args'],**req['kwargs'])
        print(json.dumps({'value':result},allow_nan=False),flush=True)
    except Exception:
        print(json.dumps({'error':'Original India engine call failed'}),flush=True)
"""


class OriginalIndiaCosts:
    """Context-managed proxy; config must explicitly accept original engine defaults.

    Args: vibe_root points to original checkout; config contains reviewed engine
    settings only. Empty config means explicitly using the original defaults.
    Source hashes/config are recorded in provenance. No network/data methods
    are exposed, and fees are never reimplemented in IndicatorLab.
    """

    def __init__(
        self, vibe_root: Path, config: dict, *, python_executable: str = sys.executable
    ):
        allowed = {
            "in_brokerage",
            "in_stt",
            "in_exchange_txn",
            "in_sebi_fee",
            "in_stamp_duty",
            "in_gst",
            "in_dp_charge",
            "slippage",
            "price_limit",
        }
        if not set(config) <= allowed:
            raise ValueError("Only explicit fee/slippage/price-limit settings accepted")
        agent = Path(vibe_root).resolve() / "agent"
        self.paths = [
            agent / "backtest/engines" / name
            for name in ["india_equity.py", "base.py", "china_a.py"]
        ]
        self.provenance = {
            "source_sha256": {
                str(p.relative_to(agent)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.paths
            },
            "config": dict(config),
            "python": str(python_executable),
        }
        self.child = subprocess.Popen(
            [
                str(python_executable),
                "-I",
                "-B",
                "-u",
                "-c",
                _WORKER,
                str(agent),
                json.dumps(config, allow_nan=False),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        try:
            if self._read() != {"ready": True}:
                raise RuntimeError("Original India engine initialization failed")
            self._verify_sources()
        except Exception:
            self.close()
            raise

    def _read(self):
        if not select.select([self.child.stdout], [], [], 60)[0]:
            self.close()
            raise RuntimeError("Original India engine timeout")
        line = self.child.stdout.readline()
        if not line:
            raise RuntimeError("Original India engine exited")
        return json.loads(line)

    def _verify_sources(self):
        for p in self.paths:
            if (
                hashlib.sha256(p.read_bytes()).hexdigest()
                != self.provenance["source_sha256"][str(p.relative_to(p.parents[2]))]
            ):
                raise RuntimeError("Original engine source changed")

    def _call(self, method, *args, **kwargs):
        self.child.stdin.write(
            json.dumps(
                {"method": method, "args": args, "kwargs": kwargs}, allow_nan=False
            )
            + "\n"
        )
        self.child.stdin.flush()
        result = self._read()
        if "error" in result:
            raise RuntimeError(result["error"])
        return float(result["value"])

    def apply_slippage(self, price: float, direction: int) -> float:
        """Return original adverse fill price for close and cash-side direction."""
        return self._call("apply_slippage", float(price), int(direction))

    def calc_commission(
        self, size: float, price: float, direction: int, is_open: bool
    ) -> float:
        """Return original cash commission for a long entry/exit, without duplication."""
        return self._call(
            "calc_commission",
            float(size),
            float(price),
            int(direction),
            is_open=bool(is_open),
        )

    def close(self) -> None:
        """Terminate the isolated local engine; no files or remote resources changed."""
        if self.child.poll() is None:
            self.child.terminate()
        try:
            self.child.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.child.kill()
            self.child.communicate()
        self._verify_sources()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
