/* 案例列表、研判结果、溯源链路 */
function renderCaseList(){
  const byCat = {};
  state.cases.forEach(c => (byCat[c.category] = byCat[c.category] || []).push(c));
  let html = `<h3>案例库（${state.cases.length} 条）</h3>`;
  CAT_ORDER.forEach(cat=>{
    if(!byCat[cat]) return;
    html += `<div class="case-group"><div class="case-group-label">${CAT_NAME[cat]}</div>`;
    byCat[cat].forEach(c=>{
      html += `<div class="case-item" data-cid="${esc(c.case_id)}" onclick="loadCase('${esc(c.case_id)}')">
        <div class="cid">${esc(c.case_id)}</div>
        <div class="ctitle">${esc(c.title)}<span class="case-cat cat-${c.category}">${CAT_LABEL[c.category]}</span></div>
      </div>`;
    });
    html += `</div>`;
  });
  document.getElementById("caseList").innerHTML = html;
}

async function loadCase(cid){
  document.querySelectorAll(".case-item").forEach(el=>el.classList.toggle("active", el.dataset.cid===cid));
  const c = await jget("/api/cases/" + cid);
  state.current = c;
  renderCase(c);
}

function renderCase(c){
  const ci = c.customer_info;
  // 已定性案例库条目（LIB-/DIS-）只读查看，不重新研判
  const isLibrary = !!(c.source && c.source !== "demo");
  const txRows = c.transactions.map(t=>`
    <tr><td>${esc(t.date)} ${esc(t.time||"")}</td><td>${esc(t.type)}</td>
    <td>${esc(t.purpose||"—")}</td>
    <td class="${IN_TYPES.includes(t.type) ? "amt-in" : "amt-out"}">${fmtTxAmount(t)}</td>
    <td>${esc(t.counterparty||"—")}</td><td>${esc(t.channel||"—")}</td><td>${esc(t.summary||"—")}</td></tr>`).join("");
  document.getElementById("mainCol").innerHTML = `
    <div class="panel">
      <div class="panel-head"><h2>${esc(c.case_id)} · ${esc(c.title)}</h2>
        <span class="case-cat cat-${esc(c.category)}" style="font-size:12px;padding:3px 10px;">期望结论：${esc(c.expected_conclusion)}</span></div>
      <div class="panel-body">
        ${isLibrary?`<div class="miss-box" style="margin:0 0 10px;">已定性案例库条目（来源：报送沉淀 / 人工排除），仅供查阅；原始研判记录见上报台账归档。</div>`:""}
        <div class="kv-grid">
          <div class="kv"><div class="k">客户</div><div class="v">${esc(ci.name)}</div></div>
          <div class="kv"><div class="k">职业/行业</div><div class="v">${esc(ci.occupation)}</div></div>
          <div class="kv"><div class="k">收入水平</div><div class="v">${esc(ci.income)}</div></div>
          <div class="kv"><div class="k">开户时间</div><div class="v">${esc(ci.open_date)}</div></div>
          <div class="kv"><div class="k">风险等级</div><div class="v">${esc(ci.risk_level)}</div></div>
        </div>
        <div style="margin-bottom:8px;"><span style="font-size:11.5px;color:var(--muted);margin-right:6px;">客户画像标签（来自客户信息系统，非本笔流水推断）：</span>${(ci.tags||[]).map(t=>`<span class="tag blue">${esc(t)}</span>`).join("")}</div>
        <table class="tx"><thead><tr><th>时间</th><th>交易类型</th><th>用途</th><th>金额</th><th>对手方</th><th>渠道</th><th>交易附言</th></tr></thead>
        <tbody>${txRows}</tbody></table>
        <div class="str-note" style="margin-top:6px;">三个字段含义不同：<b>交易类型</b>只描述“钱怎么走”（转账/现金/跨境/结汇）；<b>用途</b>是银行摘要或客户申报的业务用途（工资、货款、学费…）；<b>交易附言</b>是客户转账时自己填的备注（“—” 表示未填）。三者都不是系统判断——系统识别到的特征写在下方规则触发说明与 AI 分析要点里。外币交易显示原币金额与折人民币金额。</div>
        <div class="str-note" id="fxNote" style="margin-top:4px;"></div>
        <div style="text-align:center;margin-top:18px;">
          <button class="btn" id="btnDiag" onclick="runDiagnose()" ${isLibrary?"disabled title=\"已定性案例不支持重新研判\"":""}>开始研判</button>
        </div>
      </div>
    </div>
    <div id="resultArea"></div>`;
  appendFxNote(c);
}

