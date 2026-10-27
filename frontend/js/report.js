/* STR 报告：生成、62 项渲染、格式核对、修订、打印、XML */
/* ================= STR 报告 ================= */
async function genReport(source){
  const cid = source === "flow" ? state.flowCase : (state.current && state.current.case_id);
  const diag = source === "flow" ? state.flowDiag : state.workDiag;
  if(!cid) return toast("请先选择案例");
  if(!diag) return toast("请先完成研判");
  const btn = source === "flow" ? document.getElementById("btnStr") : null;
  if(btn){ btn.disabled = true; btn.innerHTML = '<span class="loading"></span> 生成中…'; }
  try{
    const rep = await jpost("/api/report/" + cid, {diagnosis: diag.ai_diagnosis});
    if(source === "flow"){ state.flowReport = rep; } else { state.report = rep; }
    openReport(rep);
    toast("STR 初稿已生成：62 项要素 + 中英双语正文");
  }catch(e){ alert("生成报告失败：" + errText(e)); }
  if(btn){ btn.disabled = false; btn.textContent = "⚡ 生成 STR 初稿"; }
}

function elementRows(rep, editable){
  let rows = "", cur = 0;
  rep.elements.forEach(e=>{
    if(e.part !== cur){ cur = e.part; rows += `<tr class="str-part"><td colspan="3">${esc(e.part_name)}</td></tr>`; }
    const tag = {
      system:'<span class="st auto">系统带出</span>',
      synthetic:'<span class="st syn">演示预填</span>',
      ai:'<span class="st ai">AI 生成</span>',
      manual:'<span class="st todo">待补充</span>',
      na:'<span class="st na">不适用</span>'
    }[e.source] || "";
    const edited = e.edited ? '<span class="edited-tag">人工修订</span>' : "";
    let cell;
    if(editable){
      const long = String(e.value).length > REPORT_CONFIG.longTextLength
        || REPORT_CONFIG.longTextItems.includes(e.no);
      // 待人工补充项：空值 + 红框 + 占位提示，与"请先修订标红项"的提示对应
      const todo = e.source === "manual" || String(e.value).trim() === "";
      const styleAttr = todo ? ' style="border-color:#fca5a5;background:#fff5f5;"' : "";
      const ph = todo ? ' placeholder="待专岗补充（官方代码集未接入，格式核对会提示）"' : "";
      cell = long
        ? `<textarea class="el-input" id="el-${e.no}" rows="2"${styleAttr}${ph}>${esc(e.value)}</textarea>`
        : `<input class="el-input" id="el-${e.no}" value="${esc(e.value)}"${styleAttr}${ph}>`;
    }else{
      cell = `${esc(e.value)}${tag}${edited}`;
    }
    rows += `<tr class="sr"><td class="sn">${e.no}</td><td class="sname">${esc(e.name)}</td><td>${cell}</td></tr>`;
  });
  const c = rep.counts;
  const partCounts = [1,2,3,4].map(p=>rep.elements.filter(e=>e.part===p).length);
  return `<div class="str-head">
      <div><div class="t">可疑交易报告要素对照表 · 银行业 ${rep.total} 项</div>
      <div class="s">依据：人民银行令〔2016〕第 3 号 附件《金融机构大额交易和可疑交易报告要素内容》—— 报告机构信息 ${partCounts[0]} ＋ 可疑主体信息 ${partCounts[1]} ＋ 报告基本信息 ${partCounts[2]} ＋ 交易信息 ${partCounts[3]}</div></div>
      <div class="str-cnt"><b>要素完成度 ${c.system + c.synthetic + c.ai} / ${rep.total}</b>
        <em class="c-auto">系统带出 ${c.system}</em><em class="c-syn">演示预填 ${c.synthetic}</em><em class="c-ai">AI 生成 ${c.ai}</em>${c.manual?`<em class="c-todo">待人工补充 ${c.manual}</em>`:""}<em class="c-na">本笔不适用 ${c.na}</em></div>
    </div>
    <div class="str-box"><table><tr><th style="width:44px;text-align:center;">编号</th><th style="width:220px;">要素名称</th><th>本期取值</th></tr>${rows}</table></div>
    <div class="str-note">三种来源：<b style="color:#4338ca">系统带出</b>（从客户信息 / 交易流水 / 规则引擎结论直接取数）· <b style="color:#0369a1">演示预填</b>（案例未采集的证件号、账号、地址等，按案例编号确定性生成合成值，非真实信息）· <b style="color:#7e22ce">AI 生成</b>（仅第 21、22 项判断性内容，须专岗逐项校验）。62 项中带判断性的只有 2 项，AI 的作用范围被严格限定在此；本报告全部数据仅用于演示，不构成合规依据。<br>口径说明：第 48 项交易金额为报告期内转入/存入与转出/支取的累计合计（双向流水分别计量，非净额头寸）；第 24 项可疑交易特征代码须按官方代码集由专岗补充，系统不做兜底填充（未接入官方代码集，空值会被格式核对拦截）。</div>`;
}

