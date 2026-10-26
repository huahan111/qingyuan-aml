/* 应用初始化：鉴权状态下先确认登录，再加载案例/规则/法规渲染工作台 */
function showLoadError(msg){
  const host = document.getElementById("page-workbench");
  if(!host) return;
  let box = document.getElementById("loadErrorBox");
  if(!box){
    box = document.createElement("div");
    box.id = "loadErrorBox";
    box.style.cssText = "margin:12px 0;padding:12px 14px;border:1px solid #fca5a5;"
      + "background:#fef2f2;color:#991b1b;border-radius:8px;font-size:13px;";
    host.insertBefore(box, host.firstChild);
  }
  box.innerHTML = msg + ' <a href="javascript:location.reload()" style="color:#b91c1c;'
    + 'font-weight:600;text-decoration:underline;">点此刷新重试</a>';
}

async function init(){
  await refreshAuthStatus();
  if(AUTH_STATE.required && !AUTH_STATE.user) return; // 未登录：登录层已弹出，登录成功后会重跑 init
  try{
    const h = await jget("/api/health");
    state.readOnly = !!h.read_only;
    const roTag = document.getElementById("readonlyTag");
    if(roTag) roTag.style.display = state.readOnly ? "" : "none";
    const resetBtn = document.getElementById("btnResetDemo");
    if(resetBtn) resetBtn.style.display = state.readOnly ? "none" : "";
    document.getElementById("providerName").textContent =
      h.ai_provider === "mock-prebuilt" ? "预生成校验（演示模式）" : "实时大模型（Live）";
    const ds = h.dataset || {};
    document.querySelectorAll("#dsTag").forEach(el=>{
      el.textContent = `${ds.name || "演示数据集"} ${ds.version || ""}（${ds.count || 0} 条 · JSON）`;
    });
  }catch(e){
    const p = document.getElementById("providerName");
    if(p) p.textContent = "连接超时";
  }

  // 三个基础数据集：缺任何一项都无法渲染看板，单独判定并给出可点的重试入口
  const [data, rules, regs] = await Promise.allSettled([
    jget("/api/cases"), jget("/api/rules"), jget("/api/regulations")
  ]);
  if(data.status !== "fulfilled"){
    showLoadError("案例数据没加载出来，可能是网络抖动或服务正在唤醒。");
    return;
  }
  state.cases = data.value.cases;
  state.dataset = data.value.dataset;
  state.rules = rules.status === "fulfilled" ? rules.value.rules : [];
  state.regulations = regs.status === "fulfilled" ? regs.value.regulations : [];

  // 案例明细限并发 4 个；个别失败不拖垮整页，缺的案例在列表里照样能点（打开时再取一次）
  const details = await mapLimit(state.cases, 4, c=>jget("/api/cases/" + c.case_id));
  state.caseDetails = details.filter(Boolean);

  renderCaseList();
  renderDashboard();
  flowReset();

  if(state.caseDetails.length < state.cases.length){
    showLoadError(`已加载 ${state.caseDetails.length}/${state.cases.length} 条案例明细，`
      + "部分数据没取到（不影响点开单个案例）。");
  }
}

init();
