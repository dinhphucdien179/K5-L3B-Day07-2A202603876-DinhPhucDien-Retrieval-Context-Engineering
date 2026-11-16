"""Run retrieval against the restored Day06 database."""
import argparse
import json
import os
from pathlib import Path
import time

from .day06 import Day06Store, ROOT
from .retrieval import BM25, Hybrid


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'search', 'ask', 'llm-check', 'bench', 'review', 'freeze-selection'])
    parser.add_argument('--method', choices=['dense', 'bm25', 'hybrid'], default='dense')
    parser.add_argument('--query')
    parser.add_argument('--top-k', type=int, default=3)
    parser.add_argument('--index', choices=['A', 'B'], default='A')
    parser.add_argument('--filter', type=json.loads, default={})
    parser.add_argument('--output', type=Path)
    parser.add_argument('--budget', type=int, default=6000)
    parser.add_argument('--max-searches', type=int, default=3)
    parser.add_argument('--neighbors', type=int, choices=range(4), default=0)
    parser.add_argument('--split', choices=['dev', 'test'], default='dev')
    parser.add_argument('--suite', choices=['retrieval', 'agent'], default='retrieval')
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--dev-run', type=Path)
    parser.add_argument('--trial')
    parser.add_argument('--reason')
    parser.add_argument('--workers', type=int, choices=range(1, 4), default=1)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.command in ('search', 'ask') and not args.query:
        parser.error('search/ask requires --query')
    if args.command == 'review':
        if not args.dev_run:
            parser.error('review requires --dev-run pointing to a trial directory with reviews.json')
        from .review import aggregate_reviews
        print(json.dumps(aggregate_reviews(args.dev_run), ensure_ascii=False, indent=2))
        return
    if args.command == 'freeze-selection':
        if not all([args.dev_run, args.trial, args.reason, args.output]):
            parser.error('freeze-selection requires --dev-run, --trial, --reason and --output')
        from .review import freeze_selection
        print(json.dumps(freeze_selection(args.dev_run, args.trial, args.reason, args.output), ensure_ascii=False, indent=2))
        return
    if args.command == 'llm-check':
        from .llm import OpenRouter
        client = OpenRouter()
        tool = {'type': 'function', 'function': {'name': 'connection_check',
                'description': 'Confirm that tool calling is working.',
                'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}}
        response = client.complete([{'role': 'user', 'content': 'Call connection_check with empty arguments.'}],
                                   [tool], {'type': 'function', 'function': {'name': 'connection_check'}})
        calls = response['message'].get('tool_calls', [])
        if len(calls) != 1 or calls[0]['function']['name'] != 'connection_check' or json.loads(calls[0]['function']['arguments']) != {}:
            raise ValueError('Tool calling check failed')
        print(json.dumps({'status': 'ok', **response}, ensure_ascii=False, indent=2))
        return
    url = os.getenv('DATABASE_URL')
    if not url:
        parser.error('Set DATABASE_URL in .env or use Docker Compose')
    store = Day06Store(url, strategy=args.index)
    try:
        if args.command == 'bench':
            from .benchmark import run_benchmark
            from .llm import OpenRouter
            result = run_benchmark(store, split=args.split, suite=args.suite, output=args.output,
                                   client=OpenRouter() if args.suite == 'agent' else None, selection=args.selection,
                                   workers=args.workers, resume=args.resume)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if any(row['errors'] for row in result['summary']):
                raise SystemExit(1)
            return
        elif args.command == 'check':
            result = {'status': 'ok', 'index': args.index, 'chunk_count': len(store.chunks),
                      'embedding': store.identity['resolved_embedding'], 'corpus_sha256': store.identity['corpus_sha256']}
        else:
            lexical = BM25(store.chunks)
            retriever = {'dense': store, 'bm25': lexical, 'hybrid': Hybrid(store, lexical)}[args.method]
            started = time.perf_counter()
            if args.command == 'ask':
                from .llm import OpenRouter
                from .agent import run_agent
                from .context import NeighborContext
                result = run_agent(args.query, OpenRouter(), retriever, filters=args.filter,
                                   top_k=args.top_k, budget=args.budget, max_searches=args.max_searches,
                                   context_builder=NeighborContext(store.chunks, args.neighbors))
                result.update(method=args.method, index=args.index)
            else:
                hits = retriever.search(args.query, top_k=args.top_k, filters=args.filter)
                result = {'query': args.query, 'method': args.method, 'index': args.index,
                          'filter': args.filter, 'top_k': args.top_k, 'results': hits,
                          'elapsed_seconds': time.perf_counter() - started, 'api_cost_usd': 0}
        raw = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(raw, encoding='utf-8')
        print(raw, end='')
        if result.get('status') == 'error':
            raise SystemExit(1)
    finally:
        store.close()


if __name__ == '__main__':
    from .llm import ProviderError
    try:
        main()
    except ProviderError as exc:
        import sys
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
