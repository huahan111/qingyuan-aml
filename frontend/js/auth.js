/* 授权状态机：签字确认、三级授权、预览、退回、提交报送 */
function startSign(){
  if(state.editMode){
    if(hasUnsavedEdits()){ toast("有未保存的修改，请先点「保存修订」再确认初稿"); return; }
    state.editMode = false;
    renderReportBody();
  }
  const stage = reportStage();
  if(stage === "approved" || stage === "submitted"){ toast("报告已完成三级授权"); return; }
  if(stage === "draft") renderSignConfirm();
  else renderSignRoles();
  document.getElementById("signMask").classList.add("show");
}
function closeSign(){ state.authPending = null; document.getElementById("signMask").classList.remove("show"); }

function finishAuth(){
  closeSign();
  const shown = document.getElementById("reportMask").classList.contains("show");
  if(!shown) openReport(state.report);
}

/* 复核/审批：先只读预览报告与已签记录，再决定通过或退回 */
function previewReportForAuth(){
  state.previewMode = true;
  closeSign();
  openReport(state.report);
  toast("预览模式：只读核对报告内容与已签记录");
}
function backToAuth(){
  state.previewMode = false;
  closeReport();
  renderSignRoles();
  document.getElementById("signMask").classList.add("show");
}

/* 签字完成 ≠ 已提交：提交是独立动作，需二次确认 */
function submitReport(){
  if(state.readOnly){ toast("当前为只读演示环境，不能提交报送"); return; }
  if(!state.signed){ toast("请先完成三级签字授权"); return; }
  if(state.submitted){ toast("报告已提交，回执 " + state.receiptNo); return; }
  document.getElementById("signMeta").textContent =
    `报告编号 ${state.report.report_no} · 提交后不可撤回`;
  document.getElementById("signBody").innerHTML = `
    <div class="confirm-box">
      <b>确认提交报送至人民银行反洗钱监测分析中心？</b><br>
      当前报告已完成三级授权，状态为「已签字待报送」。提交后不可撤回，5 个工作日报送时限监控开始，
      回执编号写入报告归档。
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;">
      <button class="btn ghost" onclick="closeSign()">取消</button>
      <button class="btn" onclick="doSubmitReport()">确认提交报送</button>
    </div>`;
  document.getElementById("signMask").classList.add("show");
}
async function doSubmitReport(){
  // 先写台账成功、再置「已报送」状态：写库失败时报告保持"已签字待报送"，
  // 提交按钮仍可用可重试（此前先置状态后异步写库，失败会把报告永久卡在
  // "已报送"且台账无记录，且没有任何重试入口）
  const saved = await saveSubmission();
  if(!saved){
    closeSign(); renderActionState();
    toast("报送未完成：台账写入失败，报告仍为「已签字待报送」，可重新提交");
    return;
  }
  state.submitted = true;
  state.receiptNo = saved.receipt_no;
  state.submittedAt = saved.submitted_at || isoNow();
  renderSignBlock();
  renderActionState();
  closeSign();
  toast(`已提交报送 · 回执 ${state.receiptNo}`);
  if(state.flowStage >= 6 && document.getElementById("page-flow").classList.contains("active")){
    flowAuth();
  }
}

function renderSignConfirm(){
  document.getElementById("signMeta").textContent =
    `报告编号 ${state.report.report_no} · 关联案例 ${state.report.case_id} · 签字后不可修改`;
  document.getElementById("signBody").innerHTML = `
    <div class="confirm-box">
      <b>是否确认报告内容真实、准确、完整？</b><br>
      确认后将进入三级授权：经办人 → 复核人 → 审批人。每一级都必须选择授权方式（指纹 / 人脸 / 授权卡 / 通行密钥），
      姓名、工号、岗位编号、授权方式与时间会写入报告并留痕，责任人明确可追溯。
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;">
      <button class="btn ghost" onclick="closeSign()">返回修改</button>
      <button class="btn" onclick="renderSignRoles()">确认，进入授权 →</button>
    </div>`;
}

function lastSignedKey(){
  for(const k of ["approver","reviewer","operator"]) if(state.signatures[k]) return k;
  return null;
}

