import io
import json
import os
from pathlib import Path
import sys
import unittest
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bonus.agent import run
from bonus.llm import Gemini, make_client, client_settings
from day07.llm import ProviderError


class GeminiTests(unittest.TestCase):
    def setUp(self):
        environment=patch.dict(os.environ,{'GEMINI_MIN_INTERVAL_SECONDS':'0','GEMINI_MAX_INFLIGHT':'1'})
        environment.start(); self.addCleanup(environment.stop)

    def test_direct_api_preserves_tool_thought_signature_across_agent_turns(self):
        record={'id':'p001','page':1,'kind':'page','text':'The value is 25 units.','bbox':[0,0,10,10]}
        class Search:
            by_id={'p001':record}
            def search(self,q,k):return [record]
            def expand(self,rows):return rows
        requests=[]
        def respond(request,timeout):
            payload=json.loads(request.data);requests.append(payload)
            self.assertEqual(request.full_url,Gemini.endpoint)
            self.assertNotIn('provider',payload)
            self.assertEqual(payload['max_tokens'],8192)
            name='search' if len(requests)==1 else 'finish'
            args={'query':'value'} if name=='search' else {'status':'answered','claims':[{
                'text':'The value is 25 units.','supports':[{'evidence_id':'p001','mode':'text','quote':record['text']}]}],
                'abstention_reason':''}
            call={'id':name,'type':'function','function':{'name':name,'arguments':json.dumps(args)},
                  'extra_content':{'google':{'thought_signature':'fixture-signature'}}}
            return io.BytesIO(json.dumps({'choices':[{'finish_reason':'tool_calls',
                'message':{'role':'assistant','content':None,'tool_calls':[call]}}],
                'usage':{'prompt_tokens':20,'completion_tokens':10}}).encode())
        config={'vision':False,'max_searches':1,'max_inspections':1,'top_k':1,'context_budget_chars':1000}
        with patch.dict(os.environ,{'GEMINI_MIN_INTERVAL_SECONDS':'0'},clear=True),patch('bonus.llm.urllib.request.urlopen',side_effect=respond):
            result=run('Question',Gemini(key='fixture-not-a-key'),Search(),config)
        self.assertEqual(result['status'],'answered')
        assistant=next(m for m in requests[1]['messages'] if m['role']=='assistant')
        self.assertEqual(assistant['tool_calls'][0]['extra_content']['google']['thought_signature'],'fixture-signature')
        self.assertIsNone(result['usage']['api_cost_usd'])
        self.assertNotIn('fixture-not-a-key',json.dumps(result))

    def test_google_errors_redact_credentials_and_do_not_retry(self):
        secret='AIza-fixture-never-print'
        body=json.dumps({'error':{'message':f'Quota exhausted for {secret}; Bearer hidden-token'}}).encode()
        error=urllib.error.HTTPError(Gemini.endpoint,429,'quota',{},io.BytesIO(body))
        with patch('bonus.llm.urllib.request.urlopen',side_effect=error) as transport:
            with self.assertRaises(ProviderError) as caught:Gemini(key=secret).complete([],[])
        self.assertEqual(transport.call_count,1)
        self.assertIn('Gemini HTTP 429',str(caught.exception))
        self.assertNotIn(secret,str(caught.exception))
        self.assertNotIn('hidden-token',str(caught.exception))

    def test_provider_choice_is_explicit_and_semantic_settings_are_recorded(self):
        with patch.dict(os.environ,{'BONUS_LLM_PROVIDER':'gemini'},clear=True),patch('bonus.llm.OpenRouter') as router:
            with self.assertRaisesRegex(ValueError,'GEMINI_API_KEY'):make_client()
            router.assert_not_called()
        with patch.dict(os.environ,{'GEMINI_API_KEY':'fixture','GEMINI_MODEL':'chosen-model','GEMINI_REASONING_EFFORT':'medium'},clear=True):
            client=make_client('gemini')
            self.assertEqual(client_settings(client)['model'],'chosen-model')
            self.assertEqual(client_settings(client)['reasoning_effort'],'medium')
            self.assertNotIn('fixture',json.dumps(client_settings(client)))

    def test_unavailable_retries_are_bounded_and_preserved(self):
        def unavailable():
            return urllib.error.HTTPError(Gemini.endpoint,503,'unavailable',{},io.BytesIO(b''))
        response={'choices':[{'message':{'role':'assistant','content':'OK'},'finish_reason':'stop'}],'usage':{}}
        with patch.dict(os.environ,{'GEMINI_MIN_INTERVAL_SECONDS':'0'},clear=True),patch('bonus.llm.time.sleep') as sleep:
            with patch('bonus.llm.urllib.request.urlopen',side_effect=[unavailable(),io.BytesIO(json.dumps(response).encode())]) as transport:
                result=Gemini(key='fixture').complete([],[])
                self.assertEqual(transport.call_count,2)
                self.assertEqual([a['status'] for a in result['transport_attempts']],['error','ok'])
                sleep.assert_called_once_with(2)
            with patch('bonus.llm.urllib.request.urlopen',side_effect=lambda *a,**k: (_ for _ in ()).throw(unavailable())) as transport:
                with self.assertRaises(ProviderError) as caught:Gemini(key='fixture').complete([],[])
                self.assertEqual(transport.call_count,3)
                self.assertEqual(len(caught.exception.transport_attempts),3)
                self.assertIn('unavailable',str(caught.exception))

    def test_timeout_does_not_resubmit_an_in_flight_generation(self):
        with patch('bonus.llm.urllib.request.urlopen',side_effect=TimeoutError) as transport:
            with self.assertRaises(ProviderError):Gemini(key='fixture').complete([],[])
        self.assertEqual(transport.call_count,1)

    def test_requests_do_not_overlap_and_failed_requests_are_paced(self):
        client=Gemini(key='fixture'); active=peak=0
        counts_lock=threading.Lock()
        def request(*args):
            nonlocal active,peak
            with counts_lock:active+=1;peak=max(peak,active)
            time.sleep(.02)
            with counts_lock:active-=1
            return {'message':{},'usage':{}}
        with patch.object(client,'_complete_once',side_effect=request),ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda _:client.complete([],[]),range(3)))
        self.assertEqual(peak,1)
        clock=[0.0];starts=[]
        def fail_then_succeed(*args):
            starts.append(clock[0]);clock[0]+=2
            if len(starts)==1:raise ProviderError('Gemini HTTP 429: quota')
            return {'message':{},'usage':{}}
        client=Gemini(key='fixture');client.min_interval=12
        with patch('bonus.llm.time.monotonic',side_effect=lambda:clock[0]),patch('bonus.llm.time.sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)),patch.object(client,'_complete_once',side_effect=fail_then_succeed):
            with self.assertRaises(ProviderError):client.complete([],[])
            result=client.complete([],[])
        self.assertEqual(starts,[0,14])
        self.assertEqual(result['transport_attempts'][0]['pacing_wait_seconds'],12)

    def test_parallel_requests_overlap_without_exceeding_configured_cap(self):
        with patch.dict(os.environ,{'GEMINI_MAX_INFLIGHT':'2','GEMINI_MIN_INTERVAL_SECONDS':'0'}):
            client=Gemini(key='fixture')
        active=peak=0;counts_lock=threading.Lock()
        def request(*args):
            nonlocal active,peak
            with counts_lock:active+=1;peak=max(peak,active)
            time.sleep(.03)
            with counts_lock:active-=1
            return {'message':{},'usage':{}}
        with patch.object(client,'_complete_once',side_effect=request),ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:client.complete([],[]),range(6)))
        self.assertEqual(peak,2)
        self.assertEqual(len(results),6)
