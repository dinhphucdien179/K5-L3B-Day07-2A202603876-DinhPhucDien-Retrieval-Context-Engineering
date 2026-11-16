#!/usr/bin/env bash
# Build and verify Docker without spending API credit. Run from any directory:
# bash scripts/check_bonus_docker.sh  (use sudo on Linux if Docker requires it)
set -euo pipefail

task_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd -- "$task_root"
task_compose=(docker compose -f compose.bonus.yml)
task_output=results/bonus/docker
mkdir -p -- "$task_output"

if [[ ${1:-} != --skip-build ]]; then
    "${task_compose[@]}" build bonus
fi

"${task_compose[@]}" run --rm -T bonus prepare > "$task_output/prepare.json"
"${task_compose[@]}" run --rm -T --entrypoint python bonus -m unittest discover -s tests -v > "$task_output/unit-tests.log" 2>&1

task_image=$("${task_compose[@]}" config --images)
docker image inspect "$task_image" --format '{{json .Id}}' > "$task_output/image-id.json"

"${task_compose[@]}" run --rm -T --entrypoint python bonus - <<'PY'
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys
from bonus.corpus import ROOT, digest, page_image, write
from bonus.benchmark import fingerprint

out = ROOT / 'results/bonus/docker'
log = (out / 'unit-tests.log').read_text()
match = re.search(r'Ran (\d+) tests?', log)
if not match or not log.rstrip().endswith('OK'):
    raise SystemExit('Unit-test log does not confirm success')
# A separate width exercises the container renderer instead of an existing 1600px cache.
image = page_image(135, width=1536)
result = {
    'verified_utc': datetime.now(timezone.utc).isoformat(),
    'status': 'passed',
    'image_id': json.loads((out / 'image-id.json').read_text()),
    'python_version': sys.version,
    'dotenv_version': importlib.metadata.version('python-dotenv'),
    'poppler': subprocess.run(['pdftoppm', '-v'], capture_output=True, text=True, check=True).stderr.splitlines()[0],
    'prepare': json.loads((out / 'prepare.json').read_text()),
    'unit_tests': int(match[1]),
    'render_check': {'page': 135, 'path': str(image.relative_to(ROOT)), 'sha256': digest(image)},
    'api_called': False,
    'bonus_code_sha256': fingerprint(),
}
write(out / 'verification.json', result)
print(json.dumps(result, ensure_ascii=False, indent=2))
PY

printf '%s\n' 'Docker đã build và qua kiểm tra offline. Bằng chứng: results/bonus/docker/verification.json. Chưa chạy benchmark API bằng script này.'