function renderFormatCheck(rep){
  const box = document.getElementById("formatCheck");
  const missing = rep.elements.filter(e=>String(e.value||"").trim()==="");
  const parts = new Set(rep.elements.map(e=>e.part));
  const [reqFrom, reqTo] = REPORT_CONFIG.requiredItems;
  const required = rep.elements.filter(e=>e.no>=reqFrom && e.no<=reqTo && String(e.value||"").trim()==="");
  const val = no => String((rep.elements.find(e=>e.no===no)||{}).value || "").trim();
  const clean = v => v.replace(/（合成）|\(合成\)/g, "").trim();
  const warnings = [];
  const amountNo = REPORT_CONFIG.amountItem;
  const amount = val(amountNo);
  if(amount && amount!=="不适用" && !/^\d+(\.\d{1,2})?$/.test(amount.replace(/,/g,"")))
    warnings.push(`第${amountNo}项交易金额非数字`);
  REPORT_CONFIG.dateItems.forEach(no=>{
    const v = val(no);
    if(v && !/不适用|未销户|^—/.test(v) && !/^\d{4}[-/]\d{2}([-/]\d{2})?/.test(v))
      warnings.push(`第${no}项日期格式异常`);
  });
  const idNo = clean(val(REPORT_CONFIG.idItem));
  if(idNo && idNo!=="不适用" && !idNo.includes("*")
     && !new RegExp(REPORT_CONFIG.idPattern).test(idNo))
    warnings.push(`第${REPORT_CONFIG.idItem}项证件号码格式异常`);
  const org = val(REPORT_CONFIG.orgItem);
  if(org && !new RegExp(`^\\d{${REPORT_CONFIG.orgCodeLength}}$`).test(org))
    warnings.push(`第${REPORT_CONFIG.orgItem}项报告机构编码应为 ${REPORT_CONFIG.orgCodeLength} 位数字`);
  const ok = rep.total===REPORT_CONFIG.totalItems && parts.size===REPORT_CONFIG.partCount
    && missing.length===0 && required.length===0 && warnings.length===0;
  box.className = "format-check" + (ok?"":" warn");
  box.innerHTML = `<b>${ok?"✓ 报告结构核对通过":"⚠ 报告结构需核对"}</b>　依据：人民银行令〔2016〕第 3 号附件
    <div class="fc-row">
      <span>要素总数：${rep.total} / ${REPORT_CONFIG.totalItems}</span>
      <span>四部分：${parts.size} / ${REPORT_CONFIG.partCount}</span>
      <span>空值项：${missing.length}</span>
      <span>第 ${reqFrom}–${reqTo} 项必填空缺：${required.length}</span>
      <span>字段格式异常：${warnings.length}</span>
      <span>报送时限：${esc(rep.filing_deadline || "—")}</span>
    </div>
    ${warnings.length?`<div style="margin-top:3px;font-size:11.5px;color:#92400e;">${warnings.join("；")}</div>`:""}
    <div style="margin-top:3px;font-size:11.5px;color:${ok?"#166534":"#92400e"};">${ok?"62 项齐全、四部分完整、必填项无空值、字段格式检查通过。":"请先修订标红项后再签字。"} 当前版本尚未接入 CAMLMAC XSD 与官方代码集校验，正式报送前必须补齐；现阶段报告仅为演示草稿。${rep.deadline_note?` 法定时限：${esc(rep.deadline_note)}。`:""}</div>`;
}

