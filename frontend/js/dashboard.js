/* 工作台看板、预警列表、名单筛查、大额报告、风险评级、规则配置 */
function renderDashboard(){
  const cs = state.cases;
  const counts = {intercept:0, grey:0, pass:0};
  cs.forEach(c=>counts[c.category]++);
  // 可执行规则清单以后端注册表为准（/api/rules 的 executable 字段），前端不再硬编码
  const executableCount = (state.rules||[]).filter(r=>r.executable).length;
  const regCount = (state.regulations||[]).length;
  const clauseCount = (state.regulations||[]).reduce((a,r)=>a+(r.clause_count||0), 0);
  const ds = state.dataset || {};

  document.getElementById("dashStats").innerHTML = `
    <div class="stat"><div class="lbl">演示案例</div><div class="num">${cs.length}<small> 条</small></div>
      <div style="font-size:11px;color:var(--muted);margin-top:4px;">${esc(ds.name||"演示数据集")} ${esc(ds.version||"")}</div></div>
    <div class="stat"><div class="lbl">可疑拦截</div><div class="num" style="color:var(--red)">${counts.intercept}<small> 条</small></div>
      <div style="font-size:11px;color:var(--muted);margin-top:4px;">规则 + AI 双确认</div></div>
    <div class="stat"><div class="lbl">灰区待复核</div><div class="num" style="color:var(--amber)">${counts.grey}<small> 条</small></div>
      <div style="font-size:11px;color:var(--muted);margin-top:4px;">需人工核验材料</div></div>
    <div class="stat"><div class="lbl">可执行规则</div><div class="num">${executableCount}<small> / ${state.rules.length}</small></div>
      <div style="font-size:11px;color:var(--muted);margin-top:4px;">法规 ${regCount} 部 · ${clauseCount} 条</div></div>`;

  // 近 7 个有交易的日期
  const dateCount = {};
  (state.caseDetails||[]).forEach(c=>(c.transactions||[]).forEach(t=>{
    dateCount[t.date] = (dateCount[t.date]||0)+1;
  }));
  const dates = Object.keys(dateCount).sort().slice(-7);
  const max = Math.max(1, ...dates.map(d=>dateCount[d]));
  document.getElementById("dashTrend").innerHTML = dates.length
    ? `<div class="trend">${dates.map(d=>`
        <div class="col"><div class="val">${dateCount[d]}</div>
          <div class="bar" style="height:${Math.max(4,(dateCount[d]/max)*110)}px"></div>
          <div class="dt">${d.slice(5)}</div></div>`).join("")}</div>
       <div class="str-note" style="margin-top:6px;">统计口径：演示数据集中全部案例的交易笔数，按交易日期汇总。</div>`
    : '<div class="miss-box">演示数据集暂无交易日期</div>';

  // 高频触发规则 TOP 5
  const hits = {};
  cs.forEach(c=>(c.rules_hit||[]).forEach(rid=>(hits[rid]=hits[rid]||[]).push(c.case_id)));
  const txMap = Object.fromEntries((state.caseDetails||[]).map(c=>[c.case_id, (c.transactions||[]).length]));
  const rmap = Object.fromEntries((state.rules||[]).map(r=>[r.rule_id, r.name]));
  const top = Object.keys(hits).sort((a,b)=>hits[b].length-hits[a].length || a.localeCompare(b)).slice(0,5);
  document.getElementById("dashRules").innerHTML = top.length
    ? `<table class="grid"><thead><tr><th>规则</th><th>名称</th><th>关联案例</th><th>关联交易</th><th>状态</th></tr></thead><tbody>
       ${top.map(rid=>{
         const tx = hits[rid].reduce((a,cid)=>a+(txMap[cid]||0), 0);
         return `<tr><td style="font-family:monospace;">${rid}</td><td>${esc(rmap[rid]||"")}</td>
           <td>${hits[rid].length} 条</td><td>${tx} 笔</td><td><span class="pill green">可执行</span></td></tr>`;
       }).join("")}
       </tbody></table>
       <div class="str-note" style="margin-top:6px;">仅统计演示数据集实际命中的规则；R011–R016 为规划中（需接入商户、报关、关系网络等数据）。</div>`
    : '<div class="miss-box">暂无规则命中</div>';

  // 今日待办：拦截优先，灰区次之
  const pending = cs.filter(c=>c.category==="intercept"||c.category==="grey")
    .sort((a,b)=>CAT_ORDER.indexOf(a.category)-CAT_ORDER.indexOf(b.category))
    .slice(0,6);
  document.getElementById("dashTodo").innerHTML = pending.length
    ? `<table class="grid"><thead><tr><th>事项</th><th>类型</th><th>状态</th><th>操作</th></tr></thead><tbody>
       ${pending.map(c=>`<tr class="clickable" onclick="jumpToCase('${esc(c.case_id)}')">
         <td><b style="font-family:monospace;">${esc(c.case_id)}</b>　${esc(c.title)}</td>
         <td><span class="pill ${c.category==="intercept"?"red":"amber"}">${CAT_NAME[c.category]}</span></td>
         <td>${c.category==="intercept"?"待研判确认":"待人工复核"}</td>
         <td style="color:var(--primary);font-size:12px;">进入处理 →</td></tr>`).join("")}
       </tbody></table>`
    : '<div class="miss-box">暂无待办</div>';

  const quick = [
    ["flow","全流程演示","7 步闭环：扫描 → 报送回执"],
    ["alerts","可疑交易预警","按风险优先级查看全部案例"],
    ["screening","名单筛查","命中即冻结，不经 AI"],
    ["ctr","大额交易报告","按 3 号令阈值自动识别"]
  ];
  document.getElementById("quickRow").innerHTML = quick.map(([page,t,d])=>
    `<div class="quick-card" onclick="showPage('${page}')"><b>${t}</b><span>${d}</span></div>`).join("");
}

