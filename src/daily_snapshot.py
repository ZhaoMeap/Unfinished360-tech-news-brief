"""Bounded metadata plus operational provenance; never article bodies."""
import json
from .community import canonical
from .evidence import assess, event_id
from .events import same_event
from .fetch_sources import Article
from .scheduling import utc


def save_snapshot(root,results,now,report,slot=None):
    registry_path=root/'state/events.json'
    registry=json.loads(registry_path.read_text(encoding='utf-8')) if registry_path.exists() else []
    articles=[];proof={}
    for result in results:
        for article in result.articles:
            matched=next((e for e in registry if same_event(article,Article(**e['article']))),None)
            identity=matched['event_id'] if matched else event_id(article)
            if not matched:
                registry.append(dict(event_id=identity,article=article.metadata()))
            else:
                # Keep URL aliases for cross-source identity in future independent runners.
                if not any(e['article']['url']==article.url for e in registry):
                    registry.append(dict(event_id=identity,article=article.metadata()))
            evidence=assess(article)
            articles.append(article.metadata())
            proof[canonical(article.url)]=dict(level=evidence.level,label=evidence.label,reason=evidence.reason,
                                               quality_hint=article.quality_hint,event_id=identity)
    registry_path.parent.mkdir(parents=True,exist_ok=True)
    registry_path.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    folder=root/'data/daily';folder.mkdir(parents=True,exist_ok=True)
    payload=dict(version=2,collected_at=utc(now),scheduled_slot_id=slot,report_file=str(report.relative_to(root)),
                 articles=articles,evidence=proof,source_diagnostics=[dict(source=r.source,status=r.status,count=len(r.articles)) for r in results])
    path=folder/(report.stem.replace('_editor','')+'.json')
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return path
