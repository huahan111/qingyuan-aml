/* 全局状态、常量、通用工具与页面导航 */
const state = {
  cases: [], current: null, workDiag: null, report: null,
  flowStage: 0, flowCase: null, flowDiag: null, flowReport: null,
  timer: null, editMode: false, signed: false, signReportNo: null,
  submitted: false, receiptNo: null, submittedAt: null,
  editLog: [], version: 1, returnLog: [],
  authChannel: "branch", authPending: null, previewMode: false, archiveMode: false,
  correctionOf: null, submissions: [], readOnly: false,
  signatures: {operator:null, reviewer:null, approver:null}
};
const CAT_LABEL = {pass:"放行", intercept:"拦截", grey:"灰区"};
const CAT_NAME = {intercept:"可疑拦截", grey:"灰区人工复核", pass:"正常放行"};
const CAT_ORDER = ["intercept","grey","pass"];
const {roles: SIGN_ROLES, channels: AUTH_CHANNELS, devices: BIO_DEVICE} = AUTH_CONFIG;

function toast(msg){
  const el = document.getElementById("toast");
  el.textContent = msg; el.classList.add("show");
  clearTimeout(el._t); el._t = setTimeout(()=>el.classList.remove("show"), 2200);
}
function esc(s){
  // 单引号也须转义：大量 onclick 属性用单引号包插值，漏掉即成注入点
  return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}
async function jget(url){ const r = await fetch(url); if(r.status===401){ showLogin(); } if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function jpost(url, body){
  const opt = {method: "POST"};
  if(body !== undefined){ opt.headers = {"Content-Type": "application/json"}; opt.body = JSON.stringify(body); }
  const r = await fetch(url, opt); if(r.status===401){ showLogin(); } if(!r.ok) throw new Error(await r.text()); return r.json();
}
function fmtAmt(n){ return "¥" + Number(n).toLocaleString("zh-CN", {maximumFractionDigits: 2}); }

/* 交易方向：只按"交易类型"判断（与后端 common.py 的 IN_TYPES 同源） */
const IN_TYPES = ["转账收入", "现金存入", "跨境收入", "结汇收入"];

/* 金额展示：外币显示原币 + 折人民币；人民币直接显示 */
function fmtTxAmount(t){
  const cny = Number(t.amount_cny != null ? t.amount_cny : t.amount);
  const cur = t.currency || "CNY";
  if(cur !== "CNY"){
    return `${esc(cur)} ${Number(t.amount).toLocaleString("zh-CN")}`
      + ` <span style="color:var(--muted);font-size:11px;">≈${fmtAmt(cny)}</span>`;
  }
  return fmtAmt(cny);
}

/* 统一时间与回执号格式：台账写入一律 ISO（YYYY-MM-DD HH:MM:SS），
   避免 "2026/10/23" 与 "2026-10-23" 混存导致"今日上报"漏计、排序乱序 */
function isoNow(){
  const d = new Date(), p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function isoToday(){
  const d = new Date(), p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`;
}

async function resetDemo(){
  if(state.readOnly){ toast("只读演示环境不能重置数据"); return; }
  if(!confirm("确认清空上报台账与已定性案例库？法规、规则与演示案例不受影响。")) return;
  try{
    const r = await jpost("/api/admin/reset-demo", {});
    toast(`已重置：清除 ${r.submissions} 条上报、${r.library_cases} 条案例库`);
    setTimeout(()=>location.reload(), 700);
  }catch(e){ toast("重置失败：" + e.message); }
}

/* ================= 导航 ================= */
const PAGE_META = {
  workbench: ["工作台", "选案例 → 规则 + AI 研判 → 三向分流 → 生成 STR"],
  flow: ["全流程演示", "扫描识别 → 预警筛选 → 研判处置 → STR 生成 → 预览签署 → 复核授权 → 报送人行"],
  alerts: ["可疑交易预警", "规则引擎触发 · AI 预诊断后按风险分级"],
  screening: ["名单筛查", "制裁 / 涉恐名单 · 命中即冻结，不经 AI"],
  ctr: ["大额交易报告", "客观标准：达到阈值即报，不判断可疑"],
  cdd: ["客户尽职调查", "识别 → 核实 → 留痕 · 可发起对公/个人尽调查询"],
  rating: ["客户风险评级", "四维模型实时计算 · 预警回写 · 升降级与 EDD"],
  rules: ["监测规则配置", "规则库只读展示 · R001–R009 + R017 可执行"],
  reports: ["上报台账", "已报送记录 · 回执 · 三级签字 · 报告版本"]
};
function showPage(name){
  document.querySelectorAll(".nav-item").forEach(el=>el.classList.toggle("active", el.dataset.page===name));
  document.querySelectorAll(".page").forEach(el=>el.classList.toggle("active", el.id==="page-"+name));
  const meta = PAGE_META[name] || PAGE_META.workbench;
  document.getElementById("pageTitle").textContent = meta[0];
  document.getElementById("pageSub").textContent = meta[1];
  if(name==="flow" && state.flowStage===0) flowReset();
  if(name==="alerts") renderAlerts();
  if(name==="ctr") loadCtr();
  if(name==="rating") renderRating();
  if(name==="rules") loadRules();
  if(name==="cdd") initCdd();
  if(name==="reports") loadSubmissions();
}

