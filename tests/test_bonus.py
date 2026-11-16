from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bonus.agent import Retriever, context_pack, render_claims, run, validate_witnesses, normalize_image_claims
from bonus.benchmark import summarize, validate_split, execute, select
from bonus.corpus import load_corpus, write
from bonus.visual import crop_bounds
from day07.agent import FinalFormatError


class BonusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (Path(__file__).resolve().parents[1]/'.cache/bonus').mkdir(parents=True,exist_ok=True)

    def test_full_document_and_frozen_category_counts(self):
        records=load_corpus()
        self.assertEqual({r['page'] for r in records if r['kind']=='page'},set(range(1,233)))
        self.assertEqual(sum(r['kind']=='figure' for r in records),171)
        self.assertEqual(sum(r['kind']=='table' for r in records),34)
        self.assertEqual(len(validate_split('dev')),18)
        cases=validate_split('test')
        self.assertEqual(len(cases),30)
        self.assertEqual(sum(c['answerable'] for c in cases),24)

    def test_replacement_holdout_preserves_dev_and_uses_new_test_questions(self):
        root=Path(__file__).resolve().parents[1]
        replacement=root/'data/bonus-v2'
        self.assertEqual((replacement/'dev.json').read_bytes(),(root/'data/bonus/dev.json').read_bytes())
        cases=validate_split('test',replacement)
        self.assertEqual(len(cases),30)
        old=json.loads((root/'data/bonus/test.json').read_text())+validate_split('dev')
        self.assertFalse({c['question'] for c in cases}&{c['question'] for c in old})
        self.assertEqual(len({g['id'] for c in cases if c['group']=='diagram' for g in c['gold']}),5)
        self.assertTrue(all(len({g['page'] for g in c['gold']})>=2 for c in cases if c['group']=='multi_hop'))

    def test_source_toc_errors_are_resolved_to_actual_page_captions(self):
        records={r['id']:r for r in load_corpus()}
        self.assertEqual(records['p217-table-8.1']['toc_page'],216)
        self.assertEqual(records['p220-figure-B.8.2.1']['toc_page'],219)
        self.assertEqual(records['p054-table-B.1.2.1']['toc_label'],'B.1.3.1')
        self.assertTrue(all(r.get('caption_bbox') for r in records.values() if r['kind']!='page'))

    def test_plural_document_locators_and_page_dedup(self):
        r=Retriever(load_corpus())
        rows=r.search('Compare Tables 4.1 and 4.2 for survival in 2020')
        self.assertEqual({x['id'] for x in rows[:2]},{'p132-table-4.1','p137-table-4.2'})
        self.assertEqual(len({x['page'] for x in rows}),len(rows))
        self.assertEqual(r.search('Look at Figure B.2.4.1')[0]['id'],'p096-figure-B.2.4.1')

    def test_context_budget_and_same_page_text_not_repeated(self):
        r=Retriever(load_corpus())
        rows=r.expand(r.search('Table 7.1'))
        text,chosen=context_pack(rows,16000)
        self.assertLessEqual(len(text),16000)
        self.assertEqual(len({x['id'] for x in chosen}),len(chosen))
        self.assertEqual(text.count('Table 7.1. Vietnam government revenues, 2018'),1)

    def test_renderer_uses_model_claim_mapping_and_rejects_unknown_evidence(self):
        args={'status':'answered','claims':[{'text':'A fact.','evidence_ids':['p001']}],'abstention_reason':''}
        status,answer,citations=render_claims(args,{'p001'})
        self.assertEqual((status,answer,citations),('answered','A fact. [p001]',['p001']))
        with self.assertRaises(FinalFormatError):render_claims(args,{'p002'})
        args['claims'][0]['evidence_ids']=[]
        with self.assertRaises(FinalFormatError):render_claims(args,{'p001'})
        with self.assertRaises(FinalFormatError):render_claims({'status':'abstain','claims':[{}],'abstention_reason':'No evidence'},set())

    def test_real_tool_protocol_never_sends_gold_and_logs_image_reference(self):
        record={'id':'p001','page':1,'kind':'page','text':'Corpus fact','source':'source.pdf','bbox':[0,0,100,100],'metadata':{}}
        class Search:
            by_id={'p001':record}
            def search(self,query,top_k):return [record]
            def expand(self,rows):return rows
        class Client:
            model='fixture'
            def __init__(self):self.requests=[]
            def complete(self,messages,tools,tool_choice):
                self.requests.append(json.loads(json.dumps(messages)))
                name='search' if len(self.requests)==1 else 'finish'
                args={'query':'fact'} if name=='search' else {'status':'answered','claims':[{'text':'Corpus fact','supports':[{'evidence_id':'p001','mode':'image','quote':''}]}],'abstention_reason':''}
                return {'message':{'role':'assistant','content':None,'tool_calls':[{'id':name,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]},'usage':{'cost':0}}
        config={'vision':True,'max_searches':1,'max_inspections':1,'top_k':1,'context_budget_chars':1000,'max_images':1,'image_width':1600}
        client=Client()
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root/'.cache/bonus') as temp:
            fake=Path(temp)/'fixture.jpg';fake.write_bytes(b'fixture-image-bytes')
            with patch('bonus.agent.page_image',return_value=fake):result=run('Question only',client,Search(),config)
        self.assertEqual(result['status'],'answered')
        self.assertIn('data:image/jpeg;base64,',json.dumps(client.requests))
        self.assertNotIn('data:image/jpeg;base64,',json.dumps(result))
        self.assertNotIn('expected_answer',json.dumps(client.requests))
        self.assertNotIn('verified_facts',json.dumps(client.requests))
        self.assertEqual(result['image_artifacts'][0]['page'],1)

    def test_error_remains_failure_in_denominator_and_unreviewed_is_rejected(self):
        cases=[{'id':'a','group':'text','answerable':True,'gold':[{'page':1}]},
               {'id':'b','group':'unanswerable','answerable':False}]
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp)
            review={'answer_correct':True,'citation_complete':True,'abstention_correct':True,'reason':'Read source','checked_original_pages':[1],'reviewer':'Fixture'}
            write(d/'reviews.json',{'a':review,'b':review})
            for cid,status in [('a','error'),('b','abstain')]:
                write(d/f'{cid}.json',{'status':status,'usage':{'api_cost_usd':0,'prompt_tokens':0,'completion_tokens':0},'elapsed_seconds':0})
            with patch('bonus.benchmark.validate_split',return_value=cases):
                result=summarize(d,'test')
                self.assertEqual((result['passed'],result['total'],result['errors']),(1,2,1))
                reviews=json.loads((d/'reviews.json').read_text());reviews['a']['answer_correct']=None;write(d/'reviews.json',reviews)
                with self.assertRaises(ValueError):summarize(d,'test')

    def test_credit_failure_stops_new_requests_and_resume_preserves_saved_error(self):
        cases=[{'id':'d1','question':'Public question'}]
        record={'id':'p001','page':1,'kind':'page','text':'fact','source':'source.pdf','bbox':[0,0,10,10],'metadata':{}}
        class Client:model='fixture'
        calls=[]
        trial_count=len(json.loads((Path(__file__).resolve().parents[1]/'config/bonus_trials.json').read_text()))
        def fake_run(question,client,retriever,config):
            calls.append(config['name'])
            return {'question':question,'config':config,'status':'error' if len(calls)==1 else 'abstain',
                    'error':'OpenRouter HTTP 402' if len(calls)==1 else '',
                    'citations':[],'usage':{'api_cost_usd':0}}
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/'run'
            figure={**record,'id':'p001-figure-1.1','kind':'figure','label':'1.1','caption':'Fact figure'}
            with patch('bonus.benchmark.validate_split',return_value=cases),patch('bonus.benchmark.load_corpus',return_value=[record,figure]),patch('bonus.benchmark.run',side_effect=fake_run),patch('builtins.print'):
                first=execute('dev',directory,Client(),workers=1)
                saved=(directory/'layout_text/d1.json').read_bytes()
                self.assertEqual((len(calls),first['remaining_unrun'],first['credit_blocked']),(1,trial_count-1,True))
                resumed=execute('dev',directory,Client(),workers=1,resume=True)
                execution=(directory/'execution.json').read_bytes()
                no_op=execute('dev',directory,Client(),workers=1,resume=True)
                self.assertEqual((directory/'execution.json').read_bytes(),execution)
                self.assertEqual(no_op,resumed)
            self.assertEqual(len(calls),trial_count)
            self.assertEqual(resumed['remaining_unrun'],0)
            self.assertEqual(saved,(directory/'layout_text/d1.json').read_bytes())

    def test_quota_failure_stops_before_submitting_more_cases(self):
        class Client:model='fixture'
        cases=[{'id':'d1','question':'Public question'},{'id':'d2','question':'Another question'}]
        for error in ['Gemini HTTP 429: quota exhausted','Gemini HTTP 503: service unavailable','Gemini connection failed or timed out']:
            with self.subTest(error=error),tempfile.TemporaryDirectory() as temp:
                trace={'status':'error','error':error,'usage':{'api_cost_usd':None}}
                with patch('bonus.benchmark.validate_split',return_value=cases),patch('bonus.benchmark.Retriever'),patch('bonus.benchmark.load_corpus'),patch('bonus.benchmark.run',return_value=trace) as call,patch('builtins.print'):
                    result=execute('dev',Path(temp)/'run',Client(),workers=1)
                self.assertEqual(call.call_count,1)
                self.assertTrue(result['provider_blocked'])
                self.assertFalse(result['credit_blocked'])
                self.assertGreater(result['remaining_unrun'],0)

    def test_parallel_inspections_fulfil_all_call_ids_before_images(self):
        records={f'p{n:03d}':{'id':f'p{n:03d}','page':n,'kind':'page','text':f'Fact {n}',
                            'source':'source.pdf','bbox':[0,0,10,10],'metadata':{}} for n in [1,2]}
        class Search:
            by_id=records
            def search(self,q,k):return [records['p001']]
            def expand(self,rows):return rows
        class Client:
            model='fixture'
            def __init__(self):self.requests=[]
            def complete(self,messages,tools,tool_choice):
                self.requests.append(json.loads(json.dumps(messages)))
                turn=len(self.requests)
                ops=[('search',{'query':'fact'},'s1')] if turn==1 else [
                    ('inspect_pages',{'pages':[1]},'i1'),('inspect_pages',{'pages':[2]},'i2')] if turn==2 else [
                    ('finish',{'status':'answered','claims':[{'text':'Two facts','supports':[{'evidence_id':cid,'mode':'image','quote':''} for cid in ['p001','p002']]}],'abstention_reason':''},'f1')]
                calls=[{'id':cid,'type':'function','function':{'name':name,'arguments':json.dumps(args)}} for name,args,cid in ops]
                return {'message':{'role':'assistant','content':None,'tool_calls':calls},'usage':{'cost':0}}
        config={'vision':True,'max_searches':1,'max_inspections':2,'top_k':1,'context_budget_chars':1000,'max_images':2,'image_width':1600}
        client=Client();root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root/'.cache/bonus') as temp:
            p=Path(temp)/'fixture.jpg';p.write_bytes(b'fixture')
            with patch('bonus.agent.page_image',return_value=p):result=run('Question',client,Search(),config)
        self.assertEqual(result['status'],'answered')
        self.assertEqual(result['inspection_calls'],2)
        self.assertEqual(result['citations'],['p001','p002'])
        request=client.requests[-1]
        index=next(i for i,m in enumerate(request) if m.get('tool_calls') and len(m['tool_calls'])==2)
        self.assertEqual([m.get('tool_call_id') for m in request[index+1:index+3]],['i1','i2'])
        self.assertEqual(request[index+3]['role'],'user')
        self.assertEqual(sum(p['type']=='image_url' for p in request[index+3]['content']),2)

    def test_tool_batch_over_budget_is_rejected_before_execution(self):
        record={'id':'p001','page':1,'kind':'page','text':'Fact','source':'source.pdf','bbox':[0,0,10,10],'metadata':{}}
        class Search:
            by_id={'p001':record}
            def search(self,q,k):return [record]
            def expand(self,rows):return rows
        class Client:
            model='fixture'
            def __init__(self):self.turn=0
            def complete(self,messages,tools,tool_choice):
                self.turn+=1
                calls=[{'id':'s','function':{'name':'search','arguments':'{"query":"fact"}'}}] if self.turn==1 else [
                    {'id':str(i),'function':{'name':'inspect_pages','arguments':'{"pages":[1]}'}} for i in range(3)]
                return {'message':{'role':'assistant','content':None,'tool_calls':calls},'usage':{'cost':0}}
        config={'vision':False,'max_searches':1,'max_inspections':2,'top_k':1,'context_budget_chars':1000,'max_images':2,'image_width':1600}
        result=run('Question',Client(),Search(),config)
        self.assertEqual(result['status'],'error')
        self.assertEqual(result['inspection_calls'],0)

    def test_caption_crop_keeps_legend_until_source_in_correct_column(self):
        row={'id':'p001-figure-1.1','kind':'figure','bbox':[0,0,612,792],
             'caption_bbox':[70,100,240,115]}
        lines=[{'text':'Source: wrong right-hand figure','bbox':[350,180,570,190]},
               {'text':'Female Male','bbox':[80,360,250,370]},
               {'text':'Source: actual figure','bbox':[40,400,280,410]},
               {'text':'Figure 1.2. Another figure','bbox':[60,500,260,515]}]
        bounds=crop_bounds(row,lines)
        self.assertLess(bounds[0],70)
        self.assertGreater(bounds[2],280)
        self.assertLess(bounds[2],350)
        self.assertLess(bounds[1],100)
        self.assertGreater(bounds[3],410)
        self.assertLess(bounds[3],500)

    def test_crop_preserves_full_width_and_falls_back_for_unlocalized_pages(self):
        row={'kind':'figure','bbox':[0,0,612,792],'caption_bbox':[200,100,410,115]}
        bounds=crop_bounds(row,[{'text':'Source: chart','bbox':[40,700,300,710]}])
        self.assertLess(bounds[0],40)
        self.assertGreater(bounds[2],570)
        self.assertGreater(bounds[3],710)
        self.assertEqual(crop_bounds({**row,'kind':'page'},[]),row['bbox'])

    def test_text_witness_must_belong_to_the_cited_source(self):
        rows=[{'id':'p001','page':1,'text':'A unique source fact with a date.'},
              {'id':'p002','page':2,'text':'Unrelated material on a nearby page.'}]
        args={'status':'answered','claims':[{'text':'A fact','supports':[{'evidence_id':'p002','mode':'text','quote':'A unique source fact'}]}],'abstention_reason':''}
        with self.assertRaisesRegex(FinalFormatError,'p001'):validate_witnesses(args,rows,[])
        args['claims'][0]['supports'][0]['evidence_id']='p001'
        normalized=validate_witnesses(args,rows,[])
        self.assertEqual(normalized['claims'][0]['evidence_ids'],['p001'])
        self.assertIn('supports',args['claims'][0])
        args['claims'][0]['supports'][0]['quote']='A paraphrase that is not in the source'
        with self.assertRaises(FinalFormatError):validate_witnesses(args,rows,[])

    def test_escaped_whitespace_in_quotes_still_requires_exact_source_words(self):
        rows=[{'id':'p001','page':1,'text':'Hàng LMIC\n0.012\t15.02 trillion VND'}]
        args={'status':'answered','claims':[{'text':'Value','supports':[{
            'evidence_id':'p001','mode':'text','quote':r'Hàng LMIC\n0.012\t15.02 trillion VND'}]}],'abstention_reason':''}
        self.assertEqual(validate_witnesses(args,rows,[])['claims'][0]['evidence_ids'],['p001'])
        for wrong in [r'Hàng LMIC\n0.012\t15.03 trillion VND',r'Hàng LMIC\n...\t15.02 trillion VND']:
            args['claims'][0]['supports'][0]['quote']=wrong
            with self.assertRaises(FinalFormatError):validate_witnesses(args,rows,[])

    def test_search_limit_feedback_allows_one_finish_without_extra_search(self):
        record={'id':'p001','page':1,'kind':'page','text':'The value is 25 units.','bbox':[0,0,10,10]}
        class Search:
            by_id={'p001':record}
            def __init__(self):self.calls=0
            def search(self,q,k):self.calls+=1;return [record]
            def expand(self,rows):return rows
        class Client:
            model='fixture'
            def __init__(self):self.turn=0
            def complete(self,messages,tools,tool_choice):
                self.turn+=1
                name='search' if self.turn<3 else 'finish'
                if self.turn==3:self_choice=tool_choice['function']['name'];assert self_choice=='finish'
                args={'query':'value'} if name=='search' else {'status':'answered','claims':[{
                    'text':'The value is 25 units.','supports':[{'evidence_id':'p001','mode':'text','quote':record['text']}]}],'abstention_reason':''}
                return {'message':{'role':'assistant','content':None,'tool_calls':[{
                    'id':str(self.turn),'function':{'name':name,'arguments':json.dumps(args)}}]},'usage':{'cost':0}}
        config={'vision':False,'max_searches':1,'max_inspections':1,'top_k':1,'context_budget_chars':1000}
        search=Search();result=run('Question',Client(),search,config)
        self.assertEqual(search.calls,1)
        self.assertEqual(result['status'],'answered')
        self.assertEqual(result['protocol_repairs'],1)
        self.assertTrue(any(e['event']=='tool_limit_repair' for e in result['events']))

    def test_image_witness_cannot_claim_unseen_or_different_crop(self):
        rows=[{'id':'p001','page':1,'text':'page'},
              {'id':'p001-figure-1.1','page':1,'text':'figure'}]
        args={'status':'answered','claims':[{'text':'Visual fact','supports':[{'evidence_id':'p001','mode':'image','quote':''}]}],'abstention_reason':''}
        visible=[{'page':1,'evidence_id':'p001-figure-1.1'}]
        with self.assertRaises(FinalFormatError):validate_witnesses(args,rows,visible)
        args['claims'][0]['supports'][0]['evidence_id']='p001-figure-1.1'
        self.assertEqual(validate_witnesses(args,rows,visible)['claims'][0]['evidence_ids'],['p001-figure-1.1'])
        with self.assertRaises(FinalFormatError):validate_witnesses(args,rows,[])

    def test_image_citations_reject_unseen_retired_and_wrong_crop_sources(self):
        rows=[{'id':'p001','page':1},{'id':'p001-figure-1.1','page':1},{'id':'p002','page':2}]
        args={'claims':[{'text':'Visual fact','evidence_ids':['p001-figure-1.1']}]}
        visible=[{'page':1,'evidence_id':'p001-figure-1.1'}]
        normalized=normalize_image_claims(args,rows,visible)
        self.assertEqual(render_claims(normalized,{r['id'] for r in rows})[2],['p001-figure-1.1'])
        self.assertNotIn('status',args)
        self.assertEqual(normalized['claims'],args['claims'])
        for ids,images in [(['p001'],visible),(['p002'],visible),(['unknown'],visible),(['p001-figure-1.1'],[])]:
            invalid={'status':'answered','claims':[{'text':'Visual fact','evidence_ids':ids}]}
            with self.assertRaises(FinalFormatError):normalize_image_claims(invalid,rows,images)
        conflict={**normalized,'status':'abstain','abstention_reason':'Missing evidence'}
        with self.assertRaises(FinalFormatError):render_claims(normalize_image_claims(conflict,rows,visible),{r['id'] for r in rows})
        with self.assertRaises(FinalFormatError):normalize_image_claims({'claims':[]},rows,visible)

    def test_image_protocol_runs_from_shown_source_without_text_quote(self):
        record={'id':'p001','page':1,'kind':'page','text':'Source text.', 'bbox':[0,0,10,10]}
        class Search:
            by_id={'p001':record}
            def search(self,q,k):return [record]
            def expand(self,rows):return rows
        class Client:
            model='fixture'
            def __init__(self):self.turn=0
            def complete(self,messages,tools,tool_choice):
                self.turn+=1
                schema=next(t for t in tools if t['function']['name']=='finish')['function']['parameters']
                assert 'evidence_ids' in schema['properties']['claims']['items']['properties']
                name='search' if self.turn==1 else 'finish'
                args={'query':'source'} if name=='search' else {'claims':[{'text':'The visual value is 25.','evidence_ids':['p001']}]}
                return {'message':{'role':'assistant','content':None,'tool_calls':[{
                    'id':str(self.turn),'function':{'name':name,'arguments':json.dumps(args)}}]},'usage':{'cost':0}}
        config={'vision':True,'image_citations_only':True,'max_searches':1,'max_inspections':1,'top_k':1,
                'context_budget_chars':1000,'max_images':1,'image_width':1600}
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root/'.cache/bonus') as temp:
            image=Path(temp)/'fixture.jpg';image.write_bytes(b'fixture-image')
            with patch('bonus.agent.page_image',return_value=image):result=run('Question',Client(),Search(),config)
        self.assertEqual((result['status'],result['citations']),('answered',['p001']))
        self.assertEqual(result['model_claims'],[{'text':'The visual value is 25.','evidence_ids':['p001']}])
        self.assertTrue(any(e['event']=='final_protocol_normalized' and e['filled_fields']==['abstention_reason','status'] for e in result['events']))

    def test_answer_review_commits_second_answer_and_keeps_first_draft(self):
        record={'id':'p001','page':1,'kind':'page','text':'The value is 25 units.', 'bbox':[0,0,10,10]}
        class Search:
            by_id={'p001':record}
            def search(self,q,k):return [record]
            def expand(self,rows):return rows
        class Client:
            model='fixture'
            def __init__(self,fail_review=False):self.turn=0;self.fail_review=fail_review
            def complete(self,messages,tools,tool_choice):
                self.turn+=1
                if self.turn==3 and self.fail_review:
                    from day07.llm import ProviderError
                    raise ProviderError('OpenRouter HTTP 402')
                name='search' if self.turn==1 else 'finish'
                args={'query':'value'} if self.turn==1 else {'status':'answered','claims':[{
                    'text':'Draft says 20 units.' if self.turn==2 else 'Corrected to 25 units.',
                    'supports':[{'evidence_id':'p001','mode':'text','quote':'The value is 25 units.'}]}],'abstention_reason':''}
                return {'message':{'role':'assistant','content':None,'tool_calls':[{
                    'id':f'c{self.turn}','function':{'name':name,'arguments':json.dumps(args)}}]},'usage':{'cost':0}}
        config={'vision':False,'verify_answer':True,'max_searches':1,'max_inspections':1,'top_k':1,'context_budget_chars':1000}
        result=run('Question',Client(),Search(),config)
        self.assertEqual(result['status'],'answered')
        self.assertIn('25 units',result['answer'])
        self.assertEqual(sum(e['event']=='answer_draft' for e in result['events']),1)
        failed=run('Question',Client(fail_review=True),Search(),config)
        self.assertEqual(failed['status'],'error')
        self.assertEqual(failed['answer'],'')

if __name__=='__main__':unittest.main()
