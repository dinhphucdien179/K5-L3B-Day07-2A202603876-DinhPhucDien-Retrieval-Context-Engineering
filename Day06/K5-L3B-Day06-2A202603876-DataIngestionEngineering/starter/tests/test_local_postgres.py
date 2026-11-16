"""Isolated manager checks; all paths and credentials below are test fixtures."""
import json
import subprocess
import sys

import pytest

from scripts import local_postgres


def test_pipeline_forwards_private_environment_and_exit_status(tmp_path, monkeypatch, capsys):
    root = tmp_path / 'lab'
    (root / 'starter').mkdir(parents=True)
    runtime = tmp_path / 'runtime'
    (runtime / 'bin').mkdir(parents=True)
    (runtime / 'bin/pg_ctl').touch()
    state = tmp_path / 'private-state'
    state.mkdir(mode=0o700)
    urls = {'DATABASE_URL': 'postgresql://fixture:private@localhost/lab',
            'DAY6_TEST_DATABASE_URL': 'postgresql://fixture:private@localhost/test'}
    (state / 'urls.json').write_text(json.dumps(urls))
    monkeypatch.setattr(local_postgres, 'ROOT', root)
    monkeypatch.setattr(local_postgres, 'RUNTIME', runtime)
    monkeypatch.setattr(local_postgres, 'STATE', state)
    monkeypatch.delenv('CONDA_DEFAULT_ENV', raising=False)
    monkeypatch.delenv('CONDA_PREFIX', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://wrong-fixture/ignored')
    monkeypatch.setenv('DAY6_FORWARDING_TEST', 'inherited')
    forwarded = ['evaluate', '--split', 'dev', '--config', 'a path/config.json']
    monkeypatch.setattr(sys, 'argv', ['local_postgres', 'pipeline', *forwarded])
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(local_postgres.subprocess, 'run', run)
    with pytest.raises(SystemExit) as exc:
        local_postgres.main()
    assert exc.value.code == 7
    assert len(calls) == 1
    command, options = calls[0]
    assert command == [sys.executable, '-m', 'src.run', *forwarded]
    assert options['cwd'] == root / 'starter'
    assert {key: options['env'][key] for key in urls} == urls
    assert options['env']['DAY6_FORWARDING_TEST'] == 'inherited'
    assert 'shell' not in options
    output = capsys.readouterr()
    assert not output.out and not output.err


@pytest.mark.parametrize(('arguments', 'message'), [
    (['pipeline'], 'pipeline requires src.run arguments'),
    (['start', 'ingest'], 'Only pipeline accepts additional arguments'),
])
def test_invalid_forwarding_is_rejected_before_state_changes(tmp_path, monkeypatch, capsys, arguments, message):
    state = tmp_path / 'must-not-be-created'
    monkeypatch.setattr(local_postgres, 'STATE', state)
    monkeypatch.setattr(local_postgres, 'RUNTIME', tmp_path / 'absent-runtime')
    monkeypatch.setenv('CONDA_DEFAULT_ENV', 'data-ingestion')
    monkeypatch.setattr(sys, 'argv', ['local_postgres', *arguments])
    with pytest.raises(SystemExit) as exc:
        local_postgres.main()
    assert exc.value.code == 2
    assert message in capsys.readouterr().err
    assert not state.exists()
