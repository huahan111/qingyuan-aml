/* CDD 尽职调查：对公工商尽调 / 个人身份核验（只查询，不落库、不存证件号） */

/* 示例号一键填充并直查（合成数据，演示勿输真实证件号） */
function fillCddEnt(name, uscc){
  document.getElementById("cddEntName").value = name;
  document.getElementById("cddEntUscc").value = uscc || "";
  runCddEnterprise();
}
function fillCddPer(name, idNo){
  document.getElementById("cddPerName").value = name;
  document.getElementById("cddPerId").value = idNo;
  document.getElementById("cddPerExp").value = "2030-01-01";
  runCddPersonal();
}

async function initCdd(){
  try{
    const info = await jget("/api/cdd/info");
    const ent = (info.enterprise_providers || [])
      .map(p => `${p.name}${p.available ? "" : "（未配置）"}`).join(" · ");
    const per = (info.identity_providers || [])
      .map(p => `${p.name}${p.available ? "" : "（未配置）"}`).join(" · ");
    document.getElementById("cddEntProvider").textContent = "数据源：" + (ent || "—");
    document.getElementById("cddPerProvider").textContent = "核验渠道：" + (per || "—");
  }catch(e){ /* 页面其余部分仍可用 */ }
}

function cddRiskTag(conclusion){
  if(conclusion === "高风险") return "red";
  if(conclusion === "中风险") return "amber";
  return "green";
}

async function runCddEnterprise(){
  const name = document.getElementById("cddEntName").value.trim();
  const uscc = document.getElementById("cddEntUscc").value.trim();
  const box = document.getElementById("cddEntResult");
  if(!name && !uscc){ toast("请填写企业名称或统一社会信用代码"); return; }
  box.innerHTML = '<span class="loading"></span>';
  try{
    const d = await jpost("/api/cdd/enterprise", {name, uscc});
    if(!d.found){
      box.innerHTML = `<div class="miss-box">未收录：${esc(d.query || name)}
        <div style="font-size:11.5px;color:var(--muted);margin-top:4px;">${esc(d.notice || "")}</div></div>`;
      return;
    }
    box.innerHTML = `
      <div class="hit-box" style="border-color:${d.conclusion === "高风险" ? "#fca5a5" : "#bbf7d0"};">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <b>${esc(d.query)}</b>
          <span class="tag ${cddRiskTag(d.conclusion)}">${esc(d.conclusion)}</span>
          <span class="tag gray">${esc(d.source || d.provider)}</span>
        </div>
        <div class="rdesc" style="margin-top:6px;">
          统一社会信用代码：${esc(d.uscc || "—")}　|　法定代表人：${esc(d.legal_rep || "—")}<br>
          注册资本：${esc(d.reg_capital || "—")}　|　成立日期：${esc(d.established || "—")}<br>
          登记状态：${esc(d.status || "—")}<br>
          注册地址：${esc(d.address || "—")}<br>
          经营范围：${esc(d.scope || "—")}
        </div>
        <div style="margin-top:6px;">${(d.risk_tags || []).map(t =>
          `<span class="tag ${/异常|无法联系|失联/.test(t) ? "red" : "amber"}">${esc(t)}</span>`).join("")}</div>
      </div>
      <table class="grid" style="margin-top:10px;">
        <thead><tr><th>核查项</th><th>结果</th><th>判定</th></tr></thead>
        <tbody>${(d.checks || []).map(c => `<tr><td>${esc(c.item)}</td><td>${esc(c.result)}</td>
          <td>${c.ok ? '<span class="pill green">通过</span>' : '<span class="pill red">需关注</span>'}</td></tr>`).join("")}
        </tbody></table>
      <div class="str-note">处置建议：${esc(d.suggestion || "—")}${d.provider === "mock-enterprise" ? "（模拟数据源，仅用于演示尽调流程与结论呈现）" : ""}</div>`;
  }catch(e){
    box.innerHTML = `<div class="miss-box">${esc(errText(e))}</div>`;
  }
}

async function runCddPersonal(){
  const name = document.getElementById("cddPerName").value.trim();
  const idNo = document.getElementById("cddPerId").value.trim();
  const idExp = document.getElementById("cddPerExp").value.trim();
  const box = document.getElementById("cddPerResult");
  if(!name || !idNo){ toast("请填写姓名与身份证号"); return; }
  box.innerHTML = '<span class="loading"></span>';
  try{
    const d = await jpost("/api/cdd/personal", {name, id_no: idNo, id_expiry: idExp});
    box.innerHTML = `
      <div class="hit-box" style="border-color:${d.verified ? "#bbf7d0" : "#fcd34d"};">
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <b>${esc(d.query)}</b>
          <span class="tag gray">${esc(d.id_masked || "")}</span>
          <span class="tag ${d.verified ? "green" : "amber"}">${esc(d.conclusion)}</span>
          <span class="tag gray">${esc(d.source)}</span>
        </div>
        <table class="grid" style="margin-top:8px;">
          <thead><tr><th>核查项</th><th>结果</th><th>判定</th></tr></thead>
          <tbody>${(d.checks || []).map(c => `<tr><td>${esc(c.item)}</td><td>${esc(c.result)}</td>
            <td>${c.ok ? '<span class="pill green">通过</span>' : '<span class="pill amber">需核实</span>'}</td></tr>`).join("")}
          </tbody></table>
        <div class="str-note">${esc(d.notice || "")}</div>
      </div>`;
  }catch(e){
    box.innerHTML = `<div class="miss-box">${esc(errText(e))}</div>`;
  }
}
