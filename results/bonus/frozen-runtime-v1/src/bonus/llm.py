"""Bonus provider selection; Gemini calls Google's API directly, without a gateway.

Protocol: https://ai.google.dev/gemini-api/docs/openai
No SDK dependency, automatic provider/model switch, or invented billing cost.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from day07.llm import OpenRouter, ProviderError


class Gemini:
    provider = 'gemini'
    endpoint = 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'

    def __init__(self, key=None, model=None, timeout=None):
        self.key = key if key is not None else os.getenv('GEMINI_API_KEY', '')
        self.model = model or os.getenv('GEMINI_MODEL', 'gemini-3.8-flash')
        self.timeout = float(timeout if timeout is not None else os.getenv('GEMINI_TIMEOUT_SECONDS', '120'))
        self.max_tokens = int(os.getenv('GEMINI_MAX_OUTPUT_TOKENS', '8192'))
        self.reasoning_effort = os.getenv('GEMINI_REASONING_EFFORT', 'low')
        self.max_retries = int(os.getenv('GEMINI_MAX_RETRIES', '2'))
        self.min_interval = float(os.getenv('GEMINI_MIN_INTERVAL_SECONDS', '12'))
        self.max_inflight = int(os.getenv('GEMINI_MAX_INFLIGHT', '1'))
        self._request_lock = threading.Lock()
        self._last_request_completed = None
        self._last_request_started = None
        if not self.key.strip():
            raise ValueError('Set GEMINI_API_KEY in the root .env file; do not paste it into chat')
        if not 0 < self.timeout <= 300 or not 128 <= self.max_tokens <= 32768:
            raise ValueError('Invalid Gemini timeout or output-token budget')
        if self.reasoning_effort not in {'none','minimal','low','medium','high'}:
            raise ValueError('Invalid GEMINI_REASONING_EFFORT')
        if not 0 <= self.max_retries <= 3:
            raise ValueError('GEMINI_MAX_RETRIES must be between 0 and 3')
        if not 0 <= self.min_interval <= 60:
            raise ValueError('GEMINI_MIN_INTERVAL_SECONDS must be between 0 and 60')
        if not 1 <= self.max_inflight <= 3:
            raise ValueError('GEMINI_MAX_INFLIGHT must be between 1 and 3')
        self._inflight_slots = threading.BoundedSemaphore(self.max_inflight)

    @property
    def settings(self):
        return {'provider':self.provider,'model':self.model,'max_output_tokens':self.max_tokens,
                'reasoning_effort':self.reasoning_effort,'temperature':0,'max_retries':self.max_retries,
                'min_interval_seconds':self.min_interval,'max_inflight':self.max_inflight}

    def complete(self, messages, tools, tool_choice='auto'):
        started=time.perf_counter(); attempts=[]
        for attempt in range(self.max_retries+1):
            call_started=time.perf_counter()
            try:
                result, pacing_wait=self._paced_complete_once(messages,tools,tool_choice)
            except ProviderError as exc:
                attempts.append({'attempt':attempt+1,'status':'error','error':str(exc),
                                 'pacing_wait_seconds':getattr(exc,'pacing_wait_seconds',0),
                                 'elapsed_seconds':time.perf_counter()-call_started})
                if attempt<self.max_retries and any(f'Gemini HTTP {code}:' in str(exc) for code in (502,503,504)):
                    delay=2**(attempt+1)
                    attempts[-1]['retry_delay_seconds']=delay
                    time.sleep(delay)
                    continue
                exc.transport_attempts=attempts
                raise
            attempts.append({'attempt':attempt+1,'status':'ok','pacing_wait_seconds':pacing_wait,
                             'elapsed_seconds':time.perf_counter()-call_started})
            result.update(transport_attempts=attempts,elapsed_seconds=time.perf_counter()-started)
            return result

    def _paced_complete_once(self, messages, tools, tool_choice):
        # Bound active HTTP requests, including retries. In serial mode keep
        # the quiet interval after completion. In parallel mode space request
        # starts and release the scheduling lock before network I/O.
        with self._inflight_slots:
            with self._request_lock:
                previous=self._last_request_completed if self.max_inflight==1 else self._last_request_started
                wait_seconds=0 if previous is None else max(0,self.min_interval-(time.monotonic()-previous))
                if wait_seconds:time.sleep(wait_seconds)
                self._last_request_started=time.monotonic()
            try:
                result=self._complete_once(messages,tools,tool_choice)
            except ProviderError as exc:
                exc.pacing_wait_seconds=wait_seconds
                raise
            finally:
                completed=time.monotonic()
                with self._request_lock:self._last_request_completed=completed
            return result,wait_seconds

    def _complete_once(self, messages, tools, tool_choice):
        payload={'model':self.model,'messages':messages,'tools':tools,'tool_choice':tool_choice,
                 'temperature':0,'max_tokens':self.max_tokens,'reasoning_effort':self.reasoning_effort}
        request=urllib.request.Request(self.endpoint,data=json.dumps(payload).encode(),headers={
            'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
        started=time.perf_counter()
        try:
            with urllib.request.urlopen(request,timeout=self.timeout) as response:
                data=json.load(response)
        except urllib.error.HTTPError as exc:
            detail=''
            try:
                error=json.loads(exc.read(16384)).get('error',{})
                message=error.get('message') if isinstance(error,dict) else None
                if isinstance(message,str):
                    detail=message.replace(self.key,'[REDACTED]')
                    detail=re.sub(r'AIza[A-Za-z0-9_-]+','[REDACTED]',detail)
                    detail=re.sub(r'(?i)bearer\s+\S+','Bearer [REDACTED]',detail)
                    detail=' '.join(detail.split())[:500]
            except (OSError,ValueError,AttributeError,TypeError):
                pass
            hints={400:'Invalid request or unsupported model parameters',401:'Invalid API key',
                   403:'API key/project access denied',404:'Model not available for this project',
                   429:'Rate limit or project quota exhausted',
                   502:'Upstream service unavailable',503:'Model service temporarily unavailable or overloaded; retry later',
                   504:'Upstream service timed out'}
            raise ProviderError(f'Gemini HTTP {exc.code}: {detail or hints.get(exc.code,"API request failed")}') from None
        except (urllib.error.URLError,TimeoutError,OSError):
            raise ProviderError('Gemini connection failed or timed out; no fallback result was generated') from None
        except (ValueError,UnicodeError):
            raise ProviderError('Gemini returned invalid JSON') from None
        try:
            choice=data['choices'][0]; message=choice['message']; usage=data.get('usage',{})
            if not isinstance(message,dict) or message.get('role')!='assistant' or not isinstance(usage,dict):
                raise ValueError
            if choice.get('finish_reason') in {'length','content_filter'}:
                raise ValueError
        except (KeyError,IndexError,ValueError,TypeError):
            raise ProviderError('Gemini response missing a complete assistant message') from None
        # Preserve raw tool calls, including Gemini thought signatures. Google
        # reports token counts here, not the final billed amount for the project.
        return {'message':message,'usage':{**usage,'cost':None},'id':data.get('id'),
                'model':data.get('model',self.model),'provider':self.provider,
                'finish_reason':choice.get('finish_reason'),'elapsed_seconds':time.perf_counter()-started}


def client_settings(client):
    return getattr(client,'settings',{'provider':'openrouter','model':client.model})


def make_client(provider=None):
    name=provider or os.getenv('BONUS_LLM_PROVIDER','openrouter')
    if name=='openrouter':return OpenRouter()
    if name=='gemini':return Gemini()
    raise ValueError('BONUS_LLM_PROVIDER must be openrouter or gemini')
