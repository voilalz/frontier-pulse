"""Authored offline translations, never presented as live model output."""
import copy
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import update_news as news
from deepread_editorial import build_daily_deepread

ZH = {
 'ai-1': ('前沿实验室发布更高效的多模态模型', '此次发布着重降低推理成本，支持结构化输出，并开展模型安全评估。'),
 'ai-2': ('新半导体设计面向边缘人工智能推理', '芯片结合较低功耗与设备端模型执行能力，面向工业系统应用。'),
 'ai-3': ('研究人员发布更新的人工智能安全基准', '该基准评估模型抵御滥用的能力、不确定性以及跨语言的稳健性。'),
 'space-1': ('美国航天局发射空间天气观测卫星', '航天器将监测太阳活动，改善面向卫星和电网的预警能力。'),
 'space-2': ('商业火箭完成可复用上面级测试', '测试旨在降低发射成本，并提高执行航天任务的频率。'),
 'space-3': ('欧洲机构就月球技术演示项目达成协议', '项目将验证月球附近的自主导航与通信技术。'),
 'mil-1': ('国防部门签署雷达现代化合同', '合同包括数字雷达升级、具备韧性的联网能力和操作员培训。'),
 'mil-2': ('北约在演习中测试分布式指挥网络', '演习评估跨多个领域的数据共享与通信韧性。'),
 'conflict-1': ('地区无人机袭击后停火谈判恢复', '谈判代表重返会谈，官员同时评估近期袭击的影响。'),
 'conflict-2': ('乌克兰报告应对远程无人攻击的新措施', '措施结合防空、电子战与基础设施保护方式的调整。'),
 'frontier-1': ('量子网络测试连接三个城市节点', '研究人员在实地网络中演示纠缠分发，并公布误差数据。'),
 'frontier-2': ('核聚变项目报告磁体寿命改善', '结果涉及持续高磁场运行的一项工程约束。'),
 'frontier-3': ('美国国防高级研究计划局启动材料生产项目', '项目寻求加快高温材料的资格确认，并实现可扩展生产。'),
 'uas-1': ('自主飞机完成受监督的编队测试', '三架无人飞机共享导航与任务更新，同时由人类保留授权权力。'),
 'uas-2': ('反无人机系统在实地试验后进入生产', '系统结合被动探测、电子防护与用于固定场所的拦截装置。'),
 'uas-3': ('港口运营商部署自主巡检车辆', '无人车辆巡检限制进入的区域，并向人类控制中心传输传感器数据。'),
}


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def translated_record(key, record):
    key = fixture_key(key)
    title, detail = ZH[key]
    if 'technical report' in record['text']:
        return title + '，据技术报告，已完成的工作与计划开展的后续评估分别记录，可据此区分当前结果与后续安排。'
    if 'reported measurements' in record['text']:
        return title + '，报告所列测量结果将用于项目下一次受控演示，为后续的试验安排提供测量依据。'
    return title + '，' + detail


def translate_item(item):
    item = copy.deepcopy(item)
    title, _ = ZH[fixture_key(item['id'])]
    paragraphs = [translated_record(item['id'], r) for r in item['evidenceRecords'] if r['evidenceId'] in item['summaryEvidenceRefs']]
    item['displayTranslation'] = {'version': 1, 'language': 'zh-CN', 'provider': 'deepseek',
        'title': title, 'summary': ''.join(paragraphs), 'sourceTitle': item['originalTitle'],
        'sourceSummary': item['summary'], 'sourceEvidenceRefs': item['summaryEvidenceRefs']}
    item['translationProvider'] = 'deepseek'
    return item


def fixture_key(value):
    return next((key for key in ZH if value == key or value.endswith('-'+key)), value)