async function runDiagnose(){
  const btn = document.getElementById("btnDiag");
  btn.disabled = true; btn.innerHTML = '<span class="loading"></span> 规则引擎 + AI 研判中…';
  try{
    const d = await jpost("/api/diagnose/" + state.current.case_id);
    state.workDiag = d;
    renderResult(d);
  }catch(e){ alert("研判失败：" + e.message); }
  btn.disabled = false; btn.textContent = "重新研判";
}

function renderSimilarCases(sim){
  if(!sim || !sim.results || !sim.results.length) return "";
  const rows = sim.results.map(r=>`
    <div class="hit-card" style="cursor:pointer;" title="点击查看该案例详情"
         onclick="openCaseById('${esc(r.case_id)}')">
      <span class="rid">${esc(r.case_id)}</span><span class="rname">${esc(r.title)}</span>
      <span class="tag ${r.band==="高度相似"?"red":r.band==="参考相似"?"amber":"gray"}">${esc(r.band)} ${r.score_percent}%</span>
      <span class="tag blue">${esc(r.expected_conclusion)}</span>
      ${r.official_type_name?`<span class="tag gray">${esc(r.official_type_no)} ${esc(r.official_type_name)}</span>`:""}
      <div class="rdesc">建议路径：${esc(r.route)}　|　文本相似 ${(r.components.text*100).toFixed(1)}% · 结构相似 ${(r.components.structured*100).toFixed(1)}%${r.components.matched_channels.length?`<br>共同渠道：${esc(r.components.matched_channels.join("、"))}`:""}${r.rules_hit.length?`<br>历史命中规则：${esc(r.rules_hit.join("、"))}`:""}</div>
    </div>`).join("");
  return `<div class="panel"><div class="panel-head"><h2>相似案例召回</h2>
      <span style="color:var(--muted);font-size:12px;">top ${sim.top_k} · 阈值 ${Math.round(sim.thresholds.high*100)}% / ${Math.round(sim.thresholds.medium*100)}%</span></div>
    <div class="panel-body">${rows}
      <div style="margin-top:8px;font-size:11.5px;color:var(--muted);">${esc(sim.disclaimer)}</div>
    </div></div>`;
}

async function recordDisposition(cid, btn){
  if(state.readOnly){ toast("只读演示环境不能写入案例库"); return; }
  const reason = prompt("请输入人工排除理由（写入案例库，供规则有效性统计）",
    "合同、发票、固定上下游与经营规模匹配，排除可疑");
  if(reason === null) return;
  try{
    const r = await jpost("/api/case-library/disposition",
      {case_id: cid, conclusion: "放行", reason, operator: "陈立 NJ-AML-0231"});
    toast(`已沉淀负样本 ${r.library_case_id}`);
    if(btn){ btn.disabled = true; btn.textContent = "已沉淀负样本"; }
  }catch(e){ toast("沉淀失败：" + e.message); }
}

