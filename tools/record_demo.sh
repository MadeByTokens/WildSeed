#!/usr/bin/env bash
# One command: fly the sensor rig through a generated world and write
# runs/<world>_<pattern>_seed<seed>/video.mp4 (+ dataset with --dataset).
#
# Usage: tools/record_demo.sh [pattern] [seed] [world_file] [extra `wildseed record` args...]
#   tools/record_demo.sh orbit 7
#   tools/record_demo.sh flythrough 3 worlds/forest_world.world --dataset
#
# Needs: wildseed:egl image, --gpus all, a world built with `wildseed generate --rig`.
set -euo pipefail
cd "$(dirname "$0")/.."

PATTERN="${1:-orbit}"
SEED="${2:-7}"
WORLD_FILE="${3:-worlds/forest_world.world}"
[ $# -ge 1 ] && shift; [ $# -ge 1 ] && shift; [ $# -ge 1 ] && shift
EXTRA_ARGS="$*"

if [ ! -f "$WORLD_FILE" ]; then
    echo "world file not found: $WORLD_FILE (run: wildseed generate --rig)" >&2
    exit 1
fi
WORLD_NAME=$(sed -n 's/.*<world name=["'\'']\([^"'\'']*\)["'\''].*/\1/p' "$WORLD_FILE" | head -1)
echo "recording: pattern=$PATTERN seed=$SEED world=$WORLD_NAME ($WORLD_FILE)"

docker run --rm --gpus all -e NVIDIA_DRIVER_CAPABILITIES=all \
    -v "$PWD:/workspace" --entrypoint bash wildseed:egl -c "
    cd /workspace
    GZ_SIM_RESOURCE_PATH=/workspace/models gz sim -s -r '$WORLD_FILE' > /tmp/gz.log 2>&1 &
    GZPID=\$!
    sleep 12
    PYTHONPATH=/workspace/src python3 -m wildseed.cli.main record \
        -p '$PATTERN' --seed '$SEED' --world '$WORLD_NAME' $EXTRA_ARGS
    RC=\$?
    kill \$GZPID 2>/dev/null || true
    exit \$RC
"
