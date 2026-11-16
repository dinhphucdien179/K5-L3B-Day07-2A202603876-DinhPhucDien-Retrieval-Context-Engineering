"""OpenRouter Chat Completions client; no mock or provider fallback."""
import json
import os
import re
import time
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    pass


class OpenRouter:
    endpoint = 'https://openrouter.ai/api/v1/chat/completions'

    def __init__(self, key=None, model=None, timeout=None):
        self.key = key if key is not None else os.getenv('OPENROUTER_API_KEY', '')
        self.model = model or os.getenv('OPENROUTER_MODEL', 'openai/gpt-4o-mini')
        self.timeout = float(timeout if timeout is not None else os.getenv('OPENROUTER_TIMEOUT_SECONDS', '90'))
        if not self.key.strip():
            raise ValueError('Set OPENROUTER_API_KEY in the root .env file; do not paste it into chat')
        if not 0 < self.timeout <= 300:
            raise ValueError('API timeout must be between 0 and 300 seconds')

    def complete(self, messages, tools, tool_choice='auto'):
        payload = {'model': self.model, 'messages': messages, 'tools': tools,
                   'tool_choice': tool_choice,
                   'temperature': 0, 'max_tokens': 1200,
                   'provider': {'require_parameters': True}}
        request = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode(),
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            # Expose only the top-level message, never raw provider metadata/headers.
            detail = ''
            try:
                error = json.loads(exc.read(16384)).get('error', {})
                message = error.get('message') if isinstance(error, dict) else None
                if isinstance(message, str):
                    detail = message.replace(self.key, '[REDACTED]')
                    detail = re.sub(r'sk-[A-Za-z0-9_-]+', '[REDACTED]', detail)
                    detail = re.sub(r'(?i)bearer\s+\S+', 'Bearer [REDACTED]', detail)
                    detail = ' '.join(detail.split())[:500]
            except (OSError, ValueError, AttributeError, TypeError):
                pass
            hints = {401: 'API key invalid or unauthorized', 402: 'Insufficient credit or account/key spending limit',
                     404: 'Model or provider endpoint unavailable for these parameters/account settings',
                     429: 'Rate limit exceeded'}
            suffix = detail or hints.get(exc.code, 'API request failed')
            raise ProviderError(f'OpenRouter HTTP {exc.code}: {suffix}') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ProviderError('OpenRouter connection failed or timed out; no fallback result was generated') from None
        except (ValueError, UnicodeError):
            raise ProviderError('OpenRouter returned invalid JSON') from None
        try:
            choice = data['choices'][0]
            message = choice['message']
            if not isinstance(message, dict) or message.get('role') != 'assistant':
                raise ValueError
            if choice.get('finish_reason') in ('length', 'content_filter'):
                raise ValueError
            usage = data.get('usage', {})
            if not isinstance(usage, dict):
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError('OpenRouter response missing a complete assistant message') from None
        return {'message': message, 'usage': usage, 'id': data.get('id'),
                'model': data.get('model', self.model), 'provider': data.get('provider'),
                'finish_reason': choice.get('finish_reason'),
                'elapsed_seconds': time.perf_counter() - started}