function renderResult(d){
  const t = d.triage;
  const cls = t.decision === "拦截" ? "intercept" : t.decision === "放行" ? "pass" : "review";
  const ai = d.ai_diagnosis;
  const hitsHtml = d.rule_hits.length ? d.rule_hits.map(h=>`
    <div class="hit-card"><span class="rid">${h.rule_id}</span><span class="rname">${esc(h.rule_name)}</span>
      <span class="tag amber">${esc(h.official_type_name || "基础监测")}</span>
      <div class="rdesc">${esc(h.trigger_desc)}</div></div>`).join("")
    : '<div class="hit-card"><div class="rdesc">未命中任何监测规则</div></div>';

  const aiHtml = `
    <div class="ai-card">
      <h4>AI 研判结论：${esc(ai.conclusion)}　<span class="tag red">${esc(ai.risk_level)}风险</span>
        ${ai.official_type_name ? `<span class="tag amber">${esc(ai.official_type_no)} ${esc(ai.official_type_name)}</span>` : ""}
        <span class="tag gray">${ai.provider === "mock-prebuilt" ? "预生成校验" : esc(ai.model || "live")}</span></h4>
      <ul>${(ai.analysis_points||[]).map(p=>`<li>${esc(p)}</li>`).join("")}</ul>
      ${ai.elimination ? `<div class="elim"><b>排除理由：</b>${esc(ai.elimination)}</div>` : ""}
      ${(ai.materials_to_check||[]).length ? `<div style="margin-top:8px;"><b style="color:var(--amber)">需补充核验：</b><ul>${ai.materials_to_check.map(m=>`<li>${esc(m)}</li>`).join("")}</ul></div>` : ""}
      <div class="sug"><b>处置建议：</b>${esc(ai.suggestion)}</div>
    </div>`;

  const dispositionHtml = (t.path === "命中-排除留痕" && !state.readOnly) ? `
    <div class="panel"><div class="panel-head"><h2>命中-排除 · 人工确认</h2></div>
      <div class="panel-body">
        <div style="font-size:13px;color:var(--muted);line-height:1.8;">规则命中但 AI 已依据材料排除。人工核对合同、发票与上下游后，可把该结论沉淀为负样本；规则有效性中的「命中排除」将使用这条结果。</div>
        <button class="btn small" style="margin-top:10px;" onclick="recordDisposition('${esc(d.case_id)}', this)">确认排除并沉淀负样本</button>
      </div></div>` : "";

  let greyHtml = "";
  if(t.grey_zone && t.grey_zone.pass_if){
    greyHtml = `<div class="panel"><div class="panel-head"><h2>灰区双向判定</h2></div><div class="panel-body">
      <div class="grey-zone">
        <div class="grey-box pass"><h5>✓ 满足以下情形 → 放行</h5>${esc(t.grey_zone.pass_if)}</div>
        <div class="grey-box intercept"><h5>✗ 出现以下情形 → 拦截</h5>${esc(t.grey_zone.intercept_if)}</div>
        <div class="grey-box grey-check"><h5>人工核验清单</h5><ul>${(t.grey_zone.human_check_points||[]).map(p=>`<li>${esc(p)}</li>`).join("")}</ul></div>
      </div></div></div>`;
  }

  document.getElementById("resultArea").innerHTML = `
    <div class="triage-banner ${cls}">
      <div class="verdict">${esc(t.decision)}</div>
      <div><div style="font-weight:600;margin-bottom:4px;">分流路径：${esc(t.path)}</div>
      <div class="meta">${esc(t.reason)}</div></div>
    </div>
    <div class="panel"><div class="panel-head"><h2>规则引擎命中</h2><span style="color:var(--muted);font-size:12px;">真代码规则 R001–R009</span></div>
      <div class="panel-body">${hitsHtml}</div></div>
    <div class="panel"><div class="panel-head"><h2>AI 智能诊断</h2></div><div class="panel-body">${aiHtml}</div></div>
    ${dispositionHtml}
    ${renderSimilarCases(d.similar_cases)}
    ${greyHtml}
    <div class="panel"><div class="panel-head"><h2>法规溯源链</h2>
      <button class="btn ghost small" onclick="loadTrace('${esc(d.case_id)}')">展开溯源</button></div>
      <div class="panel-body" id="traceArea"><div style="color:var(--muted);font-size:13px;">点击「展开溯源」查看：命中规则 → 法规条款原文 → 官方类型识别点 → 处罚事由</div></div></div>
    <div class="panel"><div class="panel-head"><h2>可疑交易报告（STR）</h2>
      <button class="btn small" onclick="genReport('work')">⚡ 一键生成 STR 初稿</button></div>
      <div class="panel-body" style="font-size:13px;color:var(--muted);line-height:1.9;">
        按人行 3 号令附件 62 项要素逐项填充：系统带出 + 演示预填 + AI 生成第 21、22 项，专岗核实修订后报送。
      </div></div>`;
  document.getElementById("resultArea").scrollIntoView({behavior:"smooth"});
}

