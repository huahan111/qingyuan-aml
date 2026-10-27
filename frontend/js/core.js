/* 全局状态、常量、通用工具与页面导航 */
const state = {
  cases: [], current: null, workDiag: null, report: null,
  flowStage: 0, flowCase: null, flowDiag: null, flowReport: null,
  timer: null, editMode: false, signed: false, signReportNo: null,
  submitted: false, receiptNo: null, submittedAt: null,
  editLog: [], version: 1, returnLog: [],
  authChannel: "branch", authPending: null, previewMode: false, archiveMode: false,
  correctionOf: null, submissions: [], readOnly: false, demoSubmissions: [],
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
/* 统一请求出口：带超时与一次重试。
   托管环境的网关偶发会卡住个别请求，原先裸 fetch 会一直挂着，
   调用方 await 不返回 → 首屏永远转圈。这里 12 秒超时，失败重试一次。 */
const FETCH_TIMEOUT = 12000;
async function _fetch(url, opt, retryLeft){
  const ctl = new AbortController();
  const timer = setTimeout(()=>ctl.abort(), FETCH_TIMEOUT);
  try{
    return await fetch(url, Object.assign({}, opt, {signal: ctl.signal}));
  }catch(e){
    if(retryLeft > 0){
      await new Promise(s=>setTimeout(s, 700));
      return _fetch(url, opt, retryLeft - 1);
    }
    throw e;
  }finally{
    clearTimeout(timer);
  }
}
async function jget(url){
  const r = await _fetch(url, {}, 1);
  if(r.status===401){ showLogin(); }
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}
async function jpost(url, body){
  const opt = {method: "POST"};
  if(body !== undefined){ opt.headers = {"Content-Type": "application/json"}; opt.body = JSON.stringify(body); }
  const r = await _fetch(url, opt, 1);
  if(r.status===401){ showLogin(); }
  if(!r.ok) throw new Error(await r.text());
  return r.json();
}
/* 限并发地跑一批请求：首屏原本一次性并发 20 个，容易把弱环境的连接打满 */
async function mapLimit(items, limit, fn){
  const out = new Array(items.length);
  let idx = 0;
  const workers = Array.from({length: Math.min(limit, items.length)}, async ()=>{
    while(idx < items.length){
      const i = idx++;
      try{ out[i] = await fn(items[i], i); }
      catch(e){ out[i] = null; }
    }
  });
  await Promise.all(workers);
  return out;
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

/* ============ 演示送达（只读站也能把流程走完） ============
   只读站不接人行通道、不写业务库，但流程必须能走完，否则报送之后
   台账、归档、规则反哺全都演示不了。所以报送走"演示送达"：
   本地生成带 DEMO 标记的回执号，报告置为已送达，台账里显示这条记录并标明未入库，
   同时明确告知：未出网、不具报送效力。 */
function demoReceiptNo(){
  const d = new Date(), p = n => String(n).padStart(2, "0");
  const ymd = `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`;
  return `RX-DEMO-${ymd}-${String(state.demoSubmissions.length + 1).padStart(3, "0")}`;
}

function demoSubmitRecord(rep, sigs){
  const brief = x => x ? `${x.name} ${x.id}` : "";
  const rec = {
    id: null, demo: true,
    receipt_no: demoReceiptNo(),
    report_no: rep.report_no, case_id: rep.case_id, case_title: rep.title,
    customer: (rep.meta || {}).customer || "",
    submitted_at: isoNow(), version: state.version,
    operator: brief(sigs.operator), reviewer: brief(sigs.reviewer), approver: brief(sigs.approver),
    status: "演示送达（未入库）", filing_deadline: rep.filing_deadline || "",
    supersedes_receipt: ""
  };
  state.demoSubmissions.unshift(rec);
  return rec;
}

/* ============ 演示边界说明 ============
   线上是只读演示站：不接人行报送通道、不写业务库。相关按钮点了不能"什么都不说"，
   否则用户会以为是坏了。统一用一张说明卡讲清楚：哪些做完了、哪些没接、怎么接。 */
const DEMO_LIMITS = {
  library: {
    title: "这个操作要写库，演示站已锁",
    done: "看案例、跑研判、出报告、查溯源、走完七步流程（含演示送达）这些功能都正常。",
    missing: "只读模式关闭了所有写接口（防止访客之间互相污染演示数据），所以「沉淀负样本」「重置数据」这类动作不会生效。",
    so: "它不是坏，是被锁了；报送走的是演示送达，能走完但不入库。",
    local: "本地 ./run.sh 或 Codespaces 启动后可写，能完整走一遍负样本沉淀。"
  }
};

function showDemoLimit(kind){
  const c = DEMO_LIMITS[kind];
  if(!c) return;
  let mask = document.getElementById("demoLimitMask");
  if(!mask){
    mask = document.createElement("div");
    mask.id = "demoLimitMask";
    mask.style.cssText = "position:fixed;inset:0;background:rgba(15,23,42,.45);z-index:300;"
      + "display:none;align-items:center;justify-content:center;padding:20px;";
    mask.addEventListener("click", e=>{ if(e.target === mask) mask.style.display = "none"; });
    document.body.appendChild(mask);
  }
  mask.innerHTML = `
    <div style="background:#fff;border-radius:12px;max-width:560px;width:100%;padding:20px 22px;
                box-shadow:0 18px 48px rgba(15,23,42,.28);">
      <div style="font-size:16px;font-weight:700;color:#0f172a;margin-bottom:10px;">${esc(c.title)}</div>
      <div style="font-size:13px;line-height:1.85;color:#334155;">
        <p style="margin-bottom:8px;"><b style="color:#166534;">已经做完的：</b>${esc(c.done)}</p>
        <p style="margin-bottom:8px;"><b style="color:#b45309;">还没接的：</b>${esc(c.missing)}</p>
        <p style="margin-bottom:8px;">${esc(c.so)}</p>
        <p style="font-size:12px;color:#64748b;">${esc(c.local)}</p>
      </div>
      <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:16px;">
        <button class="btn small" onclick="document.getElementById('demoLimitMask').style.display='none'">知道了</button>
      </div>
    </div>`;
  mask.style.display = "flex";
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

