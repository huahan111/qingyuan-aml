/* 登录鉴权（可选模式 QINGYUAN_AUTH=1，内部试用形态）：
   未开启时不渲染任何 UI、行为与既往一致；开启后未登录弹出登录层，
   顶栏显示当前用户，三级签字仅允许签署本人角色对应的那一级。 */

let AUTH_STATE = {required: false, user: null};

async function refreshAuthStatus(){
  try{
    const d = await fetch("/api/auth/me").then(r => r.json());
    AUTH_STATE = {required: !!d.auth_required, user: d.user || null, hint: d.demo_hint || ""};
  }catch(e){ AUTH_STATE = {required: false, user: null}; }
  renderUserChip();
  if(AUTH_STATE.required && !AUTH_STATE.user) showLogin();
  return AUTH_STATE;
}

function renderUserChip(){
  const chip = document.getElementById("userChip");
  if(!chip) return;
  if(!AUTH_STATE.required){ chip.style.display = "none"; return; }
  chip.style.display = "";
  chip.innerHTML = AUTH_STATE.user
    ? `<span class="pill green">${esc(AUTH_STATE.user.role_name)} · ${esc(AUTH_STATE.user.name)}（${esc(AUTH_STATE.user.id)}）</span>
       <button class="btn ghost small" style="margin-left:6px;" onclick="logout()">退出</button>`
    : `<span class="pill amber">未登录</span>
       <button class="btn ghost small" style="margin-left:6px;" onclick="showLogin()">登录</button>`;
}

function showLogin(){
  if(document.getElementById("loginMask")) return;
  const mask = document.createElement("div");
  mask.id = "loginMask";
  mask.className = "sign-mask show";
  mask.innerHTML = `
    <div class="login-box" style="background:#fff;border-radius:12px;padding:24px;width:min(380px,92vw);box-shadow:0 20px 60px rgba(15,46,76,.25);">
      <h3 style="margin:0 0 6px;">清源AML · 登录</h3>
      <div style="font-size:12px;color:var(--muted);margin-bottom:14px;">
        鉴权模式已开启（内部试用形态）。三级授权对应三个角色账号，谁登录谁签字。
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">
        ${[["jingban","经办"],["fuhe","复核"],["shenpi","审批"]].map(([u, t]) =>
          `<button class="tag gray" style="cursor:pointer;" onclick="document.getElementById('loginUser').value='${u}'">${u} · ${t}</button>`).join("")}
      </div>
      <input id="loginUser" class="el-input" placeholder="用户名（jingban / fuhe / shenpi）" style="width:100%;margin-bottom:8px;" autocomplete="username">
      <input id="loginPass" class="el-input" type="password" placeholder="口令" style="width:100%;margin-bottom:12px;" autocomplete="current-password">
      <div id="loginErr" style="font-size:12px;color:#b91c1c;margin-bottom:8px;display:none;"></div>
      <div style="display:flex;gap:10px;">
        <button class="btn" style="flex:1;" onclick="doLogin()">登录</button>
      </div>
      <div style="font-size:11px;color:var(--muted);margin-top:10px;">演示口令：见后端启动日志（README 有说明；生产环境须接机构统一身份认证）。会话 8 小时有效。</div>
    </div>`;
  document.body.appendChild(mask);
  document.getElementById("loginPass").addEventListener("keydown", e => { if(e.key === "Enter") doLogin(); });
}

async function doLogin(){
  const err = document.getElementById("loginErr");
  err.style.display = "none";
  try{
    const r = await fetch("/api/auth/login", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        username: document.getElementById("loginUser").value.trim(),
        password: document.getElementById("loginPass").value})
    });
    if(!r.ok){
      err.textContent = (await r.json()).detail || "登录失败";
      err.style.display = "block";
      return;
    }
    const d = await r.json();
    AUTH_STATE.user = d.user;
    document.getElementById("loginMask")?.remove();
    renderUserChip();
    toast(`已登录：${d.user.role_name} · ${d.user.name}（${d.user.id}）`);
    if(typeof init === "function") init();   // 登录成功后重新拉取此前被 401 拦截的数据
  }catch(e){
    err.textContent = "登录请求失败：" + e.message;
    err.style.display = "block";
  }
}

async function logout(){
  try{ await fetch("/api/auth/logout", {method: "POST"}); }catch(e){}
  AUTH_STATE.user = null;
  renderUserChip();
  showLogin();
  toast("已退出登录");
}
