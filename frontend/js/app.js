/* 应用初始化：鉴权状态下先确认登录，再加载案例/规则/法规渲染工作台 */
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
  }catch(e){}
  const [data, rules, regs] = await Promise.all([
    jget("/api/cases"), jget("/api/rules"), jget("/api/regulations")
  ]);
  state.cases = data.cases;
  state.dataset = data.dataset;
  state.rules = rules.rules;
  state.regulations = regs.regulations;
  state.caseDetails = await Promise.all(data.cases.map(c=>jget("/api/cases/" + c.case_id)));
  renderCaseList();
  renderDashboard();
  flowReset();
}

init();