function sigMeta(s){
  return `${s.channel?s.channel+" · ":""}${s.method}${s.device?" · "+s.device:""}${s.score?" · "+s.score:""} · ${s.time}`;
}

function renderSignRoles(){
  const meta = document.getElementById("signMeta");
  const stage = reportStage();
  meta.textContent = `报告编号 ${state.report.report_no} · 当前状态：${stage==="draft"?"草稿":stage==="pending_review"?"待复核":"待审批"} · 按经办 / 复核 / 审批顺序授权`;
  const channel = AUTH_CHANNELS.find(c=>c.key===state.authChannel) || AUTH_CHANNELS[0];
  const channelRow = `<div class="channel-row">授权通道：
    ${AUTH_CHANNELS.map(c=>`<span class="channel-tab ${c.key===state.authChannel?"on":""}" onclick="setAuthChannel('${c.key}')">${c.name}</span>`).join("")}
    <span style="font-size:11.5px;color:var(--muted);">网点优先指纹；移动端人脸/手机指纹；OA 走通行密钥</span></div>`;
  const roles = SIGN_ROLES.map((r,i)=>{
    const s = state.signatures[r.key];
    const prevDone = i===0 || !!state.signatures[SIGN_ROLES[i-1].key];
    if(s){
      const isLast = lastSignedKey() === r.key && !state.submitted;
      return `<div class="role-card done"><h4>${i+1}. ${r.title}岗 <span class="pill green">已授权</span></h4>
        <div class="kvline">${s.name} · 工号 ${s.id} · 岗位 ${s.post}<br>${sigMeta(s)}</div>
        ${isLast?`<div style="margin-top:8px;"><button class="method-btn" onclick="withdrawSignature('${r.key}')">撤回本级签字</button></div>`:""}</div>`;
    }
    if(!prevDone){
      return `<div class="role-card locked"><h4>${i+1}. ${r.title}岗 <span class="pill gray">等待上一级</span></h4>
        <div class="kvline">请先完成${SIGN_ROLES[i-1].title}岗授权。</div></div>`;
    }
    // 鉴权模式：非本角色登录时锁定本级签字入口
    if(AUTH_STATE.required && (!AUTH_STATE.user || AUTH_STATE.user.role !== r.key)){
      const cur = AUTH_STATE.user ? `当前登录：${AUTH_STATE.user.role_name} · ${AUTH_STATE.user.name}` : "当前未登录";
      return `<div class="role-card locked"><h4>${i+1}. ${r.title}岗 <span class="pill gray">需${r.title}角色登录</span></h4>
        <div class="kvline">鉴权模式下谁登录谁签字——${cur}。请退出后以「${r.title}」角色账号登录再签本级。</div></div>`;
    }
    if(state.authPending && state.authPending.key === r.key){
      return bioCard(r, channel);
    }
    const prevSig = i>0 ? state.signatures[SIGN_ROLES[i-1].key] : null;
    const prevInfo = prevSig
      ? `<div class="kvline" style="background:#f8fafc;border-radius:6px;padding:6px 9px;">上一级 ${SIGN_ROLES[i-1].title}岗已签：${prevSig.name} · ${prevSig.id} · ${sigMeta(prevSig)}</div>`
      : "";
    return `<div class="role-card"><h4>${i+1}. ${r.title}岗 <span class="pill amber">待授权</span></h4>
      <div class="kvline">${r.name} · 工号 ${r.id} · 岗位 ${r.post}　${r.desc}</div>
      ${prevInfo}
      <div class="method-btns">
        ${channel.methods.map(m=>`<button class="method-btn" onclick="beginAuth('${r.key}','${m}')">${m}</button>`).join("")}
      </div>
      ${i>0?`<div style="margin-top:9px;display:flex;gap:8px;flex-wrap:wrap;">
        <button class="method-btn" style="border-color:#93c5fd;color:var(--primary);" onclick="previewReportForAuth()">预览报告内容${i===1?"（含经办签字）":"（含经办、复核签字）"}</button>
        <button class="method-btn" style="border-color:#fcd34d;color:#92400e;" onclick="returnForRevision('${r.key}')">发现问题 · 退回经办修改</button>
      </div>`:""}
      </div>`;
  }).join("");
  const allDone = SIGN_ROLES.every(r=>state.signatures[r.key]);
  document.getElementById("signBody").innerHTML = (allDone?"":channelRow) + roles + (allDone
    ? `<div class="confirm-box" style="background:#f0fdf4;border-color:#86efac;color:#166534;">
        ✓ 三级授权完成。经办、复核、审批的姓名 / 工号 / 岗位 / 授权方式 / 时间已写入报告并留痕。
       </div>
       <div style="margin-top:12px;display:flex;gap:10px;">
         <button class="btn" onclick="finishAuth()">完成，返回报告</button>
       </div>`
    : `<div style="font-size:11.5px;color:var(--muted);margin-top:6px;">演示环境模拟设备采集与比对；真实系统由指纹仪 / 摄像头 / 统一身份认证返回结果，不接受手工点选。</div>
       <div style="margin-top:10px;"><button class="btn ghost small" onclick="closeSign()">暂不授权，关闭</button></div>`);
}

