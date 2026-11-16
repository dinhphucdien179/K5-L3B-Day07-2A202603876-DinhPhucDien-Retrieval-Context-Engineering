"""Resource budgets and durable artifacts; no numerical imports at module load."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
import math
import os
import platform
from pathlib import Path
import sys
import tempfile
import time


LAB_DIRECTORIES = frozenset({'starter', 'data', 'benchmark', 'results', 'artifacts', 'report', 'docs', '.cache'})


def require_python() -> None:
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Python 3.12 is required. Activate a Python 3.12 virtual environment.')


def lab_path(root: Path, value: str | Path) -> Path:
    """Resolve a lab artifact and reject traversal, unrelated folders and symlinks out."""
    root = root.resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Path must stay inside a configured lab directory')
    parts = path.relative_to(root).parts
    if not parts or parts[0] not in LAB_DIRECTORIES:
        raise ValueError('Path must stay inside a configured lab directory')
    return path


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: Path, value) -> None:
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


@contextmanager
def exclusive_run(path: Path):
    """A local process lock; PostgreSQL also locks its own write transaction."""
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f'Another process holds {path}') from exc
        yield


def _cgroups():
    root = Path('/sys/fs/cgroup')
    try:
        relative = next(line.split('::', 1)[1] for line in Path('/proc/self/cgroup').read_text().splitlines() if '::' in line)
        current = (root / relative.lstrip('/')).resolve()
        if current != root and root not in current.parents:
            return
        while True:
            yield current
            if current == root:
                break
            current = current.parent
    except (OSError, StopIteration):
        return


def effective_cpus() -> int:
    count = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count() or 1
    for directory in _cgroups():
        try:
            quota, period = (directory / 'cpu.max').read_text().split()
            if quota != 'max':
                count = min(count, max(1, int(quota) // int(period)))
        except (OSError, ValueError):
            pass
    return max(1, count)


def memory_status() -> dict:
    values = {}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, rest = line.split(':', 1)
            if key in {'MemTotal', 'MemAvailable'}:
                values[key] = int(rest.split()[0]) * 1024
        total, available = values['MemTotal'], values['MemAvailable']
        available_ratio = available / total
        for directory in _cgroups():
            try:
                maximum = (directory / 'memory.max').read_text().strip()
                if maximum != 'max':
                    limit = int(maximum)
                    current = int((directory / 'memory.current').read_text())
                    available_ratio = min(available_ratio, max(0, limit-current) / limit)
                    total, available = min(total, limit), min(available, max(0, limit - current))
            except (OSError, ValueError):
                pass
        rss = int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
        import resource
        return {'total_bytes': total, 'available_bytes': available, 'rss_bytes': rss,
                'available_ratio': available_ratio,
                'process_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}
    except (OSError, ValueError, KeyError):
        # Unavailable is distinct from zero usage.
        return {'total_bytes': None, 'available_bytes': None, 'rss_bytes': None}


@dataclass(frozen=True)
class RuntimeConfig:
    native_threads: int = 4
    fetch_workers: int = 2
    max_inflight: int = 4
    requests_per_second: float = 1.0
    batch_size: int = 16
    rss_limit_mb: int = 2048
    min_available_ratio: float = 0.10
    max_response_bytes: int = 2 * 1024 * 1024

    def __post_init__(self):
        for key in ('native_threads', 'fetch_workers', 'max_inflight', 'batch_size', 'rss_limit_mb', 'max_response_bytes'):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError(f'{key} must be a positive integer')
        if self.max_inflight < self.fetch_workers:
            raise ValueError('max_inflight must cover fetch_workers')
        if not math.isfinite(self.requests_per_second) or self.requests_per_second <= 0 or not 0 <= self.min_available_ratio < 1:
            raise ValueError('Invalid rate or available-memory ratio')

    def apply_threads(self) -> dict:
        require_python()
        if any(name in sys.modules for name in ('numpy', 'torch', 'sentence_transformers')):
            raise RuntimeError('Set thread budgets before importing numerical libraries; use a fresh CLI process')
        threads = min(self.native_threads, effective_cpus())
        names = ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS')
        previous = {name: os.environ.get(name) for name in names}
        for name in names:
            os.environ[name] = str(threads)
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        cpu_model = None
        try:
            cpu_model = next(line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                             if line.startswith('model name'))
        except (OSError, StopIteration):
            pass
        return {'effective_cpus': effective_cpus(), 'native_threads': threads,
                'cpu_model': cpu_model, 'architecture': platform.machine(),
                'previous_thread_environment': previous, 'budget': asdict(self),
                'python': platform.python_version(),
                'environment_type': ('venv' if sys.prefix != sys.base_prefix else
                                     'conda' if os.getenv('CONDA_PREFIX') else 'system'),
                'memory': memory_status()}

    def guard(self, stage: str) -> dict:
        state = memory_status()
        rss, total, available = (state[k] for k in ('rss_bytes', 'total_bytes', 'available_bytes'))
        if rss is None:
            raise RuntimeError('Cannot enforce memory budget: /proc memory telemetry unavailable')
        if rss > self.rss_limit_mb * 1024 * 1024 or (total and state.get('available_ratio', available / total) < self.min_available_ratio):
            raise MemoryError(f'{stage}: memory budget exceeded: {state}; limit_mb={self.rss_limit_mb}')
        return state


class Telemetry:
    """Boundary observations, not a continuous peak-memory sampler."""
    def __init__(self, path: Path, config: RuntimeConfig):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open('a', encoding='utf-8')
        self.config = config

    @contextmanager
    def stage(self, name: str, **fields):
        start = time.perf_counter()
        status = 'ok'
        try:
            self.config.guard(name + ':before')
            yield
            self.config.guard(name + ':after')
        except BaseException:
            status = 'failed'
            raise
        finally:
            record = dict(stage=name, status=status, elapsed_seconds=time.perf_counter()-start,
                          memory=memory_status(), **fields)
            self.stream.write(json.dumps(record) + '\n')
            self.stream.flush()

    def close(self):
        self.stream.close()
