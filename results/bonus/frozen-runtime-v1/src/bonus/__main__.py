"""Independent CLI: python -m bonus prepare/search/ask/bench/review/select."""
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv
from .corpus import ROOT, prepare, load_corpus, write, page_image
from .agent import Retriever, run
from .benchmark import execute, summarize, select
from .llm import make_client
from day07.llm import ProviderError


def main():
    load_dotenv(ROOT/'.env')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['prepare','page','search','llm-check','ask','bench','review','select'])
    p.add_argument('--provider',choices=['openrouter','gemini'],help='Override BONUS_LLM_PROVIDER for this command')
    p.add_argument('--query');p.add_argument('--trial',default='layout_vision')
    p.add_argument('--trials',nargs='+',help='Dev configurations to run (default: all)')
    p.add_argument('--split',choices=['dev','test'],default='dev');p.add_argument('--output',type=Path)
    p.add_argument('--run',type=Path);p.add_argument('--selection',type=Path);p.add_argument('--reason')
    p.add_argument('--workers',type=int,choices=[1,2,3],default=2);p.add_argument('--resume',action='store_true')
    p.add_argument('--reextract',action='store_true')
    p.add_argument('--page',type=int)
    a=p.parse_args()
    if a.command=='prepare':
        result=prepare(reextract=a.reextract);result={k:result[k] for k in ['indexed_pages','figure_records','table_records','corpus_sha256']}
    elif a.command=='page':
        if a.page is None:p.error('--page required')
        path=page_image(a.page)
        result={'physical_page':a.page,'image':str(path.relative_to(ROOT))}
    elif a.command=='llm-check':
        client=make_client(a.provider)
        tool={'type':'function','function':{'name':'connection_check','description':'Confirm tool connection.',
              'parameters':{'type':'object','properties':{}}}}
        response=client.complete([{'role':'user','content':'Call connection_check with empty arguments.'}],
                                [tool],{'type':'function','function':{'name':'connection_check'}})
        calls=response['message'].get('tool_calls',[])
        ok=len(calls)==1 and calls[0]['function']['name']=='connection_check' and json.loads(calls[0]['function']['arguments'])=={}
        result={'status':'ok' if ok else 'error',**response}
    elif a.command=='bench':
        if not a.output:p.error('--output required')
        result=execute(a.split,a.output,make_client(a.provider),a.selection,a.workers,a.resume,a.trials)
    elif a.command=='review':
        if not a.run:p.error('--run required')
        result=summarize(a.run,a.split)
    elif a.command=='select':
        if not(a.run and a.output and a.reason):p.error('--run --output --reason required')
        result=select(a.run,a.trial,a.output,a.reason)
    else:
        if not a.query:p.error('--query required')
        retriever=Retriever(load_corpus())
        if a.command=='search':result=retriever.search(a.query)
        else:
            configs=json.loads((ROOT/'config/bonus_trials.json').read_text())
            config=next(c for c in configs if c['name']==a.trial)
            result=run(a.query,make_client(a.provider),retriever,config)
        if a.output:write(a.output,result)
    if a.command=='ask' and a.output:
        print(json.dumps({k:result.get(k) for k in ['status','answer','citations','error','usage','elapsed_seconds']},ensure_ascii=False,indent=2))
    else:print(json.dumps(result,ensure_ascii=False,indent=2))
    if isinstance(result,dict) and result.get('status')=='error':raise SystemExit(1)

if __name__=='__main__':
    try:main()
    except ProviderError as exc:
        print(json.dumps({'status':'error','error':str(exc),
                          'transport_attempts':getattr(exc,'transport_attempts',[])},ensure_ascii=False,indent=2))
        raise SystemExit(1)
