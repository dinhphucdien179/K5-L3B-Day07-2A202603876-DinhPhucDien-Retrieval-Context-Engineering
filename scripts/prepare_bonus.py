"""Run from the repository root with the active Python 3.12 environment."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from bonus.corpus import prepare

if __name__ == '__main__':
    m = prepare(reextract='--reextract' in sys.argv,amend_catalog='--amend-catalog-before-runs' in sys.argv)
    print({k: m[k] for k in ('indexed_pages','figure_records','table_records','corpus_sha256')})
