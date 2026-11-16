"""Verify protocol, context, citations, and failures without charging API calls."""
import json
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from day07.agent import run_agent
from day07.llm import OpenRouter, ProviderError

CHUNK = {'id': 'c1', 'source_id': 'doc', 'source': 'doc.pdf', 'page': 1,
         'text': 'Insurance covers the household.', 'metadata': {}, 'score': 0.9}


class Client:
    model = 'offline-fixture'
    def __init__(self, actions): self.actions = iter(actions); self.requests = []
    def complete(self, messages, tools, tool_choice='auto'):
        self.requests.append(json.loads(json.dumps(messages)))
        name, arguments = next(self.actions)
        return {'message': {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': str(len(self.requests)), 'type': 'function',
             'function': {'name': name, 'arguments': json.dumps(arguments)}}]},
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'cost': 0.01}}


class Retriever:
    def search(self, query, *, top_k, filters): return [CHUNK]


class Day07AgentTests(unittest.TestCase):
    def test_real_protocol_and_trace_usage(self):
        client = Client([('search', {'query': 'insurance'}),
                         ('finish', {'status': 'answered', 'answer': 'Insurance covers the household [c1].', 'citations': ['c1']})])
        result = run_agent('What is covered?', client, Retriever())
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['context_ids'], ['c1'])
        self.assertAlmostEqual(result['usage']['api_cost_usd'], 0.02)
        self.assertEqual(client.requests[1][-1]['role'], 'tool')

    def test_unknown_citations_are_errors_not_successful_abstentions(self):
        client = Client([('search', {'query': 'insurance'}),
                         ('finish', {'status': 'answered', 'answer': 'Unsupported [invented]', 'citations': ['invented']}),
                         ('finish', {'status': 'answered', 'answer': 'Unsupported [invented]', 'citations': ['invented']})])
        result = run_agent('Question?', client, Retriever())
        self.assertEqual(result['status'], 'error')
        self.assertTrue(result['events'][-1]['event'] == 'error')
        self.assertEqual(result['usage']['llm_calls'], 3)
        self.assertIn('CURRENT_CONTEXT', result['error'])

    def test_missing_inline_citation_gets_one_traced_model_repair(self):
        client = Client([('search', {'query': 'insurance'}),
                         ('finish', {'status': 'answered', 'answer': 'Insurance covers the household.', 'citations': ['c1']}),
                         ('finish', {'status': 'answered', 'answer': 'Insurance covers the household [c1].', 'citations': ['c1']})])
        result = run_agent('Question?', client, Retriever(), max_searches=1)
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['format_repairs'], 1)
        self.assertEqual(result['usage']['llm_calls'], 3)
        self.assertAlmostEqual(result['usage']['api_cost_usd'], 0.03)
        self.assertEqual(sum(e['event'] == 'invalid_finish' for e in result['events']), 1)
        self.assertFalse(json.loads(client.requests[-1][-1]['content'])['accepted'])

    def test_cumulative_context_replaced_in_history(self):
        client = Client([('search', {'query': 'first'}), ('search', {'query': 'second'}),
                         ('finish', {'status': 'abstain', 'answer': 'Insufficient evidence.', 'citations': []})])
        result = run_agent('Question?', client, Retriever(), max_searches=2, budget=100)
        self.assertEqual(result['status'], 'abstain')
        tools = [m for m in client.requests[-1] if m['role'] == 'tool']
        self.assertNotIn('Insurance covers', tools[0]['content'])
        self.assertLessEqual(len(result['context']), 100)

    def test_provider_http_failure_does_not_leak_key(self):
        client = OpenRouter(key='private-example-key')
        failure = urllib.error.HTTPError(client.endpoint, 401, 'private-example-key', {}, None)
        with patch('urllib.request.urlopen', side_effect=failure):
            with self.assertRaises(ProviderError) as caught:
                client.complete([], [])
        self.assertNotIn('private-example-key', str(caught.exception))
        self.assertIn('401', str(caught.exception))

    def test_routing_error_is_visible_and_credentials_are_redacted(self):
        client = OpenRouter(key='private-example-key')
        body = json.dumps({'error': {'message': 'No endpoints support parameters. private-example-key sk-or-v1-secret',
                                    'metadata': {'raw': 'not for logging'}}}).encode()
        failure = urllib.error.HTTPError(client.endpoint, 404, 'Not Found', {}, io.BytesIO(body))
        with patch('urllib.request.urlopen', side_effect=failure):
            with self.assertRaises(ProviderError) as caught:
                client.complete([], [])
        detail = str(caught.exception)
        self.assertIn('No endpoints support parameters', detail)
        self.assertNotIn('private-example-key', detail)
        self.assertNotIn('sk-or-v1-secret', detail)
        self.assertNotIn('not for logging', detail)

    def test_request_omits_unsupported_parallel_parameter(self):
        client = OpenRouter(key='test-key')
        with patch('urllib.request.urlopen', side_effect=urllib.error.URLError('offline')) as send:
            with self.assertRaises(ProviderError):
                client.complete([], [])
        payload = json.loads(send.call_args.args[0].data)
        self.assertNotIn('parallel_tool_calls', payload)
        self.assertTrue(payload['provider']['require_parameters'])
        self.assertEqual(payload['model'], 'openai/gpt-4o-mini')


if __name__ == '__main__': unittest.main()
