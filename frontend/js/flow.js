/* 7 步全流程演示 */
/* ================= 7 步全流程 ================= */
function flowPaint(){
  document.querySelectorAll("#flowSteps .step").forEach((s,i)=>{
    s.classList.toggle("on", i===state.flowStage);
    s.classList.toggle("done", i<state.flowStage);
  });
}
function flowReset(){
  state.flowStage = 0; state.flowCase = null; state.flowDiag = null;
  state.flowReport = null;
  state.signatures = {operator:null, reviewer:null, approver:null};
  state.signed = false; state.signReportNo = null; state.editMode = false;
  state.submitted = false; state.receiptNo = null; state.submittedAt = null;
  state.editLog = []; state.version = 1; state.returnLog = [];
  state.previewMode = false;
  state.archiveMode = false;
  state.correctionOf = null;
  if(state.timer){ clearInterval(state.timer); state.timer = null; }
  flowPaint();
  document.getElementById("flowBody").innerHTML = `
    <p style="font-size:13.5px;line-height:1.9;">以一条真实形态的可疑交易为例（<b>贴线分拆现金存入规避大额申报</b>），一键走完业务闭环：</p>
    <p style="font-size:13px;line-height:1.9;color:var(--muted);margin-top:6px;">
      交易扫描 → 规则引擎 + AI 预诊断 → 人工研判处置 → 一键生成 STR（<b>62 项官方要素 + 中英双语正文</b>）→ 报告预览 → 打印签字 → 三级流转授权 → 报文报送，全程留痕。</p>
    <div style="margin-top:16px;"><button class="btn" onclick="flowScan()">▶ 开始全流程演示</button></div>`;
}
function flowScan(){
  state.flowStage = 1; flowPaint();
  const body = document.getElementById("flowBody");
  body.innerHTML = `<div class="flow-log" id="flowLog"></div><div class="pbar"><div id="flowBar"></div></div>`;
  Promise.all([jget("/api/cases"), jget("/api/rules")]).then(([cs, rs])=>{
    const by = {intercept:0, grey:0, pass:0};
    cs.cases.forEach(c=>by[c.category] = (by[c.category]||0)+1);
    const execCount = (rs.rules||[]).filter(r=>r.executable).length;
    const lines = [
      `[10:00:01] 加载案例库：${cs.cases.length} 条（拦截 ${by.intercept} / 灰区 ${by.grey} / 放行 ${by.pass}）`,
      `[10:00:02] 规则库装载：定义 ${rs.rules.length} 条；MVP 可执行 ${execCount} 条，其余规划中`,
      `[10:00:03] 逐案扫描交易流水，提取结构化特征……`,
      `[10:00:04] 规则引擎执行完成：拦截 ${by.intercept} 条、灰区 ${by.grey} 条进入人工研判队列`,
      `[10:00:05] 风险分级排序完成：可疑拦截优先，灰区次之，放行留痕`,
      `[10:00:06] 研判队列已推送至反洗钱专岗工作台`
    ];
    let i = 0;
    state.timer = setInterval(()=>{
      const log = document.getElementById("flowLog"), bar = document.getElementById("flowBar");
      if(!log || !log.isConnected){ clearInterval(state.timer); state.timer = null; return; }
      if(i < lines.length){
        log.innerHTML += lines[i] + (i===lines.length-1 ? '<br><b class="ok">扫描完成。</b>' : '') + "<br>";
        bar.style.width = ((i+1)/lines.length*100) + "%";
        i++;
        if(i === lines.length){
          clearInterval(state.timer); state.timer = null;
          log.innerHTML += '<br><button class="btn small" onclick="flowPick()">进入预警筛选 →</button>';
        }
      }
    }, 480);
  }).catch(e=>{ body.innerHTML = `<p style="color:var(--red)">${esc(errText(e))}</p>`; });
}
function flowPick(){
  state.flowStage = 2; flowPaint();
  const sorted = state.cases.slice().sort((a,b)=>
    CAT_ORDER.indexOf(a.category) - CAT_ORDER.indexOf(b.category) || a.case_id.localeCompare(b.case_id));
  const rows = sorted.map((c,i)=>`
    <div class="flow-row ${i===0?"sel":""}" id="frow-${i}" onclick="flowSelect(${i},'${esc(c.case_id)}')">
      <span class="mono">${esc(c.case_id)}</span>
      <span>${esc(c.title)}</span>
      <span class="tag ${c.category==="intercept"?"red":c.category==="grey"?"amber":"green"}">${CAT_LABEL[c.category]}</span>
      <span class="score" style="color:var(--${c.category==="intercept"?"red":c.category==="grey"?"amber":"green"})">${esc(c.expected_conclusion)}</span>
    </div>`).join("");
  window._flowSorted = sorted;
  state.flowCase = sorted[0].case_id;
  document.getElementById("flowBody").innerHTML = `
    <p style="font-size:13px;color:var(--muted);margin-bottom:10px;">AI 已按风险分排序，请选择一条进入研判（默认选中最高风险）：</p>
    <div class="card" style="margin-bottom:14px;"><div class="panel-body" style="padding:0;">${rows}</div></div>
    <button class="btn" onclick="flowJudge()">进入研判处置 →</button>`;
}
function flowSelect(i,cid){
  state.flowCase = cid;
  document.querySelectorAll(".flow-row").forEach((el,k)=>el.classList.toggle("sel", k===i));
}
async function flowJudge(){
  state.flowStage = 3; flowPaint();
  const body = document.getElementById("flowBody");
  body.innerHTML = `<div style="text-align:center;padding:44px;"><span class="loading"></span> 规则引擎 + AI 研判中…</div>`;
  try{
    const d = await jpost("/api/diagnose/" + state.flowCase);
    state.flowDiag = d;
    const t = d.triage, ai = d.ai_diagnosis;
    const cls = t.decision==="拦截" ? "intercept" : t.decision==="放行" ? "pass" : "review";
    const hits = d.rule_hits.map(h=>`
      <div class="hit-card"><span class="rid">${h.rule_id}</span><span class="rname">${esc(h.rule_name)}</span>
        <span class="tag amber">${esc(h.official_type_name||"基础监测")}</span>
        <div class="rdesc">${esc(h.trigger_desc)}</div></div>`).join("")
      || '<div class="hit-card"><div class="rdesc">未命中任何监测规则</div></div>';
    body.innerHTML = `
      <div class="triage-banner ${cls}" style="margin-bottom:14px;">
        <div class="verdict">${esc(t.decision)}</div>
        <div><div style="font-weight:600;">${esc(d.case_id)} · ${esc(d.title)}</div>
        <div class="meta">${esc(t.path)}：${esc(t.reason)}</div></div>
      </div>
      <div class="card" style="margin-bottom:12px;"><h3>规则引擎命中</h3><div class="panel-body">${hits}</div></div>
      <div class="card" style="margin-bottom:12px;"><h3>AI 诊断结论 <small>${ai.provider==="mock-prebuilt"?"预生成校验":"Live"}</small></h3>
        <div class="panel-body"><div class="ai-card">
          <h4>${esc(ai.conclusion)} · ${esc(ai.risk_level)}风险 ${ai.official_type_name?`<span class="tag amber">${esc(ai.official_type_no)} ${esc(ai.official_type_name)}</span>`:""}</h4>
          <ul>${(ai.analysis_points||[]).map(p=>`<li>${esc(p)}</li>`).join("")}</ul>
          ${ai.elimination?`<div class="elim"><b>排除理由：</b>${esc(ai.elimination)}</div>`:""}
          <div class="sug"><b>处置建议：</b>${esc(ai.suggestion)}</div>
        </div></div></div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <button class="btn" onclick="flowStr()">确认可疑 · 生成 STR 报送 →</button>
        <button class="btn ghost" onclick="toast('已排除并留痕；本演示建议选择上报，走完闭环')">人工排除</button>
      </div>`;
  }catch(e){
    body.innerHTML = `<p style="color:var(--red)">${esc(e.message)}</p><button class="btn ghost small" onclick="flowJudge()">重试</button>`;
  }
}
async function flowStr(){
  state.flowStage = 4; flowPaint();
  const body = document.getElementById("flowBody");
  body.innerHTML = `<p style="font-size:13.5px;">正在依据交易数据与研判结论生成 STR 初稿…</p>
    <div class="pbar"><div id="flowBar" style="width:35%"></div></div>`;
  try{
    const rep = await jpost("/api/report/" + state.flowCase, {diagnosis: state.flowDiag ? state.flowDiag.ai_diagnosis : null});
    state.flowReport = rep;
    const c = rep.counts;
    document.getElementById("flowBar").style.width = "100%";
    body.innerHTML = `
      <p style="font-size:13.5px;line-height:1.9;">STR 初稿生成完成 —— 按人民银行 3 号令附件 <b>62 项要素</b>逐项填充：</p>
      <div class="kv-grid" style="margin-top:12px;">
        <div class="kv"><div class="k">系统带出</div><div class="v" style="color:#4338ca">${c.system} 项</div></div>
        <div class="kv"><div class="k">演示预填（合成）</div><div class="v" style="color:#0369a1">${c.synthetic} 项</div></div>
        <div class="kv"><div class="k">AI 生成</div><div class="v" style="color:var(--purple)">${c.ai} 项</div></div>
        <div class="kv"><div class="k">本笔不适用</div><div class="v" style="color:var(--muted)">${c.na} 项</div></div>
      </div>
      <div class="card" style="margin:14px 0;"><div class="panel-body" style="font-size:12.5px;line-height:1.9;color:var(--muted);">
        AI 只负责第 21、22 项（资金交易及客户行为情况、疑点分析）；其余由系统从流水取数，或按案例编号确定性生成演示预填值。
        本页所有数据均为脱敏合成，仅用于演示。
      </div></div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <button class="btn" onclick="openReport(state.flowReport)">查看 62 项要素 / 中英正文</button>
        <button class="btn" onclick="flowPreview()">进入报告预览与签署 →</button>
      </div>`;
  }catch(e){
    body.innerHTML = `<p style="color:var(--red)">${esc(e.message)}</p><button class="btn ghost small" onclick="flowStr()">重试</button>`;
  }
}
function flowPreview(){
  state.flowStage = 5; flowPaint();
  if(state.flowReport) openReport(state.flowReport);
  document.getElementById("flowBody").innerHTML = `
    <p style="font-size:13.5px;line-height:1.9;">报告预览已打开，请完成：① <b>打印确认</b>（A4 版式，含签字区）；② <b>核对 / 修订</b>；③ <b>三级授权签字</b>。签字完成后仍需在下一步<b>单独确认提交报送</b>。</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;">
      <button class="btn ghost" onclick="if(state.flowReport)openReport(state.flowReport)">重新打开报告预览</button>
      <button class="btn" onclick="flowAuth()">进入签字与授权 →</button>
    </div>`;
}
function flowAuth(){
  state.flowStage = 6; flowPaint();
  const done = SIGN_ROLES.every(r=>state.signatures[r.key]);
  const rows = SIGN_ROLES.map(r=>{
    const s = state.signatures[r.key];
    return s
      ? `<div class="sign-row"><span class="role">${r.title}人</span><span class="who done">${s.name}</span>
          <span class="meta">工号 ${s.id} · 岗位 ${s.post}</span><span class="meta">${sigMeta(s)}</span></div>`
      : `<div class="sign-row"><span class="role">${r.title}人</span><span class="who pending">待授权</span>
          <span class="meta">${r.name} · ${r.id} · ${r.post}</span><span class="meta">尚未签字</span></div>`;
  }).join("");
  const block = `<div class="sign-block"><div class="sign-title">签字与授权留痕</div>${rows}</div>`;
  document.getElementById("flowBody").innerHTML = `
    <p style="font-size:13.5px;line-height:1.9;">STR 报送须走<b>三级流转</b>：经办 → 复核 → 审批。每级都要选择授权方式（指纹 / 人脸 / 授权卡 / 通行密钥），
      姓名、工号、岗位与时间写入报告。</p>
    ${block}
    ${state.submitted
      ? `<div class="flow-done" style="margin-top:14px;">✓ ${state.readOnly ? "演示送达完成" : "已提交报送"} · 回执 ${esc(state.receiptNo)} · ${esc(state.submittedAt)}</div>
         ${state.readOnly ? `<div class="note-bar warn" style="margin-top:10px;">演示环境说明：本次送达<b>未连接人行报文系统（CAMLMAC）、未写入业务台账</b>，
           回执号为本地模拟生成（RX-DEMO 前缀），仅用于演示闭环，不具备报送效力。接入网关、机构证书签名与专线后可正式报送。</div>` : ""}
         <div style="margin-top:12px;"><button class="btn" onclick="flowSubmit()">查看报文与回执 →</button></div>`
      : done
        ? `<div class="note-bar" style="margin-top:14px;"><b>三级授权已完成，报告已定稿。</b>签字不等于提交，请确认提交报送——提交后不可撤回，5 个工作日报送时限监控开始。</div>
           <div style="margin-top:12px;"><button class="btn" onclick="flowSubmit()">确认提交报送 · 生成报文 →</button></div>`
        : `<div class="note-bar warn" style="margin-top:14px;">报告尚未完成三级授权。请打开报告，先核对/修订，再逐级授权签字。</div>
           <div style="margin-top:12px;"><button class="btn" onclick="openReport(state.flowReport)">打开报告 · 完成核对与授权 →</button></div>`}`;
}
async function flowSubmit(){
  if(!SIGN_ROLES.every(r=>state.signatures[r.key])) return flowAuth();
  const rep = state.flowReport;
  if(!rep) return flowStr();
  // 只读演示：走"演示送达"，拿到模拟回执后继续往下走，流程不断
  if(state.readOnly && !state.submitted){
    state.report = rep;
    const rec = demoSubmitRecord(rep, state.signatures);
    state.submitted = true;
    state.receiptNo = rec.receipt_no;
    state.submittedAt = rec.submitted_at;
    toast(`演示送达完成 · 模拟回执 ${rec.receipt_no}（未连接人行报文系统，未入库）`);
  }
  if(!state.submitted){
    // 先写台账成功、再进入"已报送"环节：失败停留在签字环节可重试
    state.report = rep;
    const saved = await saveSubmission();
    if(!saved){
      toast("报送未完成：台账写入失败，报告仍为「已签字待报送」，可重试");
      return flowAuth();
    }
    state.submitted = true;
    state.receiptNo = saved.receipt_no;
    state.submittedAt = saved.submitted_at || isoNow();
  }
  state.flowStage = 7; flowPaint();
  const receiptNo = state.receiptNo;
  const v = {};
  rep.elements.forEach(e=>v[e.no] = e.value);
  const sig = state.signatures;
  const sigDesc = s => `${s.name} ${s.id}（${s.channel?s.channel+" / ":""}${s.method}${s.device?" · "+s.device:""}${s.score?" · "+s.score:""}）`;
  const audit = `经办：${sigDesc(sig.operator)}｜复核：${sigDesc(sig.reviewer)}｜审批：${sigDesc(sig.approver)}｜三级授权已归档`;
  const xml = `&lt;Report&gt;<br>
　&lt;ReportInfo&gt; 报告机构编码：${esc(v[1])}｜报告类型：STR｜紧急程度：${esc(v[17])}｜报送次数：${esc(v[18])}｜报送方向：${esc(v[19])}｜生成时间：${new Date().toLocaleString("zh-CN")} &lt;/ReportInfo&gt;<br>
　&lt;SubjectInfo&gt; 可疑主体：${esc(v[4])}｜证件类型：${esc(v[5])}｜证件号码：${esc(v[6])}｜国籍：${esc(v[16])} &lt;/SubjectInfo&gt;<br>
　&lt;TransactionInfo&gt; 账号：${esc(v[31])}｜交易时间：${esc(v[38])}｜金额：${esc(v[48])}｜币种：${esc(v[47])} &lt;/TransactionInfo&gt;<br>
　&lt;AnalysisInfo&gt; 触发点：${esc(v[20])}｜疑似涉罪类型：${esc(v[23])}｜特征代码：${esc(v[24])} &lt;/AnalysisInfo&gt;<br>
　&lt;AuditInfo&gt; ${esc(audit)} &lt;/AuditInfo&gt;<br>
&lt;/Report&gt;`;
  document.getElementById("flowBody").innerHTML = `
    <p style="font-size:13.5px;">按人民银行报文规范生成可疑交易报告报文（字段取自本笔 62 项要素表）：</p>
    <div class="flow-log" style="margin-top:10px;">${xml}</div>
    <p style="font-size:13px;line-height:1.9;margin-top:12px;">报文经<b>专线加密通道</b>提交<b>人民银行反洗钱监测分析中心（CAMLMAC）</b>，本机构留存纸质版打印、签字、扫描归档。</p>
    <div class="pbar"><div id="flowBar"></div></div><div id="receipt"></div>`;
  setTimeout(()=>{ const b=document.getElementById("flowBar"); if(b) b.style.width="45%"; },100);
  setTimeout(()=>{ const b=document.getElementById("flowBar"); if(b) b.style.width="100%"; },900);
  setTimeout(()=>{
    const r = document.getElementById("receipt");
    if(!r || !r.isConnected) return;
    const dl = rep.filing_deadline ? ` · 法定报送时限 ${rep.filing_deadline}` : "";
    r.innerHTML = state.readOnly
      ? `<div class="flow-done">✔ 演示送达完成 · 模拟回执编号 <b>${esc(receiptNo)}</b>${dl}（发现之日起 5 个工作日内）
           <div style="font-weight:400;font-size:12px;color:#92400e;margin-top:6px;">
           本次<b>未连接人行报文系统（CAMLMAC）</b>，没有真实确认时间；回执号由本地生成、未写入业务台账，不具备报送效力。
           接入网关、机构证书签名与专线后即为正式报送。</div></div>
         <button class="btn ghost small" style="margin-top:12px;" onclick="toast('演示模式：回执与授权影像归档包为前端模拟，未落盘')">查看回执与归档包</button>`
      : `<div class="flow-done">✔ 报送成功 · 回执编号 <b>${receiptNo}</b> · CAMLMAC 确认时间 ${new Date().toLocaleTimeString("zh-CN")}${dl}（发现之日起 5 个工作日内）</div>
      <button class="btn ghost small" style="margin-top:12px;" onclick="toast('已打开回执与授权影像归档包（演示）')">查看回执与归档包</button>`;
    flowFinish();
  }, 1500);
}
function flowFinish(){
  const b = document.getElementById("flowBody");
  if(b && !document.getElementById("flowSum")){
    b.insertAdjacentHTML("beforeend",
      `<div id="flowSum" class="flow-done" style="margin-top:12px;">✔ 全流程闭环完成：扫描 → 命中 → 研判 → STR（中/英）→ 预览签字 → 三级授权 → 报文报送 → 回执归档，全程留痕。
       ${state.readOnly ? "<br><span style=\"font-weight:400;font-size:12px;color:#92400e;\">注：当前为演示环境，报送环节为「演示送达」（模拟回执、未出网、未入库），其余环节均走真实后端。</span>" : ""}</div>`);
  }
}
