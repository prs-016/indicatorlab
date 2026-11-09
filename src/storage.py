"""Read and write tables and small JSON state on a local path or S3 with the same calls.

A location is a local path or an ``s3://bucket/key`` URI; ``pyarrow.fs`` resolves both, so code
that runs on a laptop also runs on AWS by changing one environment variable (e.g.
``INDICATORLAB_DATA_URI``). S3 credentials come from the usual AWS environment/profile.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.fs as pafs
import pyarrow.parquet as pq


def _resolve(uri: str | Path) -> tuple[pafs.FileSystem, str]:
    """(filesystem, path) for a local path or s3:// URI; local paths are made absolute."""
    s = str(uri)
    if "://" not in s:
        s = str(Path(s).expanduser().resolve())
    return pafs.FileSystem.from_uri(s)


def exists(uri: str | Path) -> bool:
    """True if a file or directory exists at `uri`."""
    fs, path = _resolve(uri)
    return fs.get_file_info(path).type != pafs.FileType.NotFound


def read_parquet(uri: str | Path, columns: list[str] | None = None) -> pd.DataFrame:
    """One parquet file (or a directory of parts) as a DataFrame."""
    fs, path = _resolve(uri)
    return pq.read_table(path, filesystem=fs, columns=columns).to_pandas()


def read_parquet_dir(uri: str | Path, columns: list[str] | None = None) -> pd.DataFrame | None:
    """All parquet parts under a directory, or None if it does not exist yet."""
    fs, path = _resolve(uri)
    if fs.get_file_info(path).type == pafs.FileType.NotFound:
        return None
    dataset = ds.dataset(path, filesystem=fs, format="parquet")
    if not dataset.files:
        return None
    return dataset.to_table(columns=columns).to_pandas()


def write_parquet(df: pd.DataFrame, uri: str | Path) -> None:
    """Write `df` to one parquet file, creating parent directories on local disk."""
    fs, path = _resolve(uri)
    if isinstance(fs, pafs.LocalFileSystem):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path, filesystem=fs)


def read_json(uri: str | Path, default=None):
    """Parsed JSON at `uri`, or `default` if the file does not exist."""
    fs, path = _resolve(uri)
    if fs.get_file_info(path).type == pafs.FileType.NotFound:
        return default
    with fs.open_input_stream(path) as f:
        return json.loads(f.read().decode("utf-8"))


def write_json(obj, uri: str | Path) -> None:
    """Write `obj` as pretty JSON, creating parent directories on local disk."""
    fs, path = _resolve(uri)
    if isinstance(fs, pafs.LocalFileSystem):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    with fs.open_output_stream(path) as f:
        f.write(json.dumps(obj, indent=2, default=str).encode("utf-8"))


def copy_tree(src: str | Path, dst: str | Path, newer_than: float | None = None) -> int:
    """Copy every file under `src` to the same relative path under `dst` (local <-> S3 in either direction).

    With `newer_than` (epoch seconds), only files modified after it are copied, so a job can push
    back just what it changed. A missing `src` copies nothing. Returns the number of files copied.
    """
    sfs, spath = _resolve(src)
    dfs, dpath = _resolve(dst)
    infos = sfs.get_file_info(pafs.FileSelector(spath, recursive=True, allow_not_found=True))
    n = 0
    for info in infos:
        if info.type != pafs.FileType.File:
            continue
        if newer_than is not None and info.mtime is not None and info.mtime.timestamp() <= newer_than:
            continue
        target = f"{dpath}/{info.path[len(spath):].lstrip('/')}"
        if isinstance(dfs, pafs.LocalFileSystem):
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        pafs.copy_files(info.path, target, source_filesystem=sfs, destination_filesystem=dfs)
        n += 1
    return n


def copy_file(src: str | Path, dst: str | Path) -> bool:
    """Copy one file if it exists; returns whether it did."""
    sfs, spath = _resolve(src)
    if sfs.get_file_info(spath).type != pafs.FileType.File:
        return False
    dfs, dpath = _resolve(dst)
    if isinstance(dfs, pafs.LocalFileSystem):
        Path(dpath).parent.mkdir(parents=True, exist_ok=True)
    pafs.copy_files(spath, dpath, source_filesystem=sfs, destination_filesystem=dfs)
    return True
