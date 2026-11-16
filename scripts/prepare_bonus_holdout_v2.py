"""Freeze replacement holdout after v1 exposure; never overwrite v1 or v2."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bonus.corpus import ROOT, DATA, SHA, URL, digest, load_corpus, write


def main():
    target=ROOT/'data/bonus-v2'
    if target.exists():raise SystemExit('Refuse to overwrite replacement holdout')
    corpus={r['id']:r for r in load_corpus()}
    def g(cid,region,facts):
        r=corpus[cid]
        return {'id':cid,'page':r['page'],'source':URL,'source_sha256':SHA,'bbox':r['bbox'],
                'caption_bbox':r.get('caption_bbox'),'region':region,'verified_facts':facts,
                'verification':'AI-assisted direct inspection of original PDF images; student independent review pending'}
    def a(n,group,question,answer,*gold,tolerance=None):
        return {'id':f'v2t{n:02d}','split':'test','group':group,'answerable':True,'question':question,
                'expected_answer':answer,'gold':list(gold),'tolerance':tolerance,
                'grading':'Correct AND complete, including units, conditions and arithmetic; every claim cited to supporting original source. Original PDF determines grade.'}
    def u(n,question,reason,terms,pages):
        return {'id':f'v2t{n:02d}','split':'test','group':'unanswerable','answerable':False,'question':question,
                'expected_behavior':'search_and_abstain','absence_reason':reason,
                'absence_audit':{'scope':'All 232 physical pages','keyword_matches':{
                    t:[r['page'] for r in corpus.values() if r['kind']=='page' and t.casefold() in r['text'].casefold()] for t in terms},
                    'checked_nearby_original_pages':pages,
                    'method':'Full corpus keyword search and original source inspection; related statistics do not establish the requested value or artifact.'}}
    test=[
        a(1,'table','From Table 1.1, give the UMIC ($5.50/day 2011PPP) poverty rates in 2012 and 2018 and the reduction in percentage points.',
          '40.8% to 23.4%; decrease 17.4 percentage points.',g('p048-table-1.1','UMIC column, 2012 and 2018 rows','40.8;23.4;40.8-23.4=17.4pp')),
        a(2,'table','In panel B of Table 1.3, give the IPL annual total poverty gaps for 2010 and 2020, their monetary reduction, and the price-year/unit.',
          '5.38 to 1.44 trillion 2020 VND annually; decrease 3.94 trillion 2020 VND.',g('p049-table-1.3','Panel B IPL row, 2010/2020 columns and unit header','5.38;1.44;3.94;2020 VND trillion annually')),
        a(3,'table','Using Table 2.1, what were the Central Highlands populations in 2009 and 2019, and the absolute increase?',
          '5,115,135 and 5,842,605 people; increase 727,470 people.',g('p075-table-2.1','Central Highlands row','5,115,135;5,842,605;727,470')),
        a(4,'table','According to Table 4.1, how did Vietnam’s fraction of children under five not stunted change between 2010 and 2020? State the fractions and change in percentage points.',
          '0.773 to 0.762; decline 0.011 probability = 1.1 percentage points.',g('p132-table-4.1','Fraction under five not stunted, Vietnam 2010/2020 columns','0.773;0.762;decline1.1pp')),
        a(5,'table','In Table 7.1, compare the oil-revenue CIT row with the non-oil direct-tax CIT row for 2018. Give both trillion-dong amounts and their difference.',
          'Oil CIT49;non-oil direct-tax CIT202;non-oil higher153trillion dong.',g('p199-table-7.1','CIT under oil revenues and CIT under direct taxes; TRN DONG column','49;202;202-49=153trillion dong')),
        a(6,'table','Using Table 7.2, what are 2018 primary and lower-secondary education expenditures in trillion dong and percent of GDP? Which amount is larger and by how much?',
          'Primary63trillion,1.1%GDP;lower-secondary49trillion,0.9%GDP;primary higher14trillion dong.',g('p200-table-7.2','Primary and Lower secondary rows, both numeric columns','63;1.1%;49;.9%;14trillion dong')),
        a(7,'diagram','Follow the right-hand branches of Figure B.2.4.1: which two boxes split income per adult, and which two boxes further split labor income per adult?',
          'Income per adult branches to labor and non-labor income per adult. Labor income per adult branches to share of occupied adults and labor income per occupied adult.',g('p096-figure-B.2.4.1','Grey income-per-adult box, yellow pair and blue terminal pair','Labor/non-labor per adult;occupied-adult share and labor income per occupied adult')),
        a(8,'diagram','Read Figure B.4.1.1: how many immediate productivity-component branches leave the Human Capital Index root, and which single leaf is attached to the Survival component?',
          'Three branches; Survival to age 5 is the single leaf of the Survival component.',g('p135-figure-B.4.1.1','Root to three component boxes, upper teal branch and leaf','3;survival to age5;not adult survival')),
        a(9,'diagram','In Figure B.6.3.1, list the five leaves connected to Minimum Basic Social Services, keeping them separate from Social Insurance.',
          'Housing;Health Insurance and Health;Education;Clean Water;Information Access.',g('p190-figure-B.6.3.1','Rightmost grey parent and its five vertical leaves','Housing;Health Insurance and Health;Education;Clean Water;Information Access')),
        a(10,'diagram','Read the bottom of Figure B.7.1.1: what is added to Consumer Income to obtain Final Income, is it net of fees, and which two sectors are named?',
          'Add in-kind transfers net of user fees, for health and education.',g('p197-figure-B.7.1.1','Bottom plus arrow and left white box leading to purple Final Income','Add in-kind transfers net of user fees:health;education')),
        a(11,'diagram','In panel b of Figure 8.1, what fairness condition is proposed for social insurance, and where should the equity elements of its financing be shifted?',
          'Ensure social insurance is actuarially fair; shift equity elements to broader-based financing through general revenues.',g('p225-figure-8.1','Panel b insurance arrow and lower-right financing annotation','Actuarially fair;broader-based general-revenue financing')),
        a(12,'chart','Read Figure 2.1: for households whose oldest member is aged 60–69, give the 2010 and 2020 counts and their increase. State the unit and legend colors.',
          '2.5million(teal2010) to4.6million(orange2020);increase2.1million households.',g('p075-figure-2.1','60–69 pair of labelled bars, legend and note','2.5;4.6;2.1million;teal2010/orange2020;oldest member defines age')),
        a(13,'chart','From Figure 2.3, give the 2010 and 2020 counts of households with tertiary education as their maximum level, the increase, and what the education category refers to.',
          '3.0million to4.7million;increase1.7million households;maximum completed education of any household member.',g('p076-figure-2.3','Tertiary labelled bars, legend and note','3.0;4.7;1.7million;maximum education of any member')),
        a(14,'chart','In Figure 2.7, compare medium-skill and low-skill net employment changes during 2015–2020. Give approximate magnitudes, directions, units, and the two legend colors.',
          'Medium-skill orange rises about2.9million workers;low-skill grey falls about3.0million workers. Axis in thousands.',g('p078-figure-2.7','2015–2020 orange and grey bars, zero line, axis and legend','Orange+~2900thousand;grey-~3000thousand'),tolerance='Medium gain2.6–3.2million;low loss2.7–3.3million;signs, units and colors required'),
        a(15,'chart','Using the no-contract bars in Figure 2.8, what share of workers is in agriculture and fishing in 2010 and 2020? Give the change in percentage points and its legend color.',
          'Teal agriculture/fishing56.2% to40.4%;decline15.8percentage points.',g('p079-figure-2.8','Right-hand No contract pair, bottom teal segments with numeric labels','56.2;40.4;decline15.8pp;teal')),
        a(16,'chart','Read panel A of Figure 2.11: compare the approximate mean number of income sources for the poorest and richest deciles. Is the richest decile more diversified on this measure?',
          'Poorest about3.3 sources;richest about2.9 sources;richest less diversified by this measure.',g('p082-figure-2.11','Panel A first/last bars, average-number-of-sources axis, decile labels','Poorest~3.3;richest~2.9;poorest higher'),tolerance='Poorest3.1–3.5,richest2.7–3.1;unit is sources per household, not millions or percent;direction required'),
        a(17,'multi_hop','Combine Tables 4.1 and 4.2 for 2020: give Vietnam’s national, male and female survival rates from age 15 to 60, then the female–male gap in percentage points.',
          'National.867,male.813,female.924;female-minus-male.111=11.1percentage points.',g('p132-table-4.1','Survival age15–60 Vietnam2020 cell','.867'),g('p137-table-4.2','Survival age15–60 male/female2020 cells','.813;.924;11.1pp')),
        a(18,'multi_hop','Compare the 2018 non-oil direct-tax CIT amount in Table 7.1 with Direct Transfers in Table 7.2. Give both amounts and their difference in trillion dong without inferring earmarking.',
          'CIT202trillion versus Direct Transfers40trillion;CIT higher162trillion dong;no earmarking inference.',g('p199-table-7.1','Non-oil Direct taxes > CIT, TRN DONG cell','202'),g('p200-table-7.2','Direct Transfers row','40;202-40=162')),
        a(19,'multi_hop','Use the 2020 UMIC entries in Tables 1.2 and 1.3: give the number of poor and annual total monetary gap, then estimate the annual gap per poor person in million 2020 VND using those rounded table values.',
          '18.3million poor;116.91trillion2020VND annual gap;116.91/18.3≈6.39million2020VND per poor person annually, approximate because counts are rounded.',g('p048-table-1.2','UMIC 2020 number-of-poor cell','18.3million'),g('p049-table-1.3','Panel B UMIC2020 and2020VNDtrillion header','116.91trillion;6.3885millionVND/person/year'),tolerance='Accept6.3–6.5million2020VND per poor person per year;rounded-input approximation, both source amounts and units required'),
        a(20,'multi_hop','Combine section 2.1 on physical page 75 with Box 8.2 on physical page 220: what is the 2020 average household size, how many observations are in the VHLSS expenditure module, and is that module representative at provincial level?',
          '3.7members per household;9,000expenditure-module observations;not representative at provincial level.',g('p075','Bottom-left section2.1paragraph on households2020','3.7members per household'),g('p220','Box8.2continuedfirst numbered shortcoming','9000observations;not representative at provincial level')),
        a(21,'text','According to Box 8.2, what was Vietnam’s 2020 Open Data Inventory rank and denominator, and which two Statistics Law years are contrasted when discussing openness?',
          '91st of187countries;2015law reduced openness compared with2003law.',g('p220','Third numbered statistical-practice shortcoming','91/187;2015versus2003;reduced openness')),
        a(22,'text','In Box 2.4, give the two caveats of the decomposition method: what cannot be distinguished, and why must its poverty-change contributions not be interpreted as causal effects?',
          'Cannot infer returns versus endowments;not a general-equilibrium method, counterfactuals are not equilibrium outcomes, so contributions detect distributional changes rather than causal effects.',g('p096','Second paragraph of continuedBox2.4above diagram','Returns vs endowments not distinguished;not general equilibrium;not causal')),
        a(23,'text','In chapter 7’s education discussion on physical page 200, how are household expenses received by public schools treated, and why are uniforms or books paid to private sellers excluded?',
          'School-received payments are co-payments/effectively a tax reducing net education benefit;private uniforms/books payments go outside public fiscal system and are excluded.',g('p200','Right column lower paragraph on private education spending','School receipts co-payments/tax;private vendor expenses not part of fiscal system')),
        a(24,'text','According to Box 6.3, in what year was MPSARD approved, and to which age group did its proposed phased cash-transfer policy apply?',
          '2017;infants and young children under4.',g('p190','Box6.3paragraph above social-protection tree','2017;under4')),
        u(25,'What exact p-value establishes the causal effect of wage income on poverty reduction in the decomposition of Box 2.4?',
          'No causal p-value reported;Box2.4explicitly warns decomposition contributions are not causal effects.',['p-value','causal effect'],[96]),
        u(26,'Give the complete numerical covariance matrix of the household income components underlying Figure 2.12 for 2020.',
          'Component trends are shown, not their joint covariance matrix or microdata.',['covariance','correlation matrix'],[84]),
        u(27,'Provide the executable software source code implementing the national social-insurance system drawn in Figure 8.1.',
          'Conceptual policy diagram, no executable implementation or software listing.',['source code','executable'],[225]),
        u(28,'Give the exact latitude and longitude of each individual household represented in the clean-water map in Figure 6.5.',
          'Map presents district-level aggregate patterns, no household coordinate list.',['latitude','longitude','GPS'],[179]),
        u(29,'What is the exact 2020 number of disability-adjusted life years caused by PM2.5 for every Vietnamese district in Figure 6.5?',
          'District PM2.5 exposure map does not report district attributable DALYs.',['disability-adjusted','DALY'],[179]),
        u(30,'What exact statutory day, month and year is set as the implementation deadline for the curriculum revision recommended in Table 8.2?',
          'Policy recommendation gives no exact statutory implementation deadline.',['deadline','curricula'],[222]),
    ]
    target.mkdir()
    shutil.copy2(DATA/'dev.json',target/'dev.json')
    write(target/'test.json',test)
    pages=sorted({g['page'] for c in test for g in c.get('gold',[])})
    audit_pages=sorted(set(pages)|{84,179,222})
    # These images were opened directly during authorship, before the new agent
    # experiment. Additional absence-topic pages are checked separately below.
    write(target/'source-audit.json',{'created_utc':datetime.now(timezone.utc).isoformat(),
          'reviewer':'Codex AI-assisted original-PDF inspection; student independent review pending',
          'answerable_source_pages':pages,'images':{str(p):{'path':f'.cache/bonus/p{p:03d}-w1600.jpg',
              'sha256':digest(ROOT/f'.cache/bonus/p{p:03d}-w1600.jpg')} for p in audit_pages},
          'new_test_outputs_observed':False,
          'overlap_policy':'Existing development questions retained. New test targets different facts/branches/rows from dev and old test; same document and some source figures reused. No claim of independent test authorship or equal difficulty across versions.'})
    write(target/'freeze.json',{'created_utc':datetime.now(timezone.utc).isoformat(),
          'version':2,'replaces_exposed_test':'data/bonus/test.json',
          'dev_sha256':digest(target/'dev.json'),'test_sha256':digest(target/'test.json'),
          'corpus_sha256':digest(DATA/'corpus.jsonl'),'corpus_path':'data/bonus/corpus.jsonl',
          'counts':{'dev':dict(Counter(c['group'] for c in json.loads((target/'dev.json').read_text()))),
                    'test':dict(Counter(c['group'] for c in test))},
          'policy':'Replacement test frozen before new dev/API experiments. Old exposed test is historical, never a fresh accuracy claim. Gold/groups/regions stay evaluator-only. Select on dev only; run complete new test once; all errors count as failures.',
          'limitations':'Same-document source-specific evaluation with explicit locators. Test authored by same AI collaborator that fixed generic protocol defects, with no new test outputs. Not an external blind evaluation. Student independent verification pending.'})
    print('Frozen v2: existing18dev + new30test; shared437-record corpus; refuse overwrite')


if __name__=='__main__':main()
