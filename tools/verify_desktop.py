"""Exercise the bundled runtime without opening Excel or controlling any app."""
from pathlib import Path
import json
import subprocess

root = Path(__file__).resolve().parent.parent
exe = root/'dist'/'Royalty Entry'/'Royalty Entry.exe'
report = root/'build'/'desktop-self-test.json'
result = subprocess.run([str(exe), '--self-test', str(report)], timeout=60, check=False)
if not report.exists():
    raise SystemExit(f'No self-test report was produced; exit code {result.returncode}')
checks = json.loads(report.read_text(encoding='utf-8'))
print(json.dumps(checks, indent=2))
raise SystemExit(0 if result.returncode == 0 and checks.get('ok') else 1)