function openReport(rep){
  if(rep.report_no !== state.signReportNo){
    state.signatures = {operator:null, reviewer:null, approver:null};
    state.signed = false;
    state.submitted = false;
    state.receiptNo = null;
    state.submittedAt = null;
    state.editLog = [];
    state.version = 1;
    state.returnLog = [];
    state.authChannel = "branch";
    state.authPending = null;
    state.previewMode = false;
    state.archiveMode = false;
    state.correctionOf = null;
    state.editMode = true;  // 初稿生成后默认进入可编辑态，人工先改再确认
    state.signReportNo = rep.report_no;
  }
  state.report = rep;
  document.getElementById("docTitle").textContent = "可疑交易报告（STR）";
  document.getElementById("docMeta").textContent =
    `报告编号 ${rep.report_no} · 关联案例 ${rep.case_id} · 银行业可疑交易报告 62 项要素 · 依据《反洗钱法》《金融机构大额交易和可疑交易报告管理办法》报送`;
  renderFormatCheck(rep);
  renderReportBody();
  reportTab("tbl");
  document.getElementById("reportMask").classList.add("show");
}

function renderReportBody(){
  const rep = state.report;
  if(!rep) return;
  document.getElementById("docMeta").textContent =
    `报告编号 ${rep.report_no} · 关联案例 ${rep.case_id} · 版本 v${state.version}${state.version>1?"（人工修订）":"（AI 初稿）"} · 62 项要素 · 依据《反洗钱法》《金融机构大额交易和可疑交易报告管理办法》`;
  document.getElementById("docTbl").innerHTML = elementRows(rep, state.editMode);
  if(state.editMode){
    document.getElementById("docCn").innerHTML = `<textarea class="el-input" id="cnEdit" rows="12">${esc(rep.cn)}</textarea>`;
    document.getElementById("docEn").innerHTML = `<textarea class="el-input" id="enEdit" rows="12">${esc(rep.en)}</textarea>`;
  }else{
    document.getElementById("docCn").textContent = rep.cn;
    document.getElementById("docEn").textContent = rep.en;
  }
  renderSignBlock();
  renderEditLog();
  renderActionState();
}

function reportStage(){
  if(state.submitted) return "submitted";
  if(state.signed) return "approved";
  if(state.signatures.reviewer) return "pending_approval";
  if(state.signatures.operator) return "pending_review";
  return "draft";
}

function renderEditLog(){
  const el = document.getElementById("editLog");
  if(!el) return;
  if(!state.editLog.length){ el.innerHTML = ""; return; }
  const rows = state.editLog.slice(-30).reverse().map(x=>
    `<div class="er"><span>第 ${x.no} 项</span>
      <span><span class="old">${esc(x.old)}</span> → <span class="new">${esc(x.new)}</span></span>
      <span class="who">${esc(x.who)} · ${x.time}</span></div>`).join("");
  el.innerHTML = `<div class="et">人工修订记录（${state.editLog.length} 处 · 当前版本 v${state.version}）</div>${rows}`;
}

function renderSignBlock(){
  const roles = SIGN_ROLES.map(r=>{
    const s = state.signatures[r.key];
    if(!s){
      return `<div class="sign-row"><span class="role">${r.title}人</span><span class="who pending">待授权</span>
        <span class="meta">${r.name} · ${r.id} · ${r.post}</span><span class="meta">尚未签字</span></div>`;
    }
    return `<div class="sign-row"><span class="role">${r.title}人</span><span class="who done">${s.name}</span>
      <span class="meta">工号 ${s.id} · 岗位 ${s.post}</span><span class="meta">${sigMeta(s)}</span></div>`;
  }).join("");
  const status = state.submitted
    ? `已报送 <b class="sent">${esc(state.receiptNo)}</b> · ${esc(state.submittedAt)}`
    : state.signed
      ? `<b class="signed">已签字待报送</b>（签字不等于提交，请点「提交报送」）`
      : `<b class="draft">草稿（未签字）</b>`;
  const lastReturn = state.returnLog[state.returnLog.length-1];
  const returnNote = lastReturn
    ? `<div class="sign-status" style="color:#92400e;">最近退回：${esc(lastReturn.role)}岗 ${esc(lastReturn.by)} · ${esc(lastReturn.time)}${lastReturn.reason?`<br>退回原因：${esc(lastReturn.reason)}`:""}（退回后需重新授权）</div>`
    : "";
  document.getElementById("signBlock").innerHTML =
    `<div class="sign-title">签字与授权留痕 ${state.signed?'<span class="pill green" style="margin-left:8px;">三级授权完成</span>':'<span class="pill amber" style="margin-left:8px;">待完成</span>'}</div>
     <div class="sign-status">报告状态：${status}</div>${returnNote}${roles}`;
}

