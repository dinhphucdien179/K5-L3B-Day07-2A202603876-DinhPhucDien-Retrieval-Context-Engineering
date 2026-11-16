"""Frozen split execution, dev-only selection, strict per-case source reviews."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from .agent import Retriever, run
from .corpus import ROOT, DATA, digest, load_corpus, write
from .llm import client_settings


def fingerprint():
    paths=[*sorted((ROOT/'src/bonus').glob('*.py')),
           ROOT/'src/day07/llm.py',ROOT/'src/day07/retrieval.py',ROOT/'src/day07/agent.py',
           ROOT/'config/bonus_trials.json']
    return {str(p.relative_to(ROOT)):digest(p) for p in paths}


def benchmark_directory(directory):
    path=Path(directory).resolve()
    if not path.is_relative_to(ROOT):raise ValueError('Benchmark must be inside project for portable provenance')
    return path


def validate_split(split, dataset=DATA):
    dataset=benchmark_directory(dataset)
    frozen=json.loads((dataset/'freeze.json').read_text())
    for s in ['dev','test']:
        if digest(dataset/f'{s}.json')!=frozen[f'{s}_sha256']:
            raise ValueError('Frozen benchmark changed')
    if digest(DATA/'corpus.jsonl')!=frozen['corpus_sha256']:
        raise ValueError('Frozen corpus changed')
    cases=json.loads((dataset/f'{split}.json').read_text())
    if len({c['id'] for c in cases})!=len(cases):
        raise ValueError('Duplicate case ID')
    counts={g:sum(c['group']==g for c in cases) for g in ['table','diagram','chart','multi_hop','text','unanswerable']}
    limits={'dev':{'unanswerable':3},'test':{'table':6,'diagram':5,'chart':5,'multi_hop':4,'text':4,'unanswerable':6}}
    if any(counts[g]<v for g,v in limits[split].items()) or (split=='dev' and sum(c['answerable'] for c in cases)<15):
        raise ValueError('Benchmark minimum counts not met')
    by_id={r['id']:r for r in load_corpus()}
    for c in cases:
        if c['answerable']:
            if not c['gold'] or (c['group']=='multi_hop' and len({g['page'] for g in c['gold']})<2):
                raise ValueError('Missing multi-hop/source evidence')
            for g in c['gold']:
                if g['id'] not in by_id or by_id[g['id']]['page']!=g['page'] or not g['region']:
                    raise ValueError('Gold locator does not resolve')
        elif not c.get('absence_audit'):
            raise ValueError('Missing absence audit')
    return cases


def execute(split, output, client, selection=None, workers=2, resume=False, trials=None, dataset=DATA):
    dataset=benchmark_directory(dataset)
    cases=validate_split(split,dataset)
    configs=json.loads((ROOT/'config/bonus_trials.json').read_text())
    if trials is not None:
        if split!='dev' or not trials or len(set(trials))!=len(trials) or set(trials)-{c['name'] for c in configs}:
            raise ValueError('Explicit trials must name distinct existing dev configurations')
        configs=[c for c in configs if c['name'] in trials]
    if split=='test':
        if selection is None:raise ValueError('Test requires dev selection')
        chosen=json.loads(Path(selection).read_text())
        if chosen.get('benchmark_dir','data/bonus')!=str(dataset.relative_to(ROOT)) or chosen['code_sha256']!=fingerprint() or chosen['freeze_sha256']!=digest(dataset/'freeze.json') or chosen['model']!=client.model or chosen.get('client_settings')!=client_settings(client) or chosen.get('workers')!=workers:
            raise ValueError('Selected pipeline/model/benchmark changed after dev freeze')
        for relative,expected in chosen['dev_artifacts_sha256'].items():
            if digest(ROOT/relative)!=expected:raise ValueError('Dev artifact changed after selection')
        configs=[c for c in configs if c['name']==chosen['trial']]
        if len(configs)!=1:raise ValueError('Selected trial missing')
    output=Path(output)
    identity={'split':split,'model':client.model,'client_settings':client_settings(client),'workers':workers,'configs':configs,'code_sha256':fingerprint(),
              'benchmark_dir':str(dataset.relative_to(ROOT)),
              'freeze_sha256':digest(dataset/'freeze.json'),'corpus_sha256':digest(DATA/'corpus.jsonl'),
              'selection_sha256':digest(selection) if selection else None}
    manifest=output/'run.json'
    if manifest.exists():
        if not resume:raise ValueError('Output already exists; use --resume')
        old=json.loads(manifest.read_text())
        if old['identity']!=identity:raise ValueError('Resume identity mismatch')
    else:
        if output.exists() and any(output.iterdir()):raise ValueError('Output directory not empty')
        write(manifest,{'created_utc':datetime.now(timezone.utc).isoformat(),'identity':identity})
    retriever=Retriever(load_corpus())
    tasks=[]
    for config in configs:
        for case in cases:
            path=output/config['name']/f"{case['id']}.json"
            if path.exists():
                saved=json.loads(path.read_text())
                if saved['case_id']!=case['id'] or saved['question']!=case['question'] or saved['config']!=config:
                    raise ValueError('Saved case mismatch')
            else:tasks.append((config,case,path))
    # A no-op resume must not rewrite artifacts already hashed by selection.
    if not tasks and (output/'execution.json').exists():
        return json.loads((output/'execution.json').read_text())
    started=time.perf_counter()
    def work(config,case,path):
        # Evaluator gold never enters agent/retriever. Only the public question does.
        result=run(case['question'],client,retriever,config)
        result.update(case_id=case['id'],split=split)
        write(path,result)
        return config['name'],case['id'],result['status'],result['usage']['api_cost_usd'],result.get('error','')
    credit_blocked=False
    provider_blocked=False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending=iter(tasks)
        futures={pool.submit(work,*t) for t in [next(pending,None) for _ in range(workers)] if t is not None}
        while futures:
            done,futures=wait(futures,return_when=FIRST_COMPLETED)
            for f in done:
                name,cid,status,cost,error=f.result()
                print(json.dumps({'trial':name,'id':cid,'status':status,'cost_usd':cost}),flush=True)
                if 'HTTP 402' in error:credit_blocked=True
                if any(f'HTTP {code}' in error for code in [401,402,403,429,502,503,504]) or 'connection failed or timed out' in error:
                    provider_blocked=True
            if not provider_blocked:
                for _ in done:
                    t=next(pending,None)
                    if t is not None:futures.add(pool.submit(work,*t))
    result={'split':split,'workers':workers,'cases_per_trial':len(cases),'trials':[c['name'] for c in configs],
            'planned_new_cases':len(tasks),'elapsed_seconds_this_execution':time.perf_counter()-started,
            'status':'error' if provider_blocked else 'complete',
            'credit_blocked':credit_blocked,
            'provider_blocked':provider_blocked,
            'remaining_unrun':sum(not (output/c['name']/f"{case['id']}.json").exists() for c in configs for case in cases)}
    for config in configs:
        template=output/config['name']/'reviews.template.json'
        if not template.exists():
            labels={}
            for c in cases:
                trace_path=output/config['name']/f"{c['id']}.json"
                trace=json.loads(trace_path.read_text()) if trace_path.exists() else {}
                labels[c['id']]={'answer_correct':None,'citation_complete':None,'abstention_correct':None,
                    'reason':'','checked_original_pages':[],'reviewer':'',
                    'citation_checks':{cid:{'supported':None,'reason':''} for cid in trace.get('citations',[])},
                    'expected_evidence':[{'page':g['page'],'region':g['region']} for g in c.get('gold',[])]}
            write(template,labels)
    write(output/'execution.json',result)
    return result


def summarize(directory, split):
    directory=Path(directory)
    manifest=directory.parent/'run.json'
    dataset=ROOT/json.loads(manifest.read_text())['identity'].get('benchmark_dir','data/bonus') if manifest.exists() else DATA
    cases=validate_split(split,dataset)
    reviews=json.loads((directory/'reviews.json').read_text())
    if set(reviews)!= {c['id'] for c in cases}:raise ValueError('Review ALL cases exactly once')
    groups={}
    total_cost=total_time=prompt=completion=errors=passes=0
    for case in cases:
        trace=json.loads((directory/f"{case['id']}.json").read_text())
        r=reviews[case['id']]
        required={'answer_correct','citation_complete','abstention_correct','reason','checked_original_pages','reviewer'}
        if not required<=set(r) or not r['reason'].strip() or not r['reviewer'].strip():raise ValueError('Incomplete review')
        if any(type(r[k]) is not bool for k in ('answer_correct','citation_complete','abstention_correct')):
            raise ValueError('Review decisions must be booleans')
        if case['answerable'] and not {g['page'] for g in case['gold']} <= set(r['checked_original_pages']):
            raise ValueError('Original evidence pages were not checked')
        if trace['status']=='answered':
            checks=r.get('citation_checks',{})
            if not trace.get('citations') or set(checks)!=set(trace['citations']):
                raise ValueError('Review each actual citation exactly once')
            if any(type(v.get('supported')) is not bool or not v.get('reason','').strip() for v in checks.values()):
                raise ValueError('Each citation needs support decision and reason')
            if r['citation_complete'] and not all(v['supported'] for v in checks.values()):
                raise ValueError('Incomplete citation support cannot be labeled complete')
        if case['answerable']:
            passed=trace['status']=='answered' and r['answer_correct'] and r['citation_complete']
        else:
            passed=trace['status']=='abstain' and r['abstention_correct']
        bucket=groups.setdefault(case['group'],{'passed':0,'total':0,'errors':0})
        bucket['total']+=1;bucket['passed']+=int(passed);bucket['errors']+=int(trace['status']=='error')
        passes+=passed; errors+=trace['status']=='error'
        cost=trace['usage']['api_cost_usd']
        if cost is None:total_cost=None
        elif total_cost is not None:total_cost+=cost
        total_time+=trace['elapsed_seconds'];prompt+=trace['usage']['prompt_tokens'];completion+=trace['usage']['completion_tokens']
        r['passed']=passed;r['trace_sha256']=digest(directory/f"{case['id']}.json")
    for g in groups.values():g['rate']=g['passed']/g['total']
    result={'passed':passes,'total':len(cases),'rate':passes/len(cases),'bonus_threshold_met':passes*10>=len(cases)*9,
            'errors':errors,'groups':groups,'api_cost_usd':total_cost,'case_latency_sum_seconds':total_time,
            'prompt_tokens':prompt,'completion_tokens':completion,
            'review_policy':'AI-assisted source inspection; student verification pending. Not an independent human review.'}
    write(directory/'reviews.json',reviews);write(directory/'summary.json',result)
    return result


def select(dev_run, trial, output, reason):
    dev_run=Path(dev_run).resolve()
    manifest=json.loads((dev_run/'run.json').read_text())
    if manifest['identity']['split']!='dev' or manifest['identity']['code_sha256']!=fingerprint():
        raise ValueError('Dev provenance mismatch')
    summaries={c['name']:summarize(dev_run/c['name'],'dev') for c in manifest['identity']['configs']}
    # Deterministic rule declared before test; ties prefer lower measured API cost.
    best=max(summaries,key=lambda n:(summaries[n]['rate'],-(summaries[n]['api_cost_usd'] if summaries[n]['api_cost_usd'] is not None else float('inf'))))
    if trial!=best:raise ValueError(f'Selection rule chooses {best}')
    result={'selected_utc':datetime.now(timezone.utc).isoformat(),'trial':trial,'reason':reason,
            'selection_rule':'Highest strict dev pass fraction, ties lowest measured cost',
            'model':manifest['identity']['model'],'client_settings':manifest['identity']['client_settings'],'workers':manifest['identity']['workers'],'code_sha256':fingerprint(),
            'benchmark_dir':manifest['identity'].get('benchmark_dir','data/bonus'),
            'freeze_sha256':manifest['identity']['freeze_sha256'],'dev_summaries':summaries,
            'dev_artifacts_sha256':{str(p.relative_to(ROOT)):digest(p) for p in sorted(dev_run.rglob('*.json'))}}
    if Path(output).exists():raise ValueError('Selection already frozen')
    write(output,result);return result
