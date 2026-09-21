"""Both startup paths must serve committed admin assets without rewriting them."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent

def snapshot():
    return {str(p.relative_to(ROOT)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in (ROOT / 'admin_static').rglob('*') if p.is_file()}

def main():
    before = snapshot()
    for module in ('app', 'app_legacy'):
        with tempfile.TemporaryDirectory(prefix='jj-admin-immutable-') as directory:
            env = os.environ.copy()
            env.pop('DATABASE_URL', None)
            env.update(JJ_DB_PATH=str(Path(directory)/'test.db'), RENDER='1', JJ_ENABLE_DEMO_MEMBER='0')
            subprocess.run([sys.executable, '-c', f'''
import {module} as production
from fastapi.testclient import TestClient
with TestClient(production.app, base_url='https://testserver') as client:
    response=client.get('/admin')
    assert response.status_code==200
    assert 'admin_point_requests.js' in response.text
    assert 'admin_pin_verify.js' in response.text
    assert 'ops_dashboard.js' in response.text
'''], cwd=ROOT, env=env, check=True)
        assert snapshot() == before, f'{module} changed admin files or wrote identical content'
    print('JJ_ADMIN_STARTUP_IMMUTABLE_OK production/legacy/content/mtime')

if __name__ == '__main__':
    main()
