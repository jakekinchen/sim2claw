"""Portable, offline presentation of one operations evidence snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


def render_report(snapshot: Mapping[str, Any]) -> str:
    payload = dict(snapshot)
    payload.setdefault("generated_at", payload.get("observed_at", datetime.now(timezone.utc).isoformat()))
    # JSON is data in a non-executable script element. Escape HTML delimiters so
    # even a literal closing script tag in a log cannot leave that element.
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return _HTML.replace("__OPERATIONS_SNAPSHOT__", serialized)


def write_report(snapshot: Mapping[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".operations-report-", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(render_report(snapshot))
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)


_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>Sim2Claw operations evidence</title>
<style>
:root{color-scheme:light;--ground:#eef3f9;--paper:#fff;--ink:#19334c;--secondary:#4c6175;--blue:#315fbc;--line:#cad6e3;--good:#346953;--amber:#805b18}
*{box-sizing:border-box}body{margin:0;background:var(--ground);color:var(--ink);font:16px/1.5 Avenir,"Segoe UI",Arial,sans-serif}button,input,select{font:inherit}button{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #7196e5;outline-offset:3px}button:disabled{cursor:default;opacity:.5}main{max-width:1480px;margin:auto;padding:36px 36px 60px}header{display:grid;grid-template-columns:1fr minmax(260px,380px);gap:36px;align-items:start}h1{font-size:38px;line-height:1.12;letter-spacing:-1px;margin:0 0 12px;font-weight:650}h2{font-size:24px;margin:0 0 16px;line-height:1.2}h3{font-size:19px;line-height:1.3;margin:0 0 10px}p{max-width:76ch;margin:8px 0 14px}.muted{color:var(--secondary)}.snapshot{font-size:14px;color:var(--secondary)}.snapshot p{margin:0 0 8px}code,pre{font:13px/1.65 Menlo,Consolas,monospace}code{overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:0}button{border:1px solid var(--line);background:#fff;border-radius:6px;color:var(--ink);padding:7px 12px}.boundary{margin:25px 0 16px;padding:14px 18px;background:#e2ebf8;border-left:4px solid var(--blue)}.boundary p{margin:3px 0;font-size:14px}.stats{display:flex;flex-wrap:wrap;gap:12px 28px;padding:12px 0 20px;font-size:14px;color:var(--secondary)}.stats strong{color:var(--ink);font-size:19px;margin-right:5px}.nav{display:flex;gap:4px;border-bottom:1px solid var(--line);padding-top:6px}.nav button{background:transparent;border:0;border-bottom:3px solid transparent;border-radius:0;padding:12px 20px}.nav button[aria-selected=true]{border-bottom-color:var(--blue);color:var(--blue);font-weight:650}.panel{padding:24px 0}.panel[hidden]{display:none}.toolbar{display:flex;align-items:end;gap:14px;margin-bottom:18px;flex-wrap:wrap}label{font-size:14px;color:var(--secondary);display:grid;gap:5px}label.search{flex:1;min-width:250px}input,select{border:1px solid var(--line);background:var(--paper);color:var(--ink);padding:10px 12px;border-radius:6px}input[type=search]{width:100%}.browser{display:grid;grid-template-columns:minmax(280px,39%) minmax(0,1fr);border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--paper)}.list{border-right:1px solid var(--line);max-height:690px;overflow:auto;background:#f8fafd}.source{display:block;text-align:left;width:100%;border:0;border-bottom:1px solid #e0e7ef;border-radius:0;padding:13px 18px;background:transparent}.source[aria-pressed=true]{background:#dde8fa;box-shadow:inset 4px 0 0 var(--blue)}.source:hover{background:#e8eef7}.source-title{font-size:14px;overflow-wrap:anywhere;display:block}.source-meta{font-size:12px;color:var(--secondary);display:block;margin-top:5px}.detail{padding:25px;min-width:0;max-height:690px;overflow:auto}.detail h3{overflow-wrap:anywhere}.tag{display:inline-block;border-radius:4px;background:#e9eff6;color:var(--secondary);padding:3px 7px;font-size:12px;margin:0 6px 6px 0}.tag.good{background:#e6f1ea;color:var(--good)}.tag.gap{background:#f5ecd6;color:var(--amber)}.snippet{padding:18px;background:#f1f5fa;border-radius:6px;margin:18px 0;color:#263e54}.definition{display:grid;grid-template-columns:minmax(95px,120px) 1fr;gap:8px 16px;font-size:14px;margin:18px 0}.definition dt{color:var(--secondary)}.definition dd{margin:0;overflow-wrap:anywhere}details{margin:15px 0}summary{cursor:pointer;color:var(--blue)}details pre{margin-top:12px}.empty{padding:32px 20px;color:var(--secondary);max-width:65ch}.result-count{font-size:14px;color:var(--secondary);margin:8px 0 14px}.lesson-list{display:grid;gap:0;background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:0 24px}.lesson{padding:24px 0;border-bottom:1px solid var(--line)}.lesson:last-child{border-bottom:0}.lesson-top{display:flex;gap:10px;align-items:start;justify-content:space-between}.lesson-top h3{max-width:70ch}.citation{padding:12px 0;border-bottom:1px solid #e3eaf1;font-size:14px}.citation:last-child{border-bottom:0}.citation pre{margin:10px 0;color:var(--secondary)}.graph-list .source{padding:16px 18px}.relation{display:flex;gap:10px;align-items:center;margin:10px 0;flex-wrap:wrap;font-size:14px}.relation span{color:var(--secondary)}.event{display:grid;grid-template-columns:180px 1fr;gap:20px;padding:18px 0;border-bottom:1px solid var(--line)}.event time{font-size:13px;color:var(--secondary)}.event p{margin:0}.event .tag{margin-bottom:8px}.inline-empty{color:var(--secondary);font-size:14px}.more{display:block;margin:18px auto}footer{border-top:1px solid var(--line);padding-top:18px;font-size:13px;color:var(--secondary)}.snapshot-button{font-size:13px}.milestone{padding:14px 0;border-bottom:1px solid var(--line)}.milestone h3{font-size:16px}.status-details{font-size:13px}.source-link{font-size:13px;text-align:left;overflow-wrap:anywhere}a{color:var(--blue)}
@media(max-width:820px){main{padding:24px 18px 40px}header{grid-template-columns:1fr;gap:12px}h1{font-size:31px}.browser{grid-template-columns:1fr}.list{max-height:330px;border-right:0;border-bottom:1px solid var(--line)}.detail{max-height:none;padding:20px}.nav{overflow:auto}.nav button{padding:10px 15px;white-space:nowrap}.event{grid-template-columns:1fr;gap:6px}.definition{grid-template-columns:95px 1fr}.lesson-list{padding:0 18px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
</style>
</head>
<body>
<main>
<header><div><h1>Operations evidence</h1><p class="muted">Find the work behind the result. Inspect what agents tried, the evidence they left, and the structure we can improve.</p></div><div class="snapshot"><p><strong>Saved snapshot</strong> <time id="generated"></time></p><p>This page works offline. It does not update while agents run.</p><p>Refresh: <code>sim2claw ops report</code><br>Follow locally: <code>sim2claw ops watch</code></p><button class="snapshot-button" id="download">Download snapshot JSON</button></div></header>
<div class="boundary" id="boundary"></div><div class="stats" id="stats"></div>
<nav class="nav" role="tablist" aria-label="Evidence views"><button role="tab" id="tab-sources" aria-controls="sources" aria-selected="true" data-panel="sources">Sources</button><button role="tab" id="tab-lessons" aria-controls="lessons" aria-selected="false" data-panel="lessons">Lessons</button><button role="tab" id="tab-structure" aria-controls="structure" aria-selected="false" data-panel="structure">Structure</button><button role="tab" id="tab-activity" aria-controls="activity" aria-selected="false" data-panel="activity">Activity</button></nav>
<section class="panel" id="sources" role="tabpanel" aria-labelledby="tab-sources"><div class="toolbar"><label class="search">Search paths and saved excerpts<input id="query" type="search" placeholder="Try a task ID, failure, or technique"></label><label>Source kind<select id="kind"><option value="">All kinds</option></select></label><label>Index state<select id="source-state"><option value="">All states</option></select></label></div><p id="source-count" class="result-count" aria-live="polite"></p><div class="browser"><div class="list" id="source-list" aria-label="Sources"></div><article class="detail" id="source-detail" aria-live="polite"></article></div><details class="status-details"><summary>Coverage and exclusions</summary><pre id="coverage"></pre></details></section>
<section class="panel" id="lessons" role="tabpanel" aria-labelledby="tab-lessons" hidden><h2>Lessons with evidence</h2><p class="muted">These are proposed operating techniques. Check their supporting sources and validation conditions before adopting them.</p><div class="toolbar"><label class="search">Filter lessons<input type="search" id="lesson-query" placeholder="Search a topic or operating technique"></label></div><div class="lesson-list" id="lesson-list"></div></section>
<section class="panel" id="structure" role="tabpanel" aria-labelledby="tab-structure" hidden><h2>How the system fits together</h2><p class="muted" id="architecture-description"></p><div class="browser"><div class="list graph-list" id="node-list" aria-label="Architecture components"></div><article class="detail" id="node-detail" aria-live="polite"></article></div><details><summary>Milestones and acceptance gates</summary><div id="milestones"></div></details></section>
<section class="panel" id="activity" role="tabpanel" aria-labelledby="tab-activity" hidden><h2>Local operations journal</h2><p class="muted">Notes and events recorded by this tool. This is not a reconstructed history of every agent action.</p><p>Add a note in your terminal: <code>sim2claw ops note "What you want the agents to consider"</code></p><div id="event-list"></div></section>
<footer><p>Source text remains historical evidence. A saved excerpt does not verify an evaluator result or grant campaign, hardware, training, or compute authority. Use <code>sim2claw ops show &lt;path&gt;</code> to inspect an indexed span and recheck its source hash. CLI search covers full documents and decisions; runtime JSON indexes narrative words, not raw numeric arrays. Exact numeric source spans remain available through <code>show</code>.</p></footer>
</main>
<script type="application/json" id="snapshot-data">__OPERATIONS_SNAPSHOT__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById("snapshot-data").textContent);
const byId=id=>document.getElementById(id);
const arr=value=>Array.isArray(value)?value:[];
const fmt=value=>typeof value==="string"?value:JSON.stringify(value,null,2);
const text=(tag,value,cls)=>{const el=document.createElement(tag);el.textContent=value==null?"":String(value);if(cls)el.className=cls;return el;};
const replace=(id,...items)=>byId(id).replaceChildren(...items);
const badge=(value)=>text("span",value||"unknown","tag "+(["current","implemented","existing","available","indexed"].includes(value)?"good":["proposed","planned","missing","needs_review","stale","unavailable"].includes(value)?"gap":""));
const definition=(pairs)=>{const el=document.createElement("dl");el.className="definition";for(const [key,value]of pairs){el.append(text("dt",key),text("dd",value==null?"Not supplied":fmt(value)));}return el;};
const rawDetails=(label,value)=>{const el=document.createElement("details");el.append(text("summary",label),text("pre",fmt(value)));return el;};
const button=(label,fn,cls)=>{const el=text("button",label,cls);el.type="button";el.addEventListener("click",fn);return el;};
const sourceData=arr(data.sources), lessonData=arr(data.lessons), graph=data.architecture||{}, nodes=arr(graph.nodes), edges=arr(graph.edges);
let selectedPath=null, selectedNode=null, shown=100;
byId("generated").textContent=data.generated_at||data.observed_at||"Time unavailable";
byId("generated").dateTime=data.generated_at||data.observed_at||"";
const authority=data.authority||{}, campaign=authority.campaign||{};
replace("boundary",text("strong",authority.status==="pass"?(authority.execution_admitted?"Campaign has a scoped active card":"Campaign execution is closed"):"Current authority could not be verified"),text("p",campaign.current_milestone||authority.error||"No campaign state is available."),text("p",arr(authority.blockers).join(" ")||campaign.next_transition||"Historical evidence and local annotations do not change execution authority."));
const coverage=data.coverage||{};
for(const [label,value]of [["indexed sources",coverage.indexed??sourceData.filter(s=>s.status==="indexed").length],["skipped or missing",coverage.skipped??0],["lesson candidates",lessonData.length],["structure components",nodes.length]]){const span=document.createElement("span");span.append(text("strong",value),document.createTextNode(label));byId("stats").append(span);}
byId("coverage").textContent=fmt(coverage);
function openPanel(name){for(const tab of document.querySelectorAll("[data-panel]")){const selected=tab.dataset.panel===name;tab.setAttribute("aria-selected",String(selected));byId(tab.dataset.panel).hidden=!selected;}}
for(const tab of document.querySelectorAll("[data-panel]"))tab.addEventListener("click",()=>openPanel(tab.dataset.panel));
document.querySelector("[role=tablist]").addEventListener("keydown",event=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;const tabs=[...document.querySelectorAll("[data-panel]")],i=tabs.indexOf(document.activeElement);if(i<0)return;event.preventDefault();const next=event.key==="Home"?0:event.key==="End"?tabs.length-1:(i+(event.key==="ArrowRight"?1:-1)+tabs.length)%tabs.length;tabs[next].focus();openPanel(tabs[next].dataset.panel);});
for(const [id,key]of [["kind","kind"],["source-state","status"]]){for(const value of [...new Set(sourceData.map(s=>s[key]).filter(Boolean))].sort()){const option=text("option",value);option.value=value;byId(id).append(option);}}
function shellQuote(value){return "'"+String(value).replace(/'/g,"'\\''")+"'";}
function selectSource(path, citation=null){
  selectedPath=path;
  renderSources();
  const source=sourceData.find(s=>s.path===path);
  if(!source&&!citation){
    replace("source-detail",text("p","This source is not included in the saved inventory. Use the CLI to inspect its path.","empty"));
    return;
  }
  const firstLine=citation?Number(citation.line)||1:1;
  const lastLine=citation?Number(citation.end_line)||firstLine:firstLine;
  const heading=path+(citation?":"+firstLine+(lastLine!==firstLine?"–"+lastLine:""):"");
  const excerpt=citation?(citation.excerpt||"The cited excerpt is unavailable because its source verification did not pass."):(source.excerpt||"No text excerpt is available for this source.");
  const explanation=citation?"Cited lines "+firstLine+"–"+lastLine+". This is the lesson's supporting span, as verified when this snapshot was generated.":"Saved excerpt: up to 600 characters from the start of this source. The CLI searches documents and narrative runtime words; use show to inspect exact numeric spans.";
  const command="sim2claw ops show "+shellQuote(path)+(citation?" --start "+firstLine+" --end "+lastLine:"");
  const detail=byId("source-detail");
  detail.replaceChildren(
    text("h3",heading),badge(source?.kind||"citation"),badge(citation?citation.freshness:source.status),
    text("p",explanation,"muted"),text("pre",excerpt,"snippet"),
    definition([["Source bytes",source?.bytes],["Source lines",source?.lines],["SHA-256",citation?citation.sha256:source.sha256],["Freshness",citation?citation.freshness:"Hash recorded at scan time; use CLI show to recheck."]]),
    rawDetails("Extracted metadata",source?.metadata||{}),text("p","Inspect this span:"),text("code",command)
  );
}
function renderSources(){const query=byId("query").value.toLocaleLowerCase(),kind=byId("kind").value,state=byId("source-state").value;const filtered=sourceData.filter(s=>(!kind||s.kind===kind)&&(!state||s.status===state)&&(!query||(s.path+" "+(s.excerpt||"")+" "+fmt(s.metadata||{})).toLocaleLowerCase().includes(query)));byId("source-count").textContent=filtered.length+" matching sources; "+Math.min(shown,filtered.length)+" shown. Search covers saved excerpts and metadata, not the full source text.";const list=byId("source-list");list.replaceChildren();if(!filtered.length)list.append(text("p",sourceData.length?"No sources match these filters. Clear a filter or search indexed words with the CLI.":"No indexed sources are available. Run sim2claw ops index, then regenerate this report.","empty"));for(const source of filtered.slice(0,shown)){const item=button("",()=>selectSource(source.path),"source");item.setAttribute("aria-pressed",String(selectedPath===source.path));item.append(text("span",source.path,"source-title"),text("span",(source.kind||"source")+" / "+(source.status||"unknown")+" / "+(source.lines??0)+" lines","source-meta"));list.append(item);}if(filtered.length>shown)list.append(button("Show 100 more",()=>{shown+=100;renderSources();},"more"));}
for(const id of ["query","kind","source-state"])byId(id).addEventListener(id==="query"?"input":"change",()=>{shown=100;renderSources();});
renderSources();if(sourceData.length)selectSource(sourceData[0].path);else replace("source-detail",text("p","Select a source to inspect its identity and saved excerpt.","empty"));
function showCitation(source){openPanel("sources");byId("query").value="";byId("kind").value="";byId("source-state").value="";selectSource(source.path, source);}
function renderLessons(){const query=byId("lesson-query").value.toLocaleLowerCase();const filtered=lessonData.filter(row=>!query||fmt(row).toLocaleLowerCase().includes(query));const list=byId("lesson-list");list.replaceChildren();if(!filtered.length)list.append(text("p",lessonData.length?"No lessons match this filter.":"No curated lesson candidates have been loaded. Evidence search remains available in Sources.","empty"));for(const row of filtered){const section=document.createElement("article");section.className="lesson";const head=document.createElement("div");head.className="lesson-top";head.append(text("h3",row.title||row.id||"Lesson"),badge(row.status||"proposed"));section.append(head,badge(row.domain),badge(row.evidence_state),text("p",row.lesson||row.description||""));section.append(definition([["Action",row.action],["Validation",row.validation]]));for(const source of arr(row.sources)){const cite=document.createElement("div");cite.className="citation";cite.append(button((source.path||"Source")+":"+(source.line||1),()=>showCitation(source),"source-link"),document.createTextNode(" "),badge(source.freshness));if(source.excerpt)cite.append(text("pre",source.excerpt));section.append(cite);}list.append(section);}}
byId("lesson-query").addEventListener("input",renderLessons);renderLessons();
byId("architecture-description").textContent=graph.description||"Select a component to inspect its inputs, outputs, dependencies and acceptance gate. Proposed components are not implemented capabilities.";
function nodeTitle(id){return nodes.find(node=>node.id===id)?.title||id;}
function renderNodes(){const list=byId("node-list");list.replaceChildren();if(!nodes.length)list.append(text("p","No architecture catalog has been loaded.","empty"));for(const node of nodes){const item=button("",()=>selectNode(node.id),"source");item.setAttribute("aria-pressed",String(selectedNode===node.id));item.append(text("span",node.title||node.id,"source-title"),text("span",(node.layer||"component")+" / "+(node.state||"unknown"),"source-meta"));list.append(item);}}
function selectNode(id){selectedNode=id;renderNodes();const node=nodes.find(n=>n.id===id);if(!node)return;const detail=byId("node-detail");detail.replaceChildren(text("h3",node.title||node.id),badge(node.state),badge(node.layer),definition([["Owner",node.owner],["Inputs",node.inputs],["Outputs",node.outputs],["Acceptance gate",node.gate],["Next action",node.next_action]]));if(arr(node.path_state).length){detail.append(text("h3","Implementation paths"));for(const path of node.path_state)detail.append(text("p",path.path+" ("+(path.exists?"exists":"missing")+")","source-meta"));}const related=edges.filter(e=>e.from===id||e.to===id);detail.append(text("h3","Connected components"));if(!related.length)detail.append(text("p","No dependency edges are declared for this component.","inline-empty"));for(const edge of related){const item=document.createElement("div");item.className="relation";item.append(button(nodeTitle(edge.from),()=>selectNode(edge.from)),text("span",edge.relation||"connects to"),button(nodeTitle(edge.to),()=>selectNode(edge.to)));detail.append(item);}detail.append(button("Find source references",()=>{openPanel("sources");byId("query").value=node.id;shown=100;renderSources();}));}
renderNodes();if(nodes.length)selectNode(nodes[0].id);else replace("node-detail",text("p","The architecture map will appear when its catalog is available.","empty"));
for(const milestone of arr(graph.milestones)){const item=document.createElement("article");item.className="milestone";item.append(text("h3",milestone.title||milestone.id),badge(milestone.state),definition([["Depends on",milestone.depends_on],["Acceptance gate",milestone.gate]]));byId("milestones").append(item);}if(!arr(graph.milestones).length)byId("milestones").append(text("p","No milestones are declared.","inline-empty"));
const eventData=arr(data.events);for(const event of eventData){const item=document.createElement("article");item.className="event";const at=event.at||event.recorded_at||event.timestamp||"Time unavailable";const time=text("time",at);time.dateTime=at;const content=document.createElement("div");content.append(badge(event.kind||event.event||"note"),text("p",event.message||fmt(event.payload||{})));if(event.subject)content.append(text("p",event.subject,"muted"));item.append(time,content);byId("event-list").append(item);}if(!eventData.length)byId("event-list").append(text("p","No local operations events have been recorded yet. Add a note with the CLI, then regenerate this snapshot.","empty"));
byId("download").addEventListener("click",()=>{const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"}),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download="sim2claw-operations-snapshot.json";link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
</script>
</body>
</html>
'''