function jumpToCase(cid){
  loadCase(cid);
  setTimeout(()=>document.getElementById("mainCol").scrollIntoView({behavior:"smooth", block:"start"}), 350);
}

/* ================= 预警列表 ================= */
function renderAlerts(){
  const body = document.getElementById("alertBody");
  if(!body || !state.cases.length) return;
  const rmap = Object.fromEntries((state.rules||[]).map(r=>[r.rule_id, r.name]));
  const sorted = state.cases.slice().sort((a,b)=>
    CAT_ORDER.indexOf(a.category) - CAT_ORDER.indexOf(b.category) || a.case_id.localeCompare(b.case_id));
  const rows = sorted.map(c=>{
    const rules = (c.rules_hit||[]).map(id=>`${id} ${rmap[id]||""}`).join("；") || "未命中";
    const cls = c.category==="intercept" ? "red" : c.category==="grey" ? "amber" : "green";
    return `<tr class="clickable" onclick="showPage('workbench');loadCase('${c.case_id}')">
      <td style="font-family:monospace;">${esc(c.case_id)}</td>
      <td>${esc(c.customer_name)}</td>
      <td>${esc(c.title)}</td>
      <td>${esc(rules)}</td>
      <td>${c.official_type_name ? `<span class="pill blue">${esc(c.official_type_name)}</span>` : "—"}</td>
      <td><span class="pill ${cls}">${c.expected_conclusion}</span></td>
      <td style="color:var(--primary);font-size:12px;">进入研判 →</td></tr>`;
  }).join("");
  body.innerHTML = `<table class="grid"><thead><tr><th>案例编号</th><th>客户</th><th>场景</th><th>命中规则</th><th>官方类型</th><th>预期</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
}

/* ================= 名单筛查 ================= */
function fillScan(v){ document.getElementById("scanInput").value = v; }
async function runScan(){
  const q = document.getElementById("scanInput").value.trim();
  const box = document.getElementById("scanResult");
  if(!q){ toast("请先输入筛查对象"); return; }
  box.innerHTML = '<p style="color:var(--muted);font-size:13px;">筛查中…</p>';
  try{
    const d = await jget("/api/screening?q=" + encodeURIComponent(q));
    if(d.hit){
      const items = d.matches.map(m=>`<div><b>${esc(m.name)}</b>　<span class="pill red">${esc(m.list)}</span>　<span class="pill amber">${esc(m.match_type)}</span></div>`).join("");
      box.innerHTML = `<div class="hit-box">⚠ 命中名单（模拟库 ${d.list_size} 条）${items}
        <div style="margin-top:8px;">处置：${esc(d.action)}</div>
        <button class="btn small" style="margin-top:10px;" onclick="toast('已冻结账户，紧急上报工单已生成（演示）')">执行冻结并生成上报工单</button></div>`;
    }else{
      box.innerHTML = `<div class="miss-box">✔ 未命中名单（模拟库 ${d.list_size} 条）。${esc(d.action)}</div>`;
    }
  }catch(e){ box.innerHTML = `<div class="hit-box">筛查失败：${esc(e.message)}</div>`; }
}

/* ================= 大额交易报告 ================= */
async function loadCtr(){
  const body = document.getElementById("ctrBody");
  if(!body) return;
  body.innerHTML = '<span class="loading"></span>';
  try{
    const d = await jget("/api/ctr");
    document.getElementById("ctrStats").innerHTML = `
      <div class="stat"><div class="lbl">应报大额记录</div><div class="num">${d.count}<small> 条</small></div></div>
      <div class="stat"><div class="lbl">涉及案例</div><div class="num">${d.cases}<small> 条</small></div></div>
      <div class="stat"><div class="lbl">现金标准</div><div class="num" style="font-size:18px;">5 万</div></div>
      <div class="stat"><div class="lbl">自然人转账</div><div class="num" style="font-size:18px;">50 万</div></div>
      <div class="stat"><div class="lbl">对公转账</div><div class="num" style="font-size:18px;">200 万</div></div>`;
    if(!d.rows.length){ body.innerHTML = '<div class="miss-box">当前演示数据集无达到大额标准的记录。</div>'; return; }
    const rows = d.rows.map(r=>`<tr>
      <td style="font-family:monospace;">${r.case_id}</td><td>${esc(r.customer)}</td><td>${r.date}</td>
      <td><span class="pill ${r.kind==="现金"?"amber":"blue"}">${r.kind}</span></td>
      <td style="font-family:monospace;">${fmtAmt(r.amount)}</td>
      <td style="font-family:monospace;">${fmtAmt(r.threshold)}</td>
      <td><span class="pill green">达标应报</span></td></tr>`).join("");
    body.innerHTML = `<table class="grid"><thead><tr><th>案例</th><th>客户</th><th>日期</th><th>类型</th><th>当日累计</th><th>阈值</th><th>状态</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="str-note">${esc(d.notice)}</div>`;
  }catch(e){ body.innerHTML = `<div class="hit-box">加载失败：${esc(e.message)}</div>`; }
}

/* ================= 风险评级 ================= */
function renderRating(){
  const body = document.getElementById("ratingBody");
  if(!body || !state.cases.length) return;
  const order = {"高":0, "中":1, "低":2};
  const sorted = state.cases.slice().sort((a,b)=>(order[a.risk_level]??9)-(order[b.risk_level]??9));
  const rows = sorted.map(c=>{
    const lvl = c.risk_level || "—";
    const cls = lvl==="高" ? "red" : lvl==="中" ? "amber" : "green";
    return `<tr class="clickable" onclick="showPage('workbench');loadCase('${c.case_id}')">
      <td style="font-family:monospace;">${esc(c.case_id)}</td><td>${esc(c.customer_name)}</td>
      <td>${esc(c.occupation)}</td><td><span class="pill ${cls}">${esc(lvl)}</span></td></tr>`;
  }).join("");
  body.innerHTML = `<table class="grid"><thead><tr><th>案例</th><th>客户</th><th>职业/行业</th><th>风险等级</th></tr></thead><tbody>${rows}</tbody></table>`;
}

/* ================= 规则配置 ================= */
async function loadRules(){
  const body = document.getElementById("rulesBody");
  if(!body) return;
  if(!state.rules || !state.rules.length){
    body.innerHTML = '<span class="loading"></span>';
    try{ state.rules = (await jget("/api/rules")).rules; }catch(e){ body.innerHTML = `<div class="hit-box">${esc(e.message)}</div>`; return; }
  }
  // executable 由后端规则注册表返回，与"可执行"状态同源
  const rows = state.rules.map(r=>{
    let params = "—";
    try{ params = JSON.stringify(JSON.parse(r.params||"{}"), null, 0); }catch(e){ params = r.params || "—"; }
    return `<tr>
      <td style="font-family:monospace;">${r.rule_id}</td>
      <td>${esc(r.name)}</td>
      <td><span class="pill ${r.executable?"green":"amber"}">${r.executable?"可执行":"规划中"}</span></td>
      <td>${esc(r.official_type_name||"—")}</td>
      <td>${esc(r.legal_desc||"—")}</td>
      <td><details class="rule-detail"><summary>参数</summary><pre>${esc(params)}</pre></details></td></tr>`;
  }).join("");
  body.innerHTML = `<table class="grid"><thead><tr><th>编号</th><th>规则</th><th>状态</th><th>官方/行内类型</th><th>法条依据</th><th>参数</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="str-note">「官方/行内类型」列：官方对照表 12 类之外的标签均为行内监测维度归纳（如新开户短期大额跨境、涉虚拟货币交易特征），不是官方类型；CDD 条线 R017 承接身份不明类非交易型可疑行为。</div>`;
  loadLinkage();
}

async function loadLinkage(){
  try{
    const [cov, eff, lib] = await Promise.all([
      jget("/api/linkage/coverage"), jget("/api/linkage/effectiveness"), jget("/api/case-library")
    ]);
    renderCoverage(cov);
    renderEffectiveness(eff);
    renderCaseLibrary(lib);
  }catch(e){
    ["coverageBody","effectivenessBody","caseLibraryBody"].forEach(id=>{
      const el = document.getElementById(id);
      if(el) el.innerHTML = `<div class="hit-box">联动数据加载失败：${esc(e.message)}</div>`;
    });
  }
}

function renderCoverage(data){
  const body = document.getElementById("coverageBody");
  if(!body) return;
  const rows = (data.types||[]).map(t=>{
    const cls = t.status==="已覆盖"?"green":t.status==="部分覆盖"?"blue":t.status==="规划中"?"amber":"";
    const style = cls?"":` style="background:#f1f5f9;color:#64748b;"`;
    const origin = t.official===false ? ` <span class="pill gray" style="font-size:10px;">行内归纳</span>` : "";
    return `<tr><td style="font-family:monospace;">${esc(t.no)}</td><td>${esc(t.name)}${origin}</td>
      <td><span class="pill ${cls}"${style}>${esc(t.status)}</span></td><td>${esc(t.rule||"—")}</td>
      <td style="font-family:monospace;">${t.case_count||0}</td><td style="color:var(--muted);">${esc(t.note)}</td></tr>`;
  }).join("");
  body.innerHTML = `<table class="grid"><thead><tr><th>编号</th><th>类型</th><th>覆盖状态</th><th>规则</th><th>案例支撑</th><th>说明</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="str-note">官方 12 类（类型1-1 ~ 类型12）来自《可疑交易类型和识别点对照表（银行业参考版）》原文；标注「行内归纳」的 4 组为监测维度归纳，不是官方对照表类型；「无法归类」出口承接非交易型可疑行为（如客户身份不明，11 号令第四十一条）与未定型案例。案例源：演示库 + 已定性案例库（当前已定性 ${data.library_cases||0} 条）；「案例支撑」表示该类型下已有案例数，不代表规则已完全覆盖。</div>`;
}

function renderEffectiveness(data){
  const body = document.getElementById("effectivenessBody");
  if(!body) return;
  if(!(data.rules||[]).length){
    body.innerHTML = '<div class="hit-box">暂无可执行规则的案例统计</div>';
    return;
  }
  const rows = data.rules.map(r=>{
    const rate = r.hit_cases ? `${r.confirm_rate}%` : "—";
    const cls = r.confirm_rate>=80?"green":r.confirm_rate>=50?"blue":"amber";
    return `<tr><td style="font-family:monospace;">${esc(r.rule_id)}</td><td>${esc(r.rule_name)}</td>
      <td>${r.hit_cases}</td><td>${r.confirmed}</td><td>${r.excluded}</td><td>${r.review}</td>
      <td><span class="pill ${cls}">${rate}</span></td>
      <td style="color:var(--muted);font-family:monospace;">${esc((r.case_ids||[]).join("、")||"—")}</td></tr>`;
  }).join("");
  body.innerHTML = `<table class="grid"><thead><tr><th>规则</th><th>名称</th><th>命中案例</th><th>确认拦截</th><th>命中排除</th><th>人工复核</th><th>确认率</th><th>案例编号</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="str-note">${esc(data.note||"")}</div>`;
}

function renderCaseLibrary(data){
  const body = document.getElementById("caseLibraryBody");
  if(!body) return;
  if(!data.count){
    body.innerHTML = '<div class="hit-box">尚无已定性案例。完成一次报送后，系统会自动把报告沉淀为案例库条目；也可调用 POST /api/linkage/backfill 回填历史报送。</div>';
    return;
  }
  const srcLabel = {submission:"报送沉淀", disposition:"人工排除", manual:"手工录入", import:"批量导入"};
  const rows = data.entries.map(e=>`
    <tr class="clickable" onclick="openCaseById('${esc(e.case_id)}')">
    <td style="font-family:monospace;">${esc(e.case_id)}</td><td>${esc(e.source_case_id||"—")}</td>
      <td><span class="pill ${e.expected_conclusion==="拦截"?"red":e.expected_conclusion==="放行"?"green":"amber"}">${esc(e.expected_conclusion)}</span></td>
      <td>${esc(e.official_type_name||"—")}</td><td>${esc((e.rules_hit||[]).join("、")||"—")}</td>
      <td>${esc(e.report_no||"—")}</td>
      <td>${esc((e.audit||{}).reason||"—")}</td>
      <td>${esc(srcLabel[e.source]||e.source||"—")}</td><td style="color:var(--muted);">${esc(e.updated_at||e.created_at||"—")}</td></tr>`).join("");
  body.innerHTML = `<table class="grid"><thead><tr><th>案例库编号</th><th>来源案例</th><th>结论</th><th>官方类型</th><th>规则</th><th>报告编号</th><th>确认理由</th><th>来源</th><th>入库时间</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="str-note">点击任意条目可在工作台查看该案例详情（只读）；完整报告快照见「上报台账」归档。</div>`;
}

/* 已定性案例库条目 → 工作台只读查看（/api/cases/{id} 演示 JSON 未命中时回退查案例库） */
async function openCaseById(cid){
  showPage("workbench");
  try{
    const c = await jget("/api/cases/" + cid);
    state.current = c;
    renderCase(c);
    document.getElementById("mainCol").scrollIntoView({behavior:"smooth", block:"start"});
  }catch(e){ toast("打开案例失败：" + e.message); }
}

