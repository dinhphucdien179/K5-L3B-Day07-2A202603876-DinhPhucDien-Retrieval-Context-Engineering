"""Manage only this repo's private PostgreSQL cluster; no system service changes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import quote

from src.runtime import atomic_json, exclusive_run, require_python

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.cache/day6/postgres-runtime'
PROJECT_ID = hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
STATE = Path.home() / '.local/share/day6-lab' / PROJECT_ID / 'postgres'
DATA = STATE / 'data'
CONFIG = STATE / 'connection.json'
PORT = 55433


def command(name, *args, check=True):
    return subprocess.run([str(RUNTIME / 'bin' / name), *map(str, args)], check=check)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'status', 'stop', 'check', 'test', 'smoke', 'pipeline'))
    parser.add_argument('pipeline_args', nargs=argparse.REMAINDER,
                        help='Arguments passed to src.run, only with the pipeline action')
    args = parser.parse_args()
    if args.action == 'pipeline' and not args.pipeline_args:
        parser.error('pipeline requires src.run arguments, for example: pipeline ingest')
    if args.action != 'pipeline' and args.pipeline_args:
        parser.error('Only pipeline accepts additional arguments')
    require_python()
    if not (RUNTIME / 'bin/pg_ctl').is_file():
        parser.error('Install PostgreSQL + pgvector into .cache/day6/postgres-runtime; see starter/README.md')
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    if STATE.stat().st_uid != os.geteuid() or STATE.stat().st_mode & 0o077:
        parser.error('PostgreSQL state requires an owned Linux directory with mode 0700')
    with exclusive_run(STATE / 'manager.lock'):
        if args.action in {'check', 'test', 'smoke', 'pipeline'}:
            urls = json.loads((STATE / 'urls.json').read_text())
            commands = {
                'check': [str(ROOT / 'starter/scripts/check_setup.py')],
                'test': ['-m', 'pytest', '-q', '--junitxml=results/engineering-tests.xml'],
                'smoke': ['-m', 'scripts.smoke_embedding', '--database', '--offline'],
                'pipeline': ['-m', 'src.run', *args.pipeline_args],
            }
            cwd = ROOT if args.action == 'test' else ROOT / 'starter'
            result = subprocess.run([sys.executable, *commands[args.action]], cwd=cwd, env={**os.environ, **urls})
            raise SystemExit(result.returncode)
        if args.action != 'start':
            if not CONFIG.exists() or not DATA.exists():
                parser.error('This project has no initialized local cluster')
            if args.action == 'stop':
                command('pg_ctl', '-D', DATA, '-m', 'fast', '-w', '-t', '30', 'stop')
            else:
                raise SystemExit(command('pg_ctl', '-D', DATA, 'status', check=False).returncode)
            return
        if not CONFIG.exists():
            if DATA.exists():
                parser.error('Data directory exists without project credentials; refusing to reinitialize it')
            password = secrets.token_urlsafe(32)
            atomic_json(CONFIG, {'host': '127.0.0.1', 'port': PORT, 'user': 'day6', 'password': password})
        settings = json.loads(CONFIG.read_text())
        if not (DATA / 'PG_VERSION').exists():
            if DATA.exists():
                parser.error('Incomplete data directory: inspect it before retrying initdb')
            password_file = STATE / '.init-password'
            try:
                # O_EXCL and mode 0600 avoid publishing a readable password file.
                with os.fdopen(os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
                    stream.write(settings['password'] + '\n')
                command('initdb', '-D', DATA, '--username=day6', '--auth-local=trust',
                        '--auth-host=scram-sha-256', '--encoding=UTF8', '--locale=C', '--pwfile', password_file)
            finally:
                password_file.unlink(missing_ok=True)
        if command('pg_ctl', '-D', DATA, 'status', check=False).returncode != 0:
            command('pg_ctl', '-D', DATA, '-l', STATE / 'server.log', '-w', '-t', '30', '-o',
                    f"-h 127.0.0.1 -p {PORT} -c unix_socket_directories='' -c max_connections=10 -c shared_buffers=128MB", 'start')
        import psycopg
        from psycopg import sql
        with psycopg.connect(**settings, dbname='postgres', autocommit=True, connect_timeout=5) as connection:
            actual = connection.execute('SHOW data_directory').fetchone()[0]
            if Path(actual).resolve() != DATA.resolve():
                raise RuntimeError('Port belongs to a different cluster; refusing to modify it')
            for name in ('day6_lab', 'day6_test'):
                if not connection.execute('SELECT 1 FROM pg_database WHERE datname=%s', [name]).fetchone():
                    connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        for name in ('day6_lab', 'day6_test'):
            with psycopg.connect(**settings, dbname=name, autocommit=True, connect_timeout=5) as connection:
                connection.execute('CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public')
        # Private DSNs support shell-free subprocesses without copying passwords into logs.
        base = f"postgresql://day6:{quote(settings['password'], safe='')}@127.0.0.1:{PORT}/"
        atomic_json(STATE / 'urls.json', {'DATABASE_URL': base + 'day6_lab',
                                         'DAY6_TEST_DATABASE_URL': base + 'day6_test'})
        print('Local PostgreSQL ready on 127.0.0.1:55433; credentials are stored in the user data directory.')


if __name__ == '__main__':
    main()