function renderActionState(){
  const stage = reportStage();
  const canEdit = stage === "draft";
  document.getElementById("btnEdit").style.display = canEdit ? "" : "none";
  document.getElementById("btnEdit").textContent = state.editMode ? "取消编辑" : "✎ 编辑修订";
  document.getElementById("btnSaveEdit").style.display = state.editMode ? "" : "none";

  const sb = document.getElementById("docSignBtn");
  sb.style.display = (stage === "submitted" || stage === "approved") ? "none" : "";
  sb.disabled = false;
  sb.textContent = stage === "draft" ? "确认初稿 · 进入签字授权"
    : stage === "pending_review" ? "复核岗签字 →"
    : stage === "pending_approval" ? "审批岗签字 →" : "已完成签字授权";

  const sub = document.getElementById("docSubmitBtn");
  sub.style.display = (stage === "approved" || stage === "submitted") ? "" : "none";
  sub.disabled = stage === "submitted";
  sub.textContent = stage === "submitted" ? `已报送 · ${state.receiptNo}` : "提交报送 →";

  const statusEl = document.getElementById("docStatus");
  const draftPerm = state.editMode
    ? "编辑权限：经办岗 · 编辑模式已开启，修改后先点「保存修订」，再点「经办确认」"
    : "编辑权限：经办岗 · 点「编辑修订」进入修改；经办签字后内容锁定";
  const map = {
    draft: ["draft", "当前状态：草稿 · 初稿可直接修改" + (state.correctionOf ? ` · 更正报告（原回执 ${state.correctionOf}）` : ""), draftPerm],
    pending_review: ["locked", "当前状态：已由经办签字 · 待复核", "内容已锁定；复核岗可签字通过，或退回经办修改后再重走签字"],
    pending_approval: ["locked", "当前状态：经办、复核已签 · 待审批", "内容已锁定；审批岗可签字通过，或退回修改后再重走签字"],
    approved: ["approved", "当前状态：三级授权完成 · 已签字待报送", "内容锁定；签字不等于提交，需单独提交报送"],
    submitted: ["sent", `当前状态：已报送 · 回执 ${esc(state.receiptNo)}`, `提交时间：${esc(state.submittedAt)}；报告不可再修改`]
  }[stage];
  statusEl.className = "doc-status " + map[0];
  statusEl.innerHTML = `${map[1]}<span class="perm">${map[2]}</span>`;

  document.getElementById("docActionHint").textContent = stage === "submitted"
    ? "已提交报送，回执与授权记录已归档"
    : stage === "approved"
      ? "报告已定稿。签字不等于提交，请点「提交报送」完成独立报送动作"
      : stage === "draft"
        ? (state.editMode
            ? "编辑模式已开启：直接修改要素或中英正文，改完点「保存修订」，再点「经办确认 · 进入签字授权」"
            : "初稿尚未确认：点「编辑修订」修改，保存后再进入签字授权")
        : "内容已锁定；请在签字授权中选择通过或退回修改";

  document.getElementById("docBackAuth").style.display = "none";
  if(state.archiveMode){
    document.getElementById("btnEdit").style.display = "none";
    sb.style.display = "none";
    sub.style.display = "none";
    statusEl.className = "doc-status sent";
    statusEl.innerHTML = `已报送归档 · 只读
      <span class="perm">历史报送记录，含回执号、报告版本、三级签字与报告快照；不可修改</span>`;
    document.getElementById("docActionHint").textContent = "台账归档记录：仅供查阅与审计，不可修改";
    return;
  }
  if(state.previewMode){
    document.getElementById("btnEdit").style.display = "none";
    sb.style.display = "none";
    sub.style.display = "none";
    document.getElementById("docBackAuth").style.display = "";
    statusEl.className = "doc-status locked";
    statusEl.innerHTML = `预览模式 · 只读查看报告内容与已签记录
      <span class="perm">请核对经办填写内容、报告正文与已签记录是否一致；无误后返回授权完成本级签字，发现问题可退回修改</span>`;
    document.getElementById("docActionHint").textContent = "预览模式：只读，不可修改；核对无误后点「返回签字授权」";
  }
}

function toggleEdit(){
  if(reportStage() !== "draft"){
    toast("内容已锁定：需复核或审批岗退回后才能修改");
    return;
  }
  state.editMode = !state.editMode;
  renderReportBody();
  if(state.editMode) toast("已进入编辑模式（经办岗草稿阶段）");
}

