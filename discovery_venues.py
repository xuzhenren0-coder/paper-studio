"""Auditable starting selection, based on society/publisher scope; no quartile claims."""
import re

VERSION='2026-11-03.1'
IEEE_IDS='https://open.ieee.org/wp-content/uploads/IEEE-Title-List-August-2024-Rev.pdf'
VENUES=[
 {'id':'vsd','name':'Vehicle System Dynamics','issns':['0042-3114','1744-5159'],'publisher':'Taylor & Francis','url':'https://www.tandfonline.com/action/journalInformation?journalCode=nvsd20&show=aimsScope','scope':'车辆动力学、运动与力控制、轮胎、建模与试验','identity_url':'https://www.tandfonline.com/action/journalInformation?journalCode=nvsd20'},
 {'id':'tvt','name':'IEEE Transactions on Vehicular Technology','issns':['0018-9545','1939-9359'],'publisher':'IEEE','url':'https://vtsociety.org/publication/ieee-transactions-vehicular-technology','scope':'车辆电气电子与车载系统；仍需核对具体主题','identity_url':IEEE_IDS},
 {'id':'tits','name':'IEEE Transactions on Intelligent Transportation Systems','issns':['1524-9050','1558-0016'],'publisher':'IEEE','url':'https://ieee-itss.org/pub/t-its/','scope':'智能交通感知、通信、控制、规划与评价','identity_url':IEEE_IDS},
 {'id':'tiv','name':'IEEE Transactions on Intelligent Vehicles','issns':['2379-8858','2379-8904'],'publisher':'IEEE','url':'https://ieee-itss.org/pub/t-iv/','scope':'自动驾驶、辅助驾驶、车辆控制、安全与信息融合','identity_url':IEEE_IDS},
 {'id':'tcst','name':'IEEE Transactions on Control Systems Technology','issns':['1063-6536','1558-0865'],'publisher':'IEEE','url':'https://www.ieeecss.org/publication/transactions-control-systems-technology','scope':'控制系统设计、实现、仿真与硬件','identity_url':IEEE_IDS},
 {'id':'cep','name':'Control Engineering Practice','issns':['0967-0661','1873-6939'],'publisher':'Elsevier / IFAC','url':'https://ifac-control.org/publications/','scope':'控制理论与支撑技术的工业实际应用','identity_url':'https://portal.issn.org/resource/ISSN/1873-6939'}
]
def normalized(value):return re.sub(r'[^a-z0-9]','',str(value).casefold())
def match_venue(row):
    ids={str(x).upper() for x in row.get('issns',[])}
    for venue in VENUES:
        # A conflicting ISSN must never be overridden by a similar venue title.
        if ids.intersection(venue['issns']) or (not ids and normalized(row.get('source',''))==normalized(venue['name'])):return venue
    return None
def annotate(row):
    row=dict(row);v=match_venue(row)
    if row.get('reason'):row['reason']=row['reason'].replace('；来源与摘要需进一步核对，不代表质量评级。','')
    row['venue']=dict(v,verified_at='2026-11-03',version=VERSION) if v else None
    row['source_status']='已匹配精选来源' if v else '未列入精选来源'
    if v:row['source']=v['name'];row['publisher']=v['publisher']
    row['official_url']='https://doi.org/'+row['doi'] if row.get('doi') else row.get('landing_url','')
    return row
def catalog():
    return {'version':VERSION,'verified_at':'2026-11-03','venues':VENUES,'basis':'按车辆动力学、智能车辆和控制领域的官方办刊范围建立起始清单；不是SCI分区、影响因子或逐篇质量认证。ISSN用于准确识别出处。未列入不等于质量差。',
      'conferences':[{'name':'IEEE Intelligent Vehicles Symposium (IV)','url':'https://ieee-itss.org/conf/iv/'},{'name':'IEEE International Conference on Intelligent Transportation Systems (ITSC)','url':'https://ieee-itss.org/conf/itsc/'}],
      'conference_notice':'这两个会议提供官网入口；尚未核验每届论文集标识，暂未混入自动精选结果。'}