async function loadTrace(cid){
  const d = await jget("/api/trace/" + cid);
  let html = "";
  d.chain.forEach((tc,i)=>{
    const ruleLabel = tc.rule_id ? `${tc.rule_id} · ${(tc.rule_info||{}).name||""}` : "排除性研判（未命中规则）";
    html += `<div class="trace-item ${i===0?"open":""}">
      <div class="trace-head" onclick="this.parentElement.classList.toggle('open')">
        <span class="tag amber">${esc(ruleLabel)}</span>
        ${tc.official_type_name ? `<span class="tag blue">${esc(tc.official_type_no)} ${esc(tc.official_type_name)}</span>` : ""}
        <span style="margin-left:auto;color:var(--muted);font-size:12px;">点击展开 ▾</span>
      </div>
      <div class="trace-body">
        <div style="font-size:13px;line-height:1.7;margin-bottom:6px;"><b>触发逻辑：</b>${esc(tc.trigger_desc)}</div>
        ${tc.clauses.map(cl=>`
          <div class="clause-box">
            <span class="creg">${esc(cl.reg_name)}</span><span class="cno">${esc(cl.clause_no)}</span>
            ${cl.chapter ? `<span style="color:var(--muted);font-size:11px;margin-left:8px;">${esc(cl.chapter)}</span>` : ""}
            <div class="ccontent">${esc(cl.content)}</div>
          </div>`).join("")}
        ${tc.type_identify_content ? `<div class="clause-box"><span class="creg">可疑交易类型和识别点对照表</span><span class="cno">${esc(tc.type_clause_no)}</span><div class="ccontent">${esc(tc.type_identify_content)}</div></div>` : (tc.type_note ? `<div class="clause-box" style="border-color:#fcd34d;background:#fffbeb;"><span class="creg">官方类型识别点</span><span class="cno">说明</span><div class="ccontent" style="color:#92400e;">${esc(tc.type_note)}</div></div>` : "")}
        ${tc.penalty_ref ? `<div class="penalty"><b>对应央行处罚事由：</b>${esc(tc.penalty_ref)}</div>` : ""}
      </div></div>`;
  });
  document.getElementById("traceArea").innerHTML = html || '<div style="color:var(--muted)">无溯源数据</div>';
}


/* 外币折算汇率说明：与后端 data/fx_rates.json 同源，界面上可见、可手算核对 */
let _fxCache = null;
async function appendFxNote(c){
  const box = document.getElementById("fxNote");
  if(!box) return;
  box.innerHTML = "";
  const hasFx = (c.transactions || []).some(t => (t.currency || "CNY") !== "CNY");
  if(!hasFx) return;
  try{
    if(!_fxCache) _fxCache = await jget("/api/fx");
    const parts = Object.entries(_fxCache.rates || {})
      .map(([cur, rate]) => `1 ${esc(cur)} = ${rate} 元人民币`).join("　·　");
    const real = _fxCache.real_rates || {};
    box.innerHTML = `<b>演示折算汇率</b>：${parts}（取整估算值，非实时牌价；${esc(_fxCache.as_of || "")} 人民币中间价：`
      + (real.USD ? `1 美元 = ${real.USD} 元、` : "") + (real.EUR ? `1 欧元 = ${real.EUR} 元` : "")
      + "）。外币金额按此折算为人民币，规则命中与报告金额均以折人民币计量，可自行验算。";
  }catch(e){ /* 汇率说明加载失败不影响主流程 */ }
}