function bioCard(r, channel){
  const p = state.authPending;
  const isFace = p.method === "人脸识别";
  const dev = (BIO_DEVICE[p.channel] || {})[p.method] || {device:"—", score:"—"};
  let status, cls = "", actions;
  if(p.step === "fail"){
    cls = "bio-fail";
    status = `比对未通过（相似度 ${p.failScore}），请重新采集`;
    actions = `<button class="method-btn" onclick="beginAuth('${r.key}','${p.method}')">重新采集</button>`;
  }else if(p.step === "verify"){
    status = isFace ? "已采集人脸，正在做活体检测与比对…" : "已采集指纹，正在比对模板…";
    actions = `<button class="method-btn" onclick="cancelAuth()">取消</button>`;
  }else{
    status = isFace ? "请正对摄像头，保持面部在框内…" : "请将已登记的手指按压在指纹仪上…";
    actions = `<button class="method-btn" onclick="cancelAuth()">取消</button>`;
  }
  return `<div class="role-card"><h4>${r.title}岗 · 生物识别 <span class="pill amber">采集中</span></h4>
    <div class="kvline">${r.name} · 工号 ${r.id} · 岗位 ${r.post}</div>
    <div class="bio-box ${cls}">
      <div class="bio-icon">${isFace?"☺":"☝"}</div>
      <div class="bio-title">${p.method} · ${channel.name}</div>
      <div class="bio-status">${status}</div>
      <div class="bio-meta">设备 ${dev.device} · 员工号 ${r.id} 绑定</div>
      <div class="bio-actions">${actions}
        ${p.step!=="fail"?`<button class="method-btn" onclick="simulateBioFail('${r.key}','${p.method}')">模拟认证失败</button>`:""}
      </div>
    </div></div>`;
}

function setAuthChannel(ch){
  state.authChannel = ch;
  state.authPending = null;
  renderSignRoles();
}

function beginAuth(key, method){
  const channel = state.authChannel;
  if(method === "指纹识别" || method === "人脸识别"){
    state.authPending = {key, method, channel, step:"capture"};
    renderSignRoles();
    setTimeout(()=>{
      if(!state.authPending || state.authPending.key!==key || state.authPending.step!=="capture") return;
      state.authPending.step = "verify";
      renderSignRoles();
    }, 650);
    setTimeout(()=>{
      if(!state.authPending || state.authPending.key!==key || state.authPending.step!=="verify") return;
      completeBiometric(key, method);
    }, 1600);
  }else{
    const dev = method === "授权卡" ? "CARD-RDR-02" : method === "通行密钥" ? "OA-SSO-****" : "EMP-CARD-01";
    recordSignature(key, method, {channel, device:dev});
  }
}

function simulateBioFail(key, method){
  if(!state.authPending || state.authPending.key!==key) return;
  state.authPending.step = "fail";
  state.authPending.failScore = method === "人脸识别" ? "61.4%" : "58.2%";
  renderSignRoles();
  toast("认证未通过：请重新采集");
}

function cancelAuth(){
  state.authPending = null;
  renderSignRoles();
}

function completeBiometric(key, method){
  const p = state.authPending;
  const dev = (BIO_DEVICE[p.channel] || {})[method] || {device:"—", score:"—"};
  state.authPending = null;
  recordSignature(key, method, {channel:p.channel, device:dev.device, score:dev.score});
}