def full_deep(items, edition):
    now = datetime.fromisoformat(edition).replace(tzinfo=timezone.utc)
    tech = [copy.deepcopy(i) for i in items if i['category'] in {'AI', '航空航天', '前沿技术', '无人系统'}][:4]
    for item in tech:
        item['publishedAt'] = (now - timedelta(hours=1)).isoformat()
    def provider(runtime, **kwargs):
        material = json.loads(kwargs['input_text'])
        if kwargs['schema_name'] == 'deepread_outline_v2':
            ids = material['fixedSelectedNewsIds']
            return {'selectedNewsIds': ids, 'chapters': [
                {'title': ZH[fixture_key(key)][0],
                 'angle': '追踪本次报道中的具体变化', 'newsIds':[key], 'kind':'event', 'comparisonKey':''}
                for key in ids]}
        if kwargs['schema_name'] != 'deepread_prose_v2':
            raise AssertionError('Unexpected provider operation ' + kwargs['schema_name'])
        by_id = {item['newsId']:item for item in material['events']}
        chapters = {}
        for chapter in material['outline']:
            blocks = []
            for key in chapter['newsIds']:
                for record in by_id[key]['evidenceRecords'][1:3]:
                    blocks.append({'type':'paragraph', 'text':translated_record(key, record),
                        'sourceText':record['text'], 'newsIds':[key], 'evidenceIds':[record['evidenceId']]})
            chapters[chapter['id']] = {'blocks': blocks}
        observations = []
        for event in material['events'][:2]:
            record = event['evidenceRecords'][1]
            quote = record['text'][:220]
            # Fixture second paragraphs are short enough to preserve the full sentence.
            if quote != record['text']:
                record = event['evidenceRecords'][0]
                quote = record['text']
            observations.append({'text': translated_record(event['newsId'], record), 'sourceText':quote,
                'newsIds':[event['newsId']], 'supports':[{'newsId':event['newsId'], 'supportQuote':quote}]})
        return {'headline': '本期具体技术进展及后续验证安排',
            'lead': '本期围绕有来源的技术事件核对已经完成的工作与后续验证安排，所有正文段落分别对应原文证据，保留项目当前进展与计划之间的区别。',
            'chapters':chapters, 'observations':observations}
    return build_daily_deepread(tech, {'deepread_core_events':4, 'deepread_target_events':12}, now,
        runtime={'provider':'deepseek'}, request_json=provider)


def localize_stage(stage):
    """Replace only the external provider output in an offline generation stage."""
    data = Path(stage) / 'data'
    report = load(data / 'news.json')
    edition = report['editionDate']
    for filename in ['news.json', 'stream.json']:
        value = load(data / filename)
        value['items'] = [translate_item(i) for i in value['items']]
        value.update(translationStatus='ok', translatedItemCount=len(value['items']),
                     translationProvider='deepseek', translationModel='authored-offline', translationWarnings=[])
        save(data / filename, value)
    report = load(data / 'news.json')
    save(data / f'archive/{edition}.json', report)
    status = load(data / 'status.json')
    status.update(translationStatus='ok', translatedItemCount=len(report['items']))
    save(data / 'status.json', status)
    deep = full_deep(report['items'], edition)
    from deepread_quality import choose_readable_deepread, deepread_status
    deep = choose_readable_deepread(deep, [], edition)
    status['deepread'] = deepread_status(deep, edition)
    save(data / 'status.json', status)
    save(data / 'deepread.json', deep)
    news.archive_deepread(deep, data / 'deepread', {'archive_retention_days':730})
    return deep


def advance_day(stage, edition):
    data = Path(stage) / 'data'
    report = load(data / 'news.json')
    report['editionDate'] = edition
    report['generatedAt'] = edition+'T00:00:00Z'
    report.pop('releaseId', None)
    report.pop('publicationRevision', None)
    for item in report['items']:
        item['publishedAt'] = edition+'T00:00:00Z'
    save(data / 'news.json', report)
    news.archive_report(report, data/'archive', data/'archive/index.json', data/'archive/search-index.json',730)
    status = load(data/'status.json')
    status.update(editionDate=edition, state='ok')
    save(data/'status.json', status)
    deep = full_deep(report['items'], edition)
    from deepread_quality import choose_readable_deepread
    deep = choose_readable_deepread(deep, [], edition)
    save(data/'deepread.json', deep)
    news.archive_deepread(deep, data/'deepread', {'archive_retention_days':730})
    return deep
