"""Protocol regressions use invented evidence, never benchmark answers."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bonus.agent import run
from bonus.corpus import ROOT


def call(name,args):
    return {'message':{'role':'assistant','content':None,'tool_calls':[
        {'id':name,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]},
        'usage':{'cost':0,'prompt_tokens':1,'completion_tokens':1}}


def finish(cid='p001'):
    return call('finish',{'status':'answered','claims':[{'text':'Invented fixture value is 41 units.',
                'evidence_ids':[cid]}]})


class BonusRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'.cache/bonus').mkdir(parents=True,exist_ok=True)

    def execute(self,responses,**options):
        records={f'p{p:03d}':{'id':f'p{p:03d}','page':p,'kind':'page',
                 'text':f'Invented fixture evidence on page {p}, value 41 units.',
                 'bbox':[0,0,100,100]} for p in [1,2,3]}
        class Retriever:
            by_id=records
            def search(self,q,k):
                page=int(q) if q.isdigit() else 1
                return [records[f'p{page:03d}'],*[r for r in records.values() if r['page']!=page]][:k]
            def expand(self,rows):return rows
        class Client:
            model='fixture'
            def __init__(self):self.requests=[]
            def complete(self,messages,tools,tool_choice):
                self.requests.append({'messages':copy.deepcopy(messages),'choice':tool_choice})
                return copy.deepcopy(responses[len(self.requests)-1])
        config={'vision':True,'image_citations_only':True,'max_searches':3,'max_inspections':2,
                'top_k':3,'context_budget_chars':3000,'max_images':2,'image_width':1600,**options}
        client=Client()
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache/bonus') as temp:
            def image(page,width):
                path=Path(temp)/f'{page}.jpg';path.write_bytes(f'fixture-{page}'.encode());return path
            with patch('bonus.agent.page_image',side_effect=image):
                result=run('Fixture question',client,Retriever(),config)
        return result,client.requests

    def test_plain_answer_requires_model_to_resubmit_supported_finish(self):
        plain={'message':{'role':'assistant','content':'An unsubmitted draft with no accepted citation.'},'usage':{'cost':0}}
        result,requests=self.execute([call('search',{'query':'1'}),plain,finish()])
        self.assertEqual(result['status'],'answered')
        self.assertEqual(result['plain_response_repairs'],1)
        self.assertEqual(requests[-1]['choice']['function']['name'],'finish')
        self.assertNotIn('unsubmitted draft',result['answer'])
        self.assertEqual(result['usage']['llm_calls'],3)
        self.assertIn('unsubmitted draft',json.dumps(result['events']))

    def test_repeated_plain_text_is_error_instead_of_automatic_success(self):
        plain={'message':{'role':'assistant','content':'Cannot find an answer.'},'usage':{'cost':0}}
        result,_=self.execute([call('search',{'query':'1'}),plain,plain])
        self.assertEqual(result['status'],'error')
        self.assertEqual(result['plain_response_repairs'],1)
        self.assertEqual(result['answer'],'')

    def test_missing_image_can_be_inspected_before_revalidated_finish_and_review(self):
        result,requests=self.execute([call('search',{'query':'1'}),finish('p002'),
            call('inspect_pages',{'pages':[2]}),finish('p002'),finish('p002')],verify_answer=True)
        self.assertEqual(result['status'],'answered')
        self.assertEqual(result['missing_image_recoveries'],1)
        self.assertEqual(result['format_repairs'],0)
        self.assertEqual(requests[2]['choice']['function']['name'],'inspect_pages')
        self.assertEqual(result['citations'],['p002'])
        self.assertEqual(result['inspection_calls'],1)
        self.assertTrue(result['answer_reviewed'])

    def test_successive_searches_keep_two_images_but_retire_third(self):
        result,requests=self.execute([call('search',{'query':'1'}),call('search',{'query':'2'}),
            call('search',{'query':'3'}),finish('p002')])
        self.assertEqual(result['status'],'answered')
        self.assertEqual({a['page'] for a in result['visible_image_artifacts']},{2,3})
        for request in requests:
            images=[p for m in request['messages'] if isinstance(m.get('content'),list)
                    for p in m['content'] if p.get('type')=='image_url']
            self.assertLessEqual(len(images),2)
        self.assertEqual(len(result['image_artifacts']),3)

    def test_unknown_source_does_not_trigger_source_inspection_or_get_accepted(self):
        result,requests=self.execute([call('search',{'query':'1'}),finish('unknown'),finish('unknown')])
        self.assertEqual(result['status'],'error')
        self.assertEqual(result['missing_image_recoveries'],0)
        self.assertEqual(result['inspection_calls'],0)
        self.assertEqual(requests[-1]['choice']['function']['name'],'finish')

    def test_missing_image_recovery_cannot_bypass_exhausted_inspection_limit(self):
        result,_=self.execute([call('search',{'query':'1'}),finish('p002'),finish('p002')],max_inspections=0)
        self.assertEqual(result['status'],'error')
        self.assertEqual(result['missing_image_recoveries'],0)
        self.assertEqual(result['inspection_calls'],0)


if __name__=='__main__':unittest.main()
