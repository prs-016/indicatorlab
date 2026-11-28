#!/usr/bin/env bash
# Stage only the pinned Yahoo loader and its dependencies in an isolated build context.
set -euo pipefail

vibe_checkout=${1:?usage: stage_vibe_loader.sh VIBE_CHECKOUT BUILD_CONTEXT}
build_context=${2:?usage: stage_vibe_loader.sh VIBE_CHECKOUT BUILD_CONTEXT}
revision=7f6908b7e1b95d971f4151bfaf2382e2ce9485cf
loader_path=backtest/loaders

mkdir -p "$build_context/vibe/$loader_path"
for module in base.py _http.py yahoo_client.py; do
    git -C "$vibe_checkout" show "$revision:agent/$loader_path/$module" \
        > "$build_context/vibe/$loader_path/$module"
done
git -C "$vibe_checkout" show "$revision:LICENSE" > "$build_context/vibe/VIBE-LICENSE"