function recordSignature(key, method, meta){
  const idx = SIGN_ROLES.findIndex(r=>r.key===key);
  if(idx < 0) return;
  if(idx > 0 && !state.signatures[SIGN_ROLES[idx-1].key]){ toast("请先完成上一级授权"); return; }
  const r = SIGN_ROLES[idx];
  // 鉴权模式：谁登录谁签字——只能签本人角色对应的那一级，身份取登录会话而非演示字典
  let who = r;
  if(AUTH_STATE.required){
    const u = AUTH_STATE.user;
    if(!u){ toast("鉴权模式：请先登录再签字"); showLogin(); return; }
    if(u.role !== key){
      toast(`本级为「${r.title}」签字，需以 ${r.title} 角色账号登录（当前登录：${u.role_name} · ${u.name}）`);
      return;
    }
    who = {name: u.name, id: u.id, post: u.post, title: u.role_name};
  }
  state.signatures[key] = {
    name:who.name, id:who.id, post:who.post, method,
    channel:(AUTH_CHANNELS.find(c=>c.key===(meta||{}).channel)||{}).name || "",
    device:(meta||{}).device || "", score:(meta||{}).score || "",
    time: isoNow()
  };
  state.signed = SIGN_ROLES.every(x=>state.signatures[x.key]);
  state.authPending = null;
  renderSignRoles();
  renderSignBlock();
  renderActionState();
  toast(state.signed ? "三级授权完成：报告已定稿，签字不等于提交，请点「提交报送」" : `${r.title}岗授权完成，请继续下一级`);
}

function withdrawSignature(key){
  if(state.submitted){ toast("报告已报送，不能撤回签字"); return; }
  const idx = SIGN_ROLES.findIndex(r=>r.key===key);
  if(idx < 0) return;
  const hasLater = SIGN_ROLES.slice(idx+1).some(r=>state.signatures[r.key]);
  if(hasLater){ toast("请先撤回下一级签字"); return; }
  const r = SIGN_ROLES[idx];
  delete state.signatures[key];
  state.signed = false;
  state.authPending = null;
  renderSignRoles();
  renderReportBody();
  toast(`${r.title}岗签字已撤回，报告回到上一环节`);
}

function returnForRevision(key){
  const r = SIGN_ROLES.find(x=>x.key===key);
  document.getElementById("signMeta").textContent = `报告编号 ${state.report.report_no} · 退回修改确认`;
  document.getElementById("signBody").innerHTML = `
    <div class="confirm-box">
      <b>确认由${r.title}岗退回经办修改？</b><br>
      退回后，当前三级签字记录将全部清空，报告回到「草稿」状态，由经办修改后重新走经办 → 复核 → 审批授权。
      退回人、时间与原因会留痕。
    </div>
    <div style="margin-top:12px;">
      <div style="font-size:12.5px;color:var(--muted);margin-bottom:6px;">退回原因（必填，随留痕一起写入台账）</div>
      <textarea class="el-input" id="returnReason" rows="3" placeholder="例如：第 21 项交易金额口径需与流水核对后重填；第 24 项特征代码待专岗补充"></textarea>
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;">
      <button class="btn ghost" onclick="renderSignRoles()">取消</button>
      <button class="btn" onclick="doReturnForRevision('${key}')">确认退回修改</button>
    </div>`;
}

function doReturnForRevision(key){
  const r = SIGN_ROLES.find(x=>x.key===key);
  const reasonEl = document.getElementById("returnReason");
  const reason = (reasonEl && reasonEl.value || "").trim();
  if(!reason){ toast("请填写退回原因（留痕必填项）"); return; }
  state.returnLog.push({role:r.title, by:r.name + "（" + r.id + "）",
    time:isoNow(), reason});
  state.signatures = {operator:null, reviewer:null, approver:null};
  state.signed = false;
  state.submitted = false;
  state.receiptNo = null;
  state.submittedAt = null;
  state.authPending = null;
  state.editMode = false;
  closeSign();
  renderReportBody();
  toast(`${r.title}岗已退回修改：报告回到草稿，可重新修订并重走授权`);
}

