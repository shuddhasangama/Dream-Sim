"""Run tests against a disposable loopback-only PostgreSQL 18 cluster on Windows.

No Railway credentials are read or used. Requires locally installed PostgreSQL.
All cluster files and generated credentials are removed after a clean shutdown.
"""
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile


def main():
    binaries = Path(r'C:\Program Files\PostgreSQL\18\bin')
    if not (binaries / 'initdb.exe').is_file():
        raise SystemExit('Install local PostgreSQL 18 before using this helper.')
    temp_root = Path(tempfile.gettempdir()).resolve()
    folder = Path(tempfile.mkdtemp(prefix='dhashu-phase4-pg-', dir=temp_root)).resolve()
    # Verify the absolute deletion target BEFORE any recursive cleanup.
    if folder.parent != temp_root or not folder.name.startswith('dhashu-phase4-pg-'):
        raise RuntimeError('Unexpected temporary directory; refusing cleanup.')
    cluster = folder / 'cluster'
    password = secrets.token_hex(32)
    pwfile = folder / 'password'
    pwfile.write_text(password, encoding='ascii')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    def run(args):
        # Detached server must not inherit the caller's captured stdout pipe.
        with (folder / 'control.log').open('ab') as output:
            subprocess.run(args, check=True, stdout=output, stderr=output, timeout=60)
    try:
        run([str(binaries/'initdb.exe'), '-D', str(cluster), '-U', 'postgres',
             '-A', 'scram-sha-256', '--pwfile='+str(pwfile), '--locale=C', '-E', 'UTF8'])
        run([str(binaries/'pg_ctl.exe'), '-D', str(cluster), '-l', str(folder/'server.log'),
             '-o', f'-h 127.0.0.1 -p {port}', '-w', 'start'])
        dsn = folder / 'dsn'
        dsn.write_text(f'host=127.0.0.1 port={port} user=postgres password={password} dbname=postgres',encoding='ascii')
        env = dict(os.environ)
        env.pop('DATABASE_URL', None)
        env['AUTH_TEST_POSTGRES_DSN_FILE'] = str(dsn)
        print('Isolated PostgreSQL started; running tests (credentials withheld).',flush=True)
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', *(sys.argv[1:] or ['--ignore=smoke_test.py'])],
                                env=env, cwd=Path(__file__).resolve().parent)
        return result.returncode
    finally:
        if (cluster/'postmaster.pid').exists():
            run([str(binaries/'pg_ctl.exe'), '-D', str(cluster), '-m', 'fast', '-w', 'stop'])
        if (cluster/'postmaster.pid').exists():
            raise RuntimeError('Cluster still running; retained temporary files for shutdown.')
        shutil.rmtree(folder)
        print('Isolated PostgreSQL stopped; temporary data and credentials removed.',flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
