/* 上报台账：列表、筛选、导出、归档、更正、报送写入 */
/* ================= 上报台账 ================= */
async function loadSubmissions(){
  const body = document.getElementById("subBody");
  if(!body) return;
  body.innerHTML = '<div style="padding:18px;"><span class="loading"></span></div>';
  try{
    const d = await jget("/api/submissions");
    // 只读演示站写不了库，但流程要能走完：本次会话内的"演示送达"记录并入列表并标注
    state.submissions = [...(state.demoSubmissions || []), ...(d.submissions || [])];
    const list = state.submissions;
    // 今日计数按 ISO 日期比较（写入侧已统一为 YYYY-MM-DD HH:MM:SS；
    // 历史上两种格式混存，字符串前缀比较会漏计）
    const today = isoToday();
    const normDate = s => (s||"").slice(0,10).replace(/\//g,"-");
    const todayCount = list.filter(x=>normDate(x.submitted_at) === today).length;
    const cases = new Set(list.map(x=>x.case_id)).size;
    document.getElementById("subStats").innerHTML = `
      <div class="stat"><div class="lbl">累计上报</div><div class="num">${list.length}<small> 条</small></div></div>
      <div class="stat"><div class="lbl">今日上报</div><div class="num">${todayCount}<small> 条</small></div></div>
      <div class="stat"><div class="lbl">覆盖案例</div><div class="num">${cases}<small> 条</small></div></div>
      <div class="stat"><div class="lbl">最近回执</div><div class="num" style="font-size:14px;word-break:break-all;">${list[0]?esc(list[0].receipt_no):"—"}</div></div>`;
    renderSubmissions();
  }catch(e){
    body.innerHTML = `<div class="hit-box" style="margin:18px;">加载失败：${esc(e.message)}</div>`;
  }
}

function filteredSubmissions(){
  const kw = (document.getElementById("subSearch")?.value || "").trim().toLowerCase();
  const from = document.getElementById("subFrom")?.value || "";
  const to = document.getElementById("subTo")?.value || "";
  return (state.submissions||[]).filter(x=>{
    const hay = [x.receipt_no,x.report_no,x.case_id,x.case_title,x.customer,x.operator,x.reviewer,x.approver]
      .join(" ").toLowerCase();
    if(kw && !hay.includes(kw)) return false;
    const d = (x.submitted_at||"").slice(0,10).replace(/\//g,"-");
    if(from && d < from) return false;
    if(to && d > to) return false;
    return true;
  });
}

function renderSubmissions(){
  const body = document.getElementById("subBody");
  if(!body) return;
  const list = filteredSubmissions();
  const cnt = document.getElementById("subFilterCount");
  if(cnt) cnt.textContent = `筛选 ${list.length} / ${(state.submissions||[]).length} 条`;
  if(!list.length){
    body.innerHTML = '<div class="miss-box" style="margin:18px;">没有符合条件上报记录。</div>';
    return;
  }
  const rows = list.map(x=>{
    const d = (x.submitted_at||"").slice(0,10).replace(/\//g,"-");
    const onTime = x.filing_deadline ? (d && d <= x.filing_deadline ? "按期" : "逾期") : "—";
    const openAttr = x.demo ? "" : ` class="clickable" onclick="openArchivedSubmission(${x.id})"`;
    const tail = x.demo
      ? `<td style="font-size:11.5px;color:var(--muted);">演示记录<br>未入库</td>`
      : `<td onclick="event.stopPropagation()" style="white-space:nowrap;">
        <button class="btn ghost small" onclick="openArchivedSubmission(${x.id})">查看</button>
        <button class="btn ghost small" onclick="correctSubmission(${x.id})">更正</button></td>`;
    return `<tr${openAttr}>
      <td style="font-family:monospace;font-size:11.5px;">${esc(x.receipt_no)}${x.supersedes_receipt?`<br><span style="color:var(--muted);">原 ${esc(x.supersedes_receipt)}</span>`:""}</td>
      <td style="font-family:monospace;font-size:11.5px;">${esc(x.report_no)}</td>
      <td>${esc(x.case_id)}</td><td>${esc(x.customer)}</td>
      <td>${esc(x.submitted_at)}</td>
      <td>${esc(x.operator)}</td><td>${esc(x.reviewer)}</td><td>${esc(x.approver)}</td>
      <td style="text-align:center;">v${x.version}</td>
      <td><span class="pill ${x.demo ? "blue" : x.status==="更正报告"?"blue":x.status==="已更正"?"amber":"green"}">${esc(x.status)}</span></td>
      <td style="font-size:12px;color:${onTime==="逾期"?"var(--red)":"var(--muted)"};">${onTime}</td>
      ${tail}</tr>`;
  }).join("");
  const demoBanner = (state.demoSubmissions || []).length
    ? `<div class="note-bar warn" style="margin-bottom:10px;">只读演示环境：标注「演示送达（未入库）」的是本地模拟回执——
       未连接人行报文系统、未写入业务台账，刷新页面即消失；接入网关与机构证书签名后为正式报送。</div>`
    : "";
  body.innerHTML = `${demoBanner}<div style="overflow-x:auto;"><table class="grid"><thead><tr>
    <th>回执号</th><th>报告编号</th><th>案例</th><th>客户</th><th>报送时间</th>
    <th>经办</th><th>复核</th><th>审批</th><th>版本</th><th>状态</th><th>时限</th><th></th>
    </tr></thead><tbody>${rows}</tbody></table></div>`;
}

function clearSubFilters(){
  ["subSearch","subFrom","subTo"].forEach(id=>{ const el=document.getElementById(id); if(el) el.value=""; });
  renderSubmissions();
}

function exportSubmissions(){
  const list = filteredSubmissions();
  if(!list.length){ toast("当前筛选结果为空"); return; }
  const head = ["回执号","报告编号","案例编号","案例名称","客户","报送时间","经办","复核","审批","版本","状态","报送时限","原回执"];
  const escCsv = v => `"${String(v==null?"":v).replace(/"/g,'""')}"`;
  const lines = [head.map(escCsv).join(",")].concat(list.map(x=>[
    x.receipt_no,x.report_no,x.case_id,x.case_title,x.customer,x.submitted_at,
    x.operator,x.reviewer,x.approver,"v"+x.version,x.status,x.filing_deadline,x.supersedes_receipt
  ].map(escCsv).join(",")));
  const blob = new Blob(["\ufeff"+lines.join("\r\n")], {type:"text/csv;charset=utf-8"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `清源AML_上报台账_${new Date().toISOString().slice(0,10)}.csv`;
  a.click(); URL.revokeObjectURL(a.href);
  toast(`已导出 ${list.length} 条台账记录`);
}

async function openArchivedSubmission(id){
  try{
    const d = await jget("/api/submissions/" + id);
    if(!d.report || !d.report.elements){ toast("该记录缺少报告快照"); return; }
    state.report = d.report;
    state.signatures = d.audit && d.audit.operator ? d.audit : {operator:null, reviewer:null, approver:null};
    state.signed = true; state.submitted = true;
    state.receiptNo = d.receipt_no; state.submittedAt = d.submitted_at;
    state.version = d.version || 1; state.editMode = false;
    state.editLog = d.edit_log || []; state.returnLog = d.return_log || [];
    state.previewMode = false; state.archiveMode = true;
    state.correctionOf = null;
    state.signReportNo = d.report.report_no;
    openReport(d.report);
  }catch(e){ toast("打开归档失败：" + errText(e)); }
}

async function correctSubmission(id){
  try{
    const d = await jget("/api/submissions/" + id);
    if(!d.case_id){ toast("记录缺少案例编号"); return; }
    const rep = await jpost("/api/report/" + d.case_id, {});
    openReport(rep);
    state.correctionOf = d.receipt_no;
    renderActionState();
    toast(`已基于原回执 ${d.receipt_no} 生成更正草稿，请修订后重新走三级授权`);
  }catch(e){ toast("生成更正草稿失败：" + errText(e)); }
}

function submissionPayload(){
  const rep = state.report, s = state.signatures;
  const brief = x => x ? `${x.name} ${x.id}` : "";
  return {
    report_no: rep.report_no,
    // 回执号由服务端生成（RX-日期-序号），客户端不再随机生成：随机碰撞曾把
    // 第二份报告静默并进第一条台账记录
    case_id: rep.case_id, case_title: rep.title,
    customer: (rep.meta||{}).customer || "",
    submitted_at: state.submittedAt || isoNow(), version: state.version,
    operator: brief(s.operator), reviewer: brief(s.reviewer), approver: brief(s.approver),
    audit: s, report: rep,
    edit_log: state.editLog || [], return_log: state.returnLog || [],
    supersedes_receipt: state.correctionOf || "",
    filing_deadline: rep.filing_deadline || "",
    destination: "CAMLMAC",
    status: state.correctionOf ? "更正报告" : "已报送"
  };
}

async function saveSubmission(){
  // 返回写入的台账记录（含服务端回执号）；失败返回 null，由调用方决定是否重试
  const rep = state.report, s = state.signatures;
  if(!rep || !(s && s.operator && s.reviewer && s.approver)) return null;
  try{
    const d = await jpost("/api/submissions", submissionPayload());
    if(document.getElementById("page-reports").classList.contains("active")) loadSubmissions();
    return d;
  }catch(e){
    console.error(e);
    toast("台账写入失败：" + errText(e));
    return null;
  }
}

/* ================= 审计链（防篡改留痕） ================= */
async function verifyAuditChain(){
  const box = document.getElementById("auditVerifyBox");
  box.style.display = "block";
  box.className = "miss-box";
  box.innerHTML = '<span class="loading"></span> 正在全链重放校验（逐条重算 SHA256 并核对链接）…';
  try{
    const d = await jget("/api/audit/verify");
    if(d.ok){
      box.className = "hit-box"; box.style.borderColor = "#bbf7d0";
      box.innerHTML = `<b>✓ 审计链完整</b>：共 ${d.records} 条记录，全部通过哈希链重放校验（无篡改、无删改）。
        链头哈希 <span style="font-family:monospace;font-size:11px;word-break:break-all;">${esc(d.head_hash)}</span><br>
        <span style="font-size:11.5px;color:var(--muted);">每条记录的哈希覆盖：序号|时间戳|操作人|动作|对象|内容|上一条哈希——改任何一处，其后整条链全部失效；数据库触发器另拒绝 UPDATE/DELETE。</span>`;
    }else{
      box.className = "hit-box"; box.style.borderColor = "#fca5a5";
      box.innerHTML = `<b style="color:var(--red);">✗ 审计链校验失败</b>：第 ${esc(String(d.broken_seq))} 条 ${esc(d.reason||"")}。链在此处断裂，其后所有记录不可信，应立即核查。`;
    }
  }catch(e){
    box.className = "hit-box"; box.style.borderColor = "#fca5a5";
    box.innerHTML = "校验请求失败：" + esc(e.message);
  }
}

function toggleAuditPanel(){
  const p = document.getElementById("auditPanel");
  p.style.display = p.style.display === "none" ? "block" : "none";
  if(p.style.display !== "none" && !state.auditLoaded) loadAuditLog(0);
}

async function loadAuditLog(offset){
  offset = Math.max(0, offset || 0);
  state.auditOffset = offset;
  const params = [];
  const add = (k, v) => { if(v) params.push(k + "=" + encodeURIComponent(v)); };
  add("actor", document.getElementById("auditActor").value.trim());
  add("action", document.getElementById("auditAction").value);
  add("object_id", document.getElementById("auditObject").value.trim());
  add("date_from", document.getElementById("auditFrom").value);
  add("date_to", document.getElementById("auditTo").value);
  params.push("limit=50", "offset=" + offset);
  const body = document.getElementById("auditBody");
  body.innerHTML = '<tr><td colspan="7"><span class="loading"></span></td></tr>';
  try{
    const d = await jget("/api/audit?" + params.join("&"));
    state.auditLoaded = true;
    const sel = document.getElementById("auditAction");
    if(sel.options.length <= 1){
      (d.actions || []).forEach(a=>{
        const o = document.createElement("option"); o.value = a; o.textContent = a; sel.appendChild(o);
      });
    }
    document.getElementById("auditCount").textContent =
      `共 ${d.total} 条 · 第 ${offset + 1}–${offset + d.count} 条`;
    if(!d.records.length){
      body.innerHTML = '<tr><td colspan="7" style="color:var(--muted);">没有符合条件的审计记录。</td></tr>';
      return;
    }
    body.innerHTML = d.records.map(r=>`<tr>
      <td style="font-family:monospace;">${r.seq}</td>
      <td style="font-family:monospace;font-size:11.5px;">${esc(r.occurred_at)}</td>
      <td>${esc(r.actor)}</td>
      <td>${esc(r.action)}</td>
      <td style="font-family:monospace;font-size:11.5px;">${esc(r.object_type)}<br>${esc(r.object_id||"—")}</td>
      <td style="font-size:12px;max-width:300px;word-break:break-all;">${esc(JSON.stringify(r.detail||{}).slice(0,160))}</td>
      <td style="font-family:monospace;font-size:10.5px;color:var(--muted);word-break:break-all;">${esc((r.record_hash||"").slice(0,16))}…</td>
    </tr>`).join("");
  }catch(e){
    body.innerHTML = `<tr><td colspan="7" style="color:var(--red);">加载失败：${esc(e.message)}</td></tr>`;
  }
}