function saveEdits(){
  const rep = state.report;
  if(!rep) return;
  const who = SIGN_ROLES[0].name + "（" + SIGN_ROLES[0].id + "）";
  const time = isoNow();
  let changed = 0;
  rep.elements.forEach(e=>{
    const el = document.getElementById("el-"+e.no);
    if(!el) return;
    const v = el.value;
    if(v !== e.value){
      state.editLog.push({no:e.no, name:e.name, old:e.value, new:v, who, time});
      e.value = v; e.edited = true; changed++;
    }
  });
  const cn = document.getElementById("cnEdit");
  const en = document.getElementById("enEdit");
  if(cn && cn.value !== rep.cn){
    state.editLog.push({no:"正文", name:"报告正文（中）", old:rep.cn, new:cn.value, who, time});
    rep.cn = cn.value; changed++;
  }
  if(en && en.value !== rep.en){
    state.editLog.push({no:"EN", name:"Report (EN)", old:rep.en, new:en.value, who, time});
    rep.en = en.value; changed++;
  }
  if(changed) state.version++;
  state.editMode = false;
  renderReportBody();
  renderFormatCheck(rep);
  toast(changed ? `已保存 ${changed} 处修订，版本升为 v${state.version}；请核对后点「确认初稿」` : "未检测到修改");
}

function hasUnsavedEdits(){
  const rep = state.report;
  if(!rep) return false;
  const fieldChanged = rep.elements.some(e=>{
    const el = document.getElementById("el-"+e.no);
    return el && el.value !== e.value;
  });
  const cn = document.getElementById("cnEdit");
  const en = document.getElementById("enEdit");
  return fieldChanged || (cn && cn.value !== rep.cn) || (en && en.value !== rep.en);
}

function reportTab(l){
  ["tbl","cn","en"].forEach(k=>{
    document.getElementById("lt-"+k).classList.toggle("on", k===l);
    document.getElementById("doc"+k.charAt(0).toUpperCase()+k.slice(1)).style.display = (k===l)?"block":"none";
  });
}
function printReport(){
  if(!state.report) return;
  if(state.editMode){ toast("请先保存修订再打印"); return; }
  reportTab("tbl");
  window.print();
  toast("已调起打印预览（A4，含签字授权区）");
}

function exportReportXml(){
  const rep = state.report;
  if(!rep) return;
  const x = v => String(v==null?"":v).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  const partName = {1:"ReportInfo",2:"SubjectInfo",3:"ReportBaseInfo",4:"TransactionInfo"};
  let xml = `<?xml version="1.0" encoding="UTF-8"?>\n`
    + `<!-- 清源AML 演示报文草稿：按 3 号令附件 62 项要素组织；未经 CAMLMAC XSD 校验，不得直接用于正式报送 -->\n`
    + `<Report reportNo="${x(rep.report_no)}" caseId="${x(rep.case_id)}" generatedAt="${x(rep.generated_at)}">\n`;
  [1,2,3,4].forEach(p=>{
    xml += `  <${partName[p]}>\n`;
    rep.elements.filter(e=>e.part===p).forEach(e=>{
      xml += `    <Element no="${e.no}" name="${x(e.name)}" source="${x(e.source)}">${x(e.value)}</Element>\n`;
    });
    xml += `  </${partName[p]}>\n`;
  });
  const s = state.signatures || {};
  if(s.operator){
    const line = [s.operator,s.reviewer,s.approver].filter(Boolean).map(sigMeta).join("｜");
    xml += `  <AuditInfo>${x(line)}</AuditInfo>\n`;
  }
  xml += `</Report>\n`;
  const blob = new Blob([xml], {type:"application/xml;charset=utf-8"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${rep.report_no}_要素草稿.xml`;
  a.click(); URL.revokeObjectURL(a.href);
  toast("已导出报文草稿：XML 是给系统对接用的源码，用记事本打开即为此形态；未经 XSD 校验，不可直接报送");
}
function closeReport(){
  document.getElementById("reportMask").classList.remove("show");
  if(state.archiveMode){ state.archiveMode = false; return; }
  if(state.previewMode){
    state.previewMode = false;
    renderSignRoles();
    document.getElementById("signMask").classList.add("show");
    return;
  }
  // 全流程演示第 6 步：在报告弹层里签完字回到 flow 页，签字区必须刷新，
  // 否则页面还显示"待授权 / 报告尚未完成三级授权"（演示现场会翻车）
  if(state.flowStage >= 6 && document.getElementById("page-flow").classList.contains("active")){
    flowAuth();
  }
}

