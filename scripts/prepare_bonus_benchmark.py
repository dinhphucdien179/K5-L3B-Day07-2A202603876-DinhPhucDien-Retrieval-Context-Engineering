"""Author source-checked advanced splits before any agent experiments."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from bonus.corpus import DATA, SHA, URL, digest, load_corpus, write


def main():
    if (DATA/'freeze.json').exists():raise SystemExit('Benchmark frozen; refuse overwrite')
    corpus={r['id']:r for r in load_corpus()}
    def gold(cid,region,facts):
        r=corpus[cid]
        return {'id':cid,'page':r['page'],'source':URL,'source_sha256':SHA,
                'bbox':r['bbox'],'caption_bbox':r.get('caption_bbox'),
                'region':region,'verified_facts':facts,
                'verification':'AI-assisted reading of original rendered PDF and layout text; student verification pending'}
    def a(cid,group,q,answer,*g,tolerance=None):
        return {'id':cid,'group':group,'answerable':True,'question':q,'expected_answer':answer,
                'gold':list(g),'tolerance':tolerance,'grading':'Correct AND complete answer, units/conditions, and citations supporting ALL claims. Original source determines grade.'}
    def u(cid,q,why,terms):
        matches={t:[r['page'] for r in corpus.values() if r['kind']=='page' and t.casefold() in r['text'].casefold()] for t in terms}
        return {'id':cid,'group':'unanswerable','answerable':False,'question':q,
                'expected_behavior':'search_and_abstain','absence_reason':why,
                'absence_audit':{'scope':'All 232 physical pages, not the old 39-page subset',
                                 'keyword_matches':matches,'method':'Whole-corpus keyword search plus source/topic inspection; nearby estimates/projections are not the requested evidence.'}}
    dev=[
      a('bd01','table','In Table 1.3, what is the 2020 LMIC poverty gap as a share of the poverty line, and the corresponding annual monetary gap? Give the units.',
        '0.012 of the line (1.2%); 15.02 trillion 2020 VND annually.',gold('p049-table-1.3','Panel A LMIC row, 2020; panel B LMIC row, 2020','0.012 and 15.02; ratios versus trillion VND')),
      a('bd02','table','Using Table 2.1, give the national census populations in 2009 and 2019 and their absolute increase.',
        '85,801,996 and 96,208,635; increase 10,406,639 people.',gold('p075-table-2.1','National row, 2009 and 2019 columns','85,801,996; 96,208,635; subtract for 10,406,639')),
      a('bd03','table','According to Table 7.2, what were health spending and its GDP share in 2018, and the in-patient/out-patient amounts?',
        'Health 89 trillion dong, 1.6% GDP; in-patient 43 and out-patient 46 trillion dong.',gold('p200-table-7.2','Health row and two indented subrows','89; 1.6%; 43; 46')),
      a('bd04','diagram','Read the three maps in Figure 1.7. Which years do they compare, what does the shared color scale measure, and does the dark high-poverty area generally expand or contract?',
        '2009, 2015, 2019; poverty rate (%), darker green higher; high-poverty area generally contracts.',gold('p052-figure-1.7','Three map panels, year labels and shared 0–100% legend','2009/2015/2019; poverty percent; dark concentration shrinks')),
      a('bd05','diagram','Which two regions are zoomed in Figure 3.9, and does orange or blue indicate higher poverty on its legend?',
        'Midlands and Northern Mountains; Central Highlands. Orange is higher poverty, blue lower.',gold('p107-figure-3.9','Two map titles and shared poverty-rate color legend','Midlands & Northern Mountains, Central Highlands; orange high, blue low')),
      a('bd06','diagram','In the top row of Figure 6.5, compare the temperature and PM2.5 maps: where are high temperatures concentrated and where is high air pollution concentrated?',
        'Higher temperature in the south; air pollution concentrated in the Red River Delta (northern area).',gold('p179-figure-6.5','Top-left temperature and top-middle PM2.5 maps, legends; paragraph above','Warm colors high; south temperature, Red River Delta air pollution')),
      a('bd07','chart','From Figure 4.8, how does school attendance change from ages 10–14 to 20–24 for both genders, and which gender is slightly higher at 20–24?',
        'Falls from near universal to roughly a quarter for both; men slightly higher at 20–24.',gold('p137-figure-4.8','Three age groups, female/male legend and vertical attendance-percent axis','Near 100% -> around25%; male slightly above female in20–24'),tolerance='At final age group accept 20–30%; approximate reading, no exact decimals required'),
      a('bd08','chart','Compare the agriculture/fishing and manufacturing panels in Figure 5.11 between 2010 and 2020. Which sector loses workers and which gains, and what skill color dominates agriculture?',
        'Agriculture/fishing loses workers, manufacturing gains; unskilled manual (yellow) dominates agriculture.',gold('p161-figure-5.11','Two stacked-bar panels and four-color skill legend','Agriculture ~24m->17m; manufacturing ~7m->11m; yellow unskilled manual')),
      a('bd09','chart','Using Figure 6.3, compare the direction of Vietnam and the lower-middle-income group in out-of-pocket health spending from 2010 to 2018. Give Vietnam’s approximate endpoints and units.',
        'Vietnam rises about37% to45% of total health expenditure; LMIC group falls.',gold('p177-figure-6.3','Green Vietnam line, orange LMIC line; share of total health expenditure axis','Vietnam37 to45; LMIC roughly57to51'),tolerance='Vietnam endpoints within 2 percentage points; correct direction and denominator required'),
      a('bd10','multi_hop','Combine Tables 1.1 and 1.3: what are the 2020 LMIC headcount poverty rate and average poverty-gap share, and why are these not the same statistic?',
        'Headcount5.0% of people versus poverty gap0.012=1.2% of poverty line averaged across population; prevalence versus average shortfall.',
        gold('p048-table-1.1','2020 row, LMIC column','Headcount5.0%'),gold('p049-table-1.3','Panel A 2020 LMIC and explanatory paragraph above','Average gap1.2% of line; not headcount')),
      a('bd11','multi_hop','Use Tables 4.1 and 4.2 to give the 2020 national, male and female probabilities of surviving to age five, and calculate the female–male difference in percentage points.',
        'National0.979, male0.976, female0.983; female minus male0.007 probability=0.7 percentage points.',
        gold('p132-table-4.1','Vietnam 2020 survival-to-age5 cell','0.979'),gold('p137-table-4.2','Survival-to-age5 male/female2020 cells','Male0.976; female0.983;0.7pp difference')),
      a('bd12','multi_hop','Compare total 2018 revenues and grants in Table 7.1 with total expenditures in Table 7.2. Which is larger and by how many trillion dong? Do not infer a national fiscal balance from these differently scoped tables.',
        'Revenues/grants1,364; total expenditures1,435 trillion dong; expenditures71trillion higher in these tables, scope caveat.',
        gold('p199-table-7.1','Total revenues & grants row','1,364 trillion dong'),gold('p200-table-7.2','Total expenditures row and title central government','1,435trillion; difference71; scopes differ')),
      a('bd13','text','In Box 2.1, when did Vietnam join the WTO, and to what share of GDP had exports of goods and services risen by 2019?',
        'January2007;106% of GDP in2019.',gold('p081','Box2.1 continued, upper left paragraph','January2007; exports106% of GDP2019')),
      a('bd14','text','What share of households reported a negative shock between February and June 2020, and which first nationwide lockdown month is identified in section 6.2?',
        'Almost70%; April2020.',gold('p178','Left column Shocks experienced by households during COVID-19, first paragraph','Almost70%; February–June2020; lockdownApril2020')),
      a('bd15','text','In section 8.2, how does Vietnam’s higher-education gross enrollment rate compare with 30 percent and with East Asian peers?',
        'Below30%, among the lowest in East Asia.',gold('p221','Bottom-right paragraph Continuing improvements in higher education access and quality','GER below30%;one of lowest East Asian')),
      u('bd16','What was Vietnam’s observed national child stunting rate measured in a survey conducted in 2028?','A2022 publication cannot provide observed2028 survey results.',['2028','stunting']),
      u('bd17','Give the exact 2020 VHLSS income and sampling weight of respondent household BONUS-HH-814209.','Published aggregates, no identified household-level record.',['BONUS-HH-814209']),
      u('bd18','What are the lower and upper 95% confidence bounds for Vietnam’s 2020 HCI value in Table 4.1?','Point estimate0.69 is supplied, requested confidence interval is absent.',['confidence','0.69']),
    ]
    test=[
      a('bt01','table','From Table 1.1, give Vietnam’s extreme-poverty rates at the $1.90/day 2011PPP line in 2010 and 2020 and the percentage-point reduction.',
        '4.0% in2010,1.0% in2020; reduction3.0percentage points.',gold('p048-table-1.1','IPL $1.90 column,2010 and2020 rows','4.0;1.0;subtract3.0pp')),
      a('bt02','table','Which two 2011 dong-to-dollar conversion rates are shown in Table A.1.2.1, and which is the purchasing-power-parity rate?',
        'PPP7,528.385VND per international dollar; period-average exchange rate20,509.75VND/US$1.',gold('p069-table-A.1.2.1','Two conversion-rate rows and unit header','PPP7,528.385;exchange20,509.75;units VND per dollar')),
      a('bt03','table','Using Table 4.1, how did Vietnam’s expected years of school change from 2010 to 2020? Give both values and the increase.',
        '11.8 to12.9years; increase1.1years.',gold('p132-table-4.1','Expected Years of School row, Vietnam2010/2020 columns','11.8;12.9;increase1.1')),
      a('bt04','table','What are the female and male 2020 HCI values in Table 4.2, and the female-minus-male index gap?',
        'Female0.73, male0.65;gap0.08 index points.',gold('p137-table-4.2','Human Capital Index row;2020 female/male columns','0.73;0.65;0.08 index points, not8index points')),
      a('bt05','table','According to Table A.5.1.1, how are professionals classified by skill, and what education level and ISCED codes are expected?',
        'High-skilled non-manual; tertiary education,ISCED5–6.',gold('p170-table-A.5.1.1','Occupation2 professionals, merged high-skilled non-manual/tertiary cells spanninggroups1–3','High-skilled non-manual;tertiaryISCED5–6')),
      a('bt06','table','In Table 7.1, what are 2018 personal income tax revenues in trillion dong and as a percentage of GDP?',
        '94trillion dong;1.7%GDP.',gold('p199-table-7.1','PIT row below direct taxes, both numeric columns','94;1.7%')),
      a('bt07','diagram','Read the branches of Figure B.2.4.1. Which two factors form household consumption per capita, and which two factors form household income per capita?',
        'Consumption per capita = propensity to consume × household income per capita. Household income per capita = share of adults × income per adult.',gold('p096-figure-B.2.4.1','First two branch levels of decomposition tree, left to right','Propensity×HHincomepercap;shareadults×incomeperadult')),
      a('bt08','diagram','In Figure B.4.1.1, which two leaf indicators feed the contribution to productivity from school, and which two feed the health component?',
        'School:expected years of schooling,harmonized test scores. Health:adult survival rate,not-stunted rate.',gold('p135-figure-B.4.1.1','School and Health branches on right side of HCI tree','School expectedyears+testscores;health adultsurvival+notstunted')),
      a('bt09','diagram','In the tree in Figure B.6.3.1, name the three branches directly under Social Assistance and the three under Social Insurance.',
        'Assistance:regular allowances,social care centers and care services,emergency assistance. Insurance:unemployment insurance,compulsory and voluntary insurance,other programs(supplement SI).',gold('p190-figure-B.6.3.1','First two main columns and their three leaves each','Assistance and insurance each3 distinct child boxes; do not swap emergency andunemployment')),
      a('bt10','diagram','Follow Figure B.7.1.1 from market income plus pensions to disposable income: what is subtracted to obtain net market income, and what is then added to obtain disposable income?',
        'Subtract direct taxes(PIT,property tax,border tax); then add direct cash transfers.',gold('p197-figure-B.7.1.1','Central flow from pre-fiscal income through net market income to disposable income; minus/plus side boxes','Minusdirecttaxes thenplusdirectcashtransfers')),
      a('bt11','diagram','Compare panels a and c of Figure 8.1. Which gap in social protection is removed in c, and what does its annotation recommend for assistance and subsidies at the top of the income distribution?',
        'Closes coverage/missing-middle gap between narrowly targeted assistance and insurance; taper assistance/subsidies away from top through tax systems.',gold('p225-figure-8.1','Panel a gap, panel c continuous coverage and top annotation','Missing-middle gapfilled; taperassistance/subsidies at top via taxsystems')),
      a('bt12','chart','Read Figure 2.10 from the poorest to the richest household decile. How do the family-farm and family-business shares of household income change? Refer to both legend colors.',
        'Family farm(teal/green)decreases;family business(orange)increases asdecile rises.',gold('p081-figure-2.10','Stacked bars deciles1–10, green familyfarm/orange familybusiness legend','Farmsharefalls roughly35to8%;businessrises roughly7to30%')),
      a('bt13','chart','Using Figure 4.17, estimate extra-class participation for top and bottom wealth quintiles at age 12 and the gap in percentage points. Is the gap larger than at age 8?',
        'Age12topabout85%,bottomabout30%,gapabout55pp; largerthan age8gapabout30pp.',gold('p145-figure-4.17','Age8and12 paired bars,top/bottomlegend,percentaxis','Age12~85and30;gap~55;age8~78and47 gap~31'),tolerance='Allow ±5 percentage points per bar and ±8 pp for gap; must identify larger gap at12'),
      a('bt14','chart','Read Figure 5.4: which 2045 projected GDP-per-capita path is higher, the baseline or the HIC path? Estimate each value to the nearest thousand and state the price-year/currency unit.',
        'HIC higher;baselineaboutUS$10,000,HICaboutUS$14,000;GDPpercapita constant2018US$.',gold('p157-figure-5.4','Two dashed arrows ending at2045,legend,y-axisunit andnotenextline','Baseline~10k,HIC~14k;constant2018US$'),tolerance='Accept baseline9–11thousand andHIC13–15thousand; must say constant2018US$'),
      a('bt15','chart','In Figure 5.7, how does the projected working-age population share move after 2018 toward 2050, and what line style distinguishes the projection from historical data?',
        'Declines fromhigh60s towardmid60percent;futuresegmentdashed versus historicalsolid.',gold('p159-figure-5.7','GreenWorkingage line;solidtill2018,dashedprojected2020–2050;percentaxis','Workingagesharefalls;solid->dashed projection')),
      a('bt16','chart','In Figure 6.12, which bar has the lowest social-assistance benefit level and which has the highest? Estimate both as shares of welfare among the lowest quintile.',
        'Vietnam lowestabout6%;UMIC highestabout22%.',gold('p190-figure-6.12','Sixbars,country/income-group labels,y-axis shareofwelfareamonglowestquintile','Vietnam~6;UMIC~22'),tolerance='Vietnam4–8%,UMIC20–24%; correct denominator andranking'),
      a('bt17','multi_hop','Use Tables 4.1 and 4.2 to compare 2020 harmonized-test-score gaps: Vietnam minus East Asia and Pacific, and Vietnamese females minus males. Give all four scores and both point gaps.',
        'Vietnam519,EAP432,gap87;females524,males514,gap10 test-scorepoints.',gold('p132-table-4.1','Harmonizedtestscores Vietnam2020/EAP2020','519and432,gap87'),gold('p137-table-4.2','Harmonizedtestscore female2020/male2020','524and514,gap10')),
      a('bt18','multi_hop','Compare VAT revenue in Table 7.1 with education spending in Table 7.2 for 2018. Give both trillion-dong amounts and their difference, without claiming the VAT was earmarked for education.',
        'VAT344trillion;education220trillion;VAT124trillionhigher;notanearmarkingclaim.',gold('p199-table-7.1','VATrow underTaxesongoods/services','344trillion'),gold('p200-table-7.2','Educationrow','220trillion;difference124')),
      a('bt19','multi_hop','Combine section 4.2 across physical PDF pages 132–133: what are Vietnam’s expected school years and learning-adjusted years, how many years is the difference, and what does the adjustment account for?',
        'Expected12.9years;learning-adjusted10.7;difference2.2years;adjustsquantityfor educationquality proxiedby standardized/harmonizedtestscores.',gold('p132','Section4.2rightcolumn:12.9expected,10.7beginningofsentenceatbottom','12.9and10.7'),gold('p133','Continuationtop-leftdefining learning-adjustedyearsofschooling','Adjustmentreflectsqualityvia test scores;2.2difference')),
      a('bt20','multi_hop','Combine Table 2.1 and the PM2.5 map in Figure 6.5: which region gained the most population between 2009 and 2019, and is it the same region identified as having concentrated high air pollution? Name both.',
        'Southeastlargestpopulationgain;highairpollutionconcentratedinRedRiverDelta;differentregions.',gold('p075-table-2.1','Regional2009/2019counts;paragraphleftabove','Southeast+3,761,457largest'),gold('p179-figure-6.5','TopmiddlePM2.5mapandparagraphabove','AirpollutionRedRiverDelta,nottheSoutheast')),
      a('bt21','text','According to section 4.2, what was Vietnam’s 2020 under-five mortality rate? State its denominator rather than confusing it with a percentage.',
        '21deathsper1,000livebirths(2.1%).',gold('p133','RightcolumnparagraphImprovingaccesstomaternalhealthcare','21deathsper1,000livebirths2020')),
      a('bt22','text','Under the worst-case climate-change scenario discussed in section 6.2, what sea-level rises are projected for 2050 and 2100?',
        '30cm (0.3m) by2050;70cm (0.7m) by2100;worst-case scenario,not observations.',gold('p178','Bottom-rightparagraphClimatechangeisexpectedtoexacerbateexistingrisks','30cm and70cm by2050/2100respectively')),
      a('bt23','text','What subnational social spending is excluded from the chapter 7 fiscal analysis because of data limitations, and which two sectors include both central and local expenditures?',
        'Important subnational/local socialassistancespending excluded;healthandeducation include both centralandlocalspending.',gold('p199','RightcolumnExpendituresfirstparagraph','Localsocialassistanceexcluded;central+localhealth/educationincluded')),
      a('bt24','text','Which three demographic trends does section 8.2 cite when explaining the need for broad-based human-capital investment?',
        'Decliningfertility,risinglifeexpectancy,shrinkingworking-agepopulation.',gold('p221','LeftcolumnEquitablehumancapitalformationparagraph','Fertilitydown,lifeexpectancyup,workingagepopulationshrinks')),
      u('bt25','What exact national population did a census conducted in calendar year 2026 observe for Vietnam?','2022report includesearliercensuses/projections,notanobserved2026census.',['2026','Census']),
      u('bt26','What was the observed 2027 out-of-pocket health spending share from Vietnam’s 2027 national accounts?','Noobserved2027nationalaccountsinthe2022report.',['2027','out-of-pocket']),
      u('bt27','What are the exact household-level income and sample weight for VHLSS respondent BONUS-HH-993577?','NorecordforinventedIDorrespondentmicrodatainthepublication.',['BONUS-HH-993577']),
      u('bt28','What are the lower and upper limits of the 95% confidence interval for the female 2020 HCI in Table 4.2?','Table4.2haspointestimates,noconfidenceboundsforthisvalue.',['confidence','0.73']),
      u('bt29','What is the exact standard error of the 2020 national poverty rate at the $1.90/day line in Table 1.1?','Headcountrateispresent,butitsstandarderrorisnotreportedinthetableorelsewhere.',['standard error','1.90']),
      u('bt30','According to this Vietnam report, what was Sydney’s district-level mean PM2.5 concentration in 2020?','Figure6.5showsVietnamdistricts,notSydney;nomatching2020citymeasurement.',['Sydney','PM2.5']),
    ]
    for split,items in [('dev',dev),('test',test)]:
        for item in items:item['split']=split
        write(DATA/f'{split}.json',items)
    write(DATA/'freeze.json',{'created_utc':datetime.now(timezone.utc).isoformat(),
        'dev_sha256':digest(DATA/'dev.json'),'test_sha256':digest(DATA/'test.json'),
        'corpus_sha256':digest(DATA/'corpus.jsonl'),
        'counts':{'dev':dict(Counter(c['group'] for c in dev)),'test':dict(Counter(c['group'] for c in test))},
        'policy':'Authored/frozen before agent experiments. Gold, group and expected answers never enter runtime. Select only on dev; test is single final evaluation, errors remain failures.',
        'limits':'Document-specific benchmark, many explicit Table/Figure locators; not an open-domain generalization claim. Dev maps count as substantive images. Test diagram group has five distinct conceptual diagrams.'})
    print('Frozen 18 dev (15 answerable+3 absent), 30 test (24 answerable+6 absent)')

if __name__=='__main__':main()
