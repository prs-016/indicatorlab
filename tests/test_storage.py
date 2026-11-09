"""Local-path behaviour of src.storage (S3 uses the same pyarrow code path)."""
import pandas as pd

from src import storage


def test_parquet_round_trip_creates_parents(tmp_path):
    df = pd.DataFrame({"ticker": ["AAPL", "MSFT"], "value": [3, 5]})
    target = tmp_path / "a" / "b" / "t.parquet"
    storage.write_parquet(df, target)
    assert storage.exists(target)
    pd.testing.assert_frame_equal(storage.read_parquet(target), df)
    assert storage.read_parquet(target, columns=["value"]).columns.tolist() == ["value"]


def test_parquet_dir_reads_all_parts_and_handles_missing(tmp_path):
    assert storage.read_parquet_dir(tmp_path / "nope") is None
    storage.write_parquet(pd.DataFrame({"x": [1]}), tmp_path / "parts" / "part-1.parquet")
    storage.write_parquet(pd.DataFrame({"x": [2]}), tmp_path / "parts" / "part-2.parquet")
    assert sorted(storage.read_parquet_dir(tmp_path / "parts")["x"]) == [1, 2]


def test_json_round_trip_and_default(tmp_path):
    p = tmp_path / "state" / "_state.json"
    assert storage.read_json(p, default={}) == {}
    storage.write_json({"stocks": 1731000000}, p)
    assert storage.read_json(p) == {"stocks": 1731000000}


def test_copy_tree_and_newer_than(tmp_path):
    import os
    import time

    src, dst = tmp_path / "src", tmp_path / "dst"
    storage.write_json({"a": 1}, src / "x" / "a.json")
    storage.write_json({"b": 2}, src / "b.json")
    old = time.time() - 100
    os.utime(src / "b.json", (old, old))
    assert storage.copy_tree(src, dst) == 2 and storage.read_json(dst / "x" / "a.json") == {"a": 1}
    assert storage.copy_tree(src, tmp_path / "dst2", newer_than=old + 1) == 1
    assert storage.copy_tree(tmp_path / "missing", dst) == 0
    assert storage.copy_file(src / "b.json", tmp_path / "one" / "b.json")
    assert not storage.copy_file(src / "nope.json", tmp_path / "one" / "nope.json")
