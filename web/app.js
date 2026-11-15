'use strict';
const $ = (selector) => document.querySelector(selector);
const pages = [
  ['overview', '◫', 'Overview'], ['visuals', '◉', 'Visuals'], ['aim', '⌖', 'Aim settings'],
  ['movement', '⌁', 'Movement & utility'], ['radar', '◎', 'Radar'],
  ['configs', '▱', 'Configurations'], ['hotkeys', '⌘', 'Hotkeys'],
];
const titles = {overview: ['Control room', 'Everything in view. Every setting in its place.'],
  visuals: ['Visual workspace', 'Build your look with a live, synthetic preview.'],
  aim: ['Aim preferences', 'Tune stored preferences. No input is sent to the game.'],
  movement: ['Movement & utility', 'A workspace for your utility preferences.'],
  radar: ['Situational view', 'Synthetic positions, rendered in a circular radar.'],
  configs: ['Your configurations', 'Named, local, and ready when you are.'],
  hotkeys: ['At your fingertips', 'Capture bindings for your configuration.']};
let state = null, settings = {}, page = 'overview', view = 'scene', busy = false;
let writeQueue = Promise.resolve(), toastTimer, animation, captureCleanup;
let dirty = false;
const labels = {
  skeleton: ['Skeleton', 'Connect player bones in the preview'], health: ['Health bars', 'Health alongside each preview actor'],
  armor: ['Armor bars', 'A second bar for armor values'], glow: ['Glow V2', 'Highlight the synthetic silhouette'],
  visibilityColors: ['Visibility colors', 'Separate visible and occluded actors'], teammates: ['Show teammates', 'Include your team in the preview'],
  sound: ['Sound ESP', 'Animated synthetic footstep rings'], spectators: ['Spectator list', 'Show a sample spectator panel'],
  bomb: ['Bomb timer', 'Sample explosion and defuse countdown'], radar: ['2D radar', 'A compact circular position display'],
  tracers: ['Bullet tracers', 'Draw sample shot paths'], hitmarker: ['Hitmarker', 'Show a crosshair hit indicator'],
  visibleFallback: ['Visible bone fallback', 'Stored preference · requires game visibility data'],
  prediction: ['Movement prediction', 'Stored preference · no live tracking'], trigger: ['Triggerbot', 'Stored preference · no automated firing'],
  bunnyHop: ['Bunny hop', 'Stored preference · no movement automation'], nadeHelper: ['Nade helper', 'Stored preference · no lineup database'],
  noSpread: ['No spread · experimental', 'Stored preference · not implemented'], noFlash: ['No flash', 'Stored preference · not applied to CS2'],
  noSmoke: ['No smoke', 'Stored preference · not applied to CS2'], thirdPerson: ['Third person', 'Stored preference · not applied to CS2'],
};
const escapeHTML = (value) => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notify(message) { $('#toast').textContent = message; $('#toast').classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 3800); }
async function api(path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 6000);
  try {
    const response = await fetch(path, {cache: 'no-store', signal: controller.signal,
      ...(body ? {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Phantom-Token': state.token}, body: JSON.stringify(body)} : {})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  } finally { clearTimeout(timeout); }
}
function connection(online, next) {
  $('#connection-led').style.background = online ? 'var(--green)' : '#c38b83';
  $('#connection-label').textContent = online ? 'Connected · local API' : 'Connection unavailable';
  $('#stat-companion').textContent = online ? 'Connected' : 'Offline';
  if (!next) return;
  $('#stat-platform').textContent = next.platform === 'win32' ? 'WINDOWS' : next.mode === 'demo' ? 'DEMO' : 'NON-WINDOWS';
  $('#stat-process').textContent = next.pid ? `Detected · PID ${next.pid}` : next.detectionError ? 'Detection failed' : next.platform !== 'win32' ? 'Windows required' : 'CS2 not running';
  $('#stat-config').textContent = (state?.active || 'Unsaved workspace') + (dirty && state?.active ? ' *' : '');
  $('#saved-count').textContent = `${state?.configs.length || 0} saved`;
  $('#preview-description').textContent = next.mode === 'demo' ? 'Synthetic telemetry. Settings are saved locally; no game interaction.' : 'Process detection only. Visual preview uses synthetic data.';
}
function toggle(key) {
  const [name, description] = labels[key];
  return `<div class="setting-row"><div><div class="setting-name" id="label-${key}">${name}</div><div class="setting-desc">${description}</div></div><button class="switch" role="switch" aria-checked="${settings[key]}" aria-labelledby="label-${key}" data-toggle="${key}"></button></div>`;
}
function selectRow(key, title, values, description = 'Stored preference · not applied to the game') {
  return `<div class="setting-row"><div><label class="setting-name" for="${key}">${title}</label><div class="setting-desc">${description}</div></div><select class="field" id="${key}" data-setting="${key}">${values.map(v => `<option ${settings[key] === v ? 'selected' : ''}>${v}</option>`).join('')}</select></div>`;
}
function slider(key, title, min, max, suffix = '', description = 'Stored preference') {
  return `<div class="setting-row"><div><label class="setting-name" for="${key}">${title}</label><div class="setting-desc">${description}</div></div><div class="range-control"><input id="${key}" data-setting="${key}" type="range" min="${min}" max="${max}" value="${settings[key]}"><output class="range-value" for="${key}">${settings[key]}${suffix}</output></div></div>`;
}
function panel(title, icon, body, aside = '') { return `<section class="panel"><div class="panel-header"><div class="panel-title"><span>${icon}</span>${title}</div>${aside}</div>${body}</section>`; }
const note = '<div class="pending-note">Preferences only · game modification is not implemented.</div>';
function palette() {
  return `<div class="setting-row"><div><div class="setting-name">Accent color</div><div class="setting-desc">Your preview, your palette</div></div><div class="color-palette">${['#a995ff','#8bc9a3','#e4b381','#8fbce8','#e69ebc'].map(c => `<button class="color-dot ${settings.accent === c ? 'selected' : ''}" style="--swatch:${c}" data-color="${c}" aria-label="Set accent ${c}" aria-pressed="${settings.accent === c}"></button>`).join('')}</div></div>`;
}
function preview(radarOnly = false) {
  return panel(radarOnly ? 'Radar preview' : 'Visual preview', radarOnly ? '◎' : '◉',
    `<div class="preview-toolbar"><div class="segmented"><button data-view="scene" class="${view === 'scene' ? 'selected' : ''}" aria-pressed="${view === 'scene'}">Perspective</button><button data-view="radar" class="${view === 'radar' ? 'selected' : ''}" aria-pressed="${view === 'radar'}">Radar</button></div><span>LOCAL SCENE / 01</span></div><div class="canvas-wrap"><canvas id="preview-canvas" aria-label="Animated synthetic player preview, not live game data" role="img"></canvas><span class="canvas-label"><i></i>SYNTHETIC ENVIRONMENT</span><span class="canvas-bottom">${radarOnly ? 'TOP-DOWN VIEW' : 'PREVIEW ONLY · NOT GAME FOOTAGE'}</span></div><div class="legend"><span><i></i>Visible</span><span><i></i>Occluded</span><span>Sample actors · 4</span></div>`,
    '<span class="live-tag"><i></i>DEMO</span>');
}
function configForm(full = false) {
  const active = escapeHTML(state.active || 'Untitled workspace');
  return panel('Configuration', '▱', `<div class="config-body"><div class="config-info"><span class="file-symbol">▱</span><div><strong>${active}</strong><small>${dirty ? 'Unsaved changes' : state.active ? 'Named configuration loaded' : 'Save your current preferences'}</small></div><span class="pill">LOCAL</span></div><form id="save-config" class="config-controls"><input class="field" id="config-name" name="name" aria-label="Configuration name" placeholder="Name your configuration…" maxlength="40" required pattern="[A-Za-z0-9][A-Za-z0-9 _\-]{0,39}" value="${escapeHTML(state.active || '')}"><button type="submit" class="button primary">Save config <span>↗</span></button></form>${full ? `<div class="config-list">${state.configs.length ? state.configs.map(name => `<div class="config-item"><span>${escapeHTML(name)}</span><button class="button" data-load="${escapeHTML(name)}">Load</button><button class="button" data-delete="${escapeHTML(name)}" aria-label="Delete ${escapeHTML(name)}">Delete</button></div>`).join('') : '<div class="empty-state">No saved configurations yet.</div>'}</div><div class="help-line">Names support letters, numbers, spaces, hyphens, and underscores. Saving an existing name replaces it. Loading a config replaces unsaved preferences.</div>` : ''}</div>`, `<button class="text-action" data-page="configs">Manage ↗</button>`);
}
function keyRow(key, name) { return `<div class="key-row"><span>${name}</span><button class="keycap" data-key="${key}" aria-label="Change ${name} binding">${escapeHTML(settings[key])}</button></div>`; }
function render() {
  captureCleanup?.();
  cancelAnimationFrame(animation);
  document.documentElement.style.setProperty('--accent', settings.accent);
  $('#nav').innerHTML = pages.map(([id, icon, title], index) => `${index === 5 ? '<div class="nav-divider"></div>' : ''}<button class="nav-button ${page === id ? 'active' : ''}" data-page="${id}" ${page === id ? 'aria-current="page"' : ''} aria-label="${title}"><span class="nav-icon">${icon}</span><span class="nav-text">${title}</span>${id === 'configs' ? `<span class="nav-count">${state.configs.length.toString().padStart(2, '0')}</span>` : ''}</button>`).join('');
  $('#breadcrumb').textContent = pages.find(p => p[0] === page)[2];
  $('#page-title').innerHTML = `${titles[page][0]}<span>.</span>`;
  $('#page-subtitle').textContent = titles[page][1];
  const content = $('#content');
  if (page === 'overview') {
    content.innerHTML = `<div class="content-grid">${preview()}<div class="side-stack">${panel('Quick controls', '⌘', ['skeleton','health','visibilityColors'].map(toggle).join(''), '<span class="sub-label">PREVIEW</span>')}${panel('Make it yours', '◈', palette() + toggle('teammates'))}</div></div><div class="bottom-grid">${configForm()}${panel('Quick bindings', '⌨', keyRow('menuKey', 'Menu toggle') + keyRow('aimKey', 'Aim activation') + keyRow('triggerKey', 'Trigger activation'), '<button class="text-action" data-page="hotkeys">Edit bindings ↗</button>')}</div>`;
  } else if (page === 'visuals') {
    content.innerHTML = `<div class="content-grid">${preview()}<div class="side-stack">${panel('ESP editor', '◉', ['skeleton','health','armor','glow','visibilityColors','teammates'].map(toggle).join(''))}${panel('Style', '◈', palette() + slider('espRange','Preview range',10,300,'m','Filter synthetic actors by distance'))}</div></div><div class="bottom-grid">${panel('Awareness', '◎', ['sound','spectators','bomb'].map(toggle).join(''))}${panel('Feedback', '⌖', ['tracers','hitmarker'].map(toggle).join(''))}</div>`;
  } else if (page === 'aim') {
    content.innerHTML = `<div class="settings-grid">${panel('Aim preferences','⌖', '<div class="section-intro">These settings are saved to your configuration. This build does not move the mouse, fire, or modify CS2.</div>' + selectRow('aimMode','Aim mode',['Off','Hardlock','Silent','Humanized V2']) + selectRow('bone','Priority bone',['Head','Chest','Pelvis']) + toggle('visibleFallback') + slider('smoothing','Smoothing',1,100,'%') + toggle('prediction') + note)}${panel('Recoil & trigger','⌁', selectRow('recoil','Recoil mode',['Off','Soft','Hard']) + toggle('trigger') + slider('triggerDelay','Shot delay',0,1000,'ms') + keyRow('aimKey','Aim activation') + keyRow('triggerKey','Trigger activation') + note)}</div>`;
  } else if (page === 'movement') {
    content.innerHTML = `<div class="settings-grid">${panel('Movement & equipment','⌁', ['bunnyHop','nadeHelper','noFlash','noSmoke'].map(toggle).join('') + note)}${panel('Camera & experimental','◈', slider('pov','Field of view',60,140,'°') + toggle('thirdPerson') + toggle('noSpread') + note)}</div>`;
  } else if (page === 'radar') {
    view = 'radar';
    content.innerHTML = `<div class="content-grid">${preview(true)}${panel('Radar settings','◎', toggle('radar') + toggle('teammates') + toggle('visibilityColors') + slider('espRange','Preview range',10,300,'m','Filter synthetic positions') + palette())}</div>`;
  } else if (page === 'configs') {
    content.innerHTML = `<div class="settings-grid">${configForm(true)}${panel('Local by design','◇','<div class="config-body"><div class="setting-name">Your settings stay on this machine.</div><p class="help-line">Configurations are written atomically to the companion’s config directory. No account, upload, or cloud service is involved.</p><p class="help-line">A saved config contains preferences only. It does not enable any game modifications. Demo and local companion configs are stored on the machine running the companion, not in browser storage.</p></div>')}</div>`;
  } else {
    content.innerHTML = `<div class="settings-grid">${panel('Custom bindings','⌨','<div class="section-intro">Click a binding, then press a key or mouse button. Escape cancels. Bindings are stored, not registered as global Windows shortcuts.</div>' + keyRow('menuKey','Menu toggle') + keyRow('aimKey','Aim activation') + keyRow('triggerKey','Trigger activation'))}${panel('Binding behavior','◇','<div class="config-body"><div class="setting-name">Browser capture only</div><p class="help-line">Letter keys, number keys, F1–F12, modifiers, Insert, Home, End, Delete, Space, and mouse buttons are supported. Some shortcuts are reserved by your browser or operating system.</p><p class="help-line">This build does not install a keyboard hook or send input to the game.</p></div>')}</div>`;
  }
  connection(true, state);
  if ($('#preview-canvas')) animatePreview();
}
function updateSetting(key, value) {
  if (busy) return;
  settings[key] = value; dirty = true;
  const snapshot = structuredClone(settings);
  render();
  writeQueue = writeQueue.then(async () => {
    const result = await api('/api/settings', {settings: snapshot, revision: state.revision});
    state.revision = result.revision;
  }).catch(async error => {
    notify(error.message);
    // Reconcile after rejected writes; never claim a failed preference was saved.
    try { state = await api('/api/state'); settings = {...state.settings}; dirty = true; render(); }
    catch { connection(false); }
  });
}
async function configAction(action, name) {
  if (busy) return;
  if (action === 'delete' && !window.confirm(`Delete configuration “${name}”?`)) return;
  if (action === 'load' && dirty && !window.confirm('Replace current preferences with this configuration?')) return;
  busy = true;
  try {
    await writeQueue;
    await api(`/api/config/${action}`, {name, revision: state.revision});
    state = await api('/api/state'); settings = {...state.settings};
    if (action !== 'delete') dirty = false;
    render(); notify(action === 'save' ? 'Configuration saved locally.' : action === 'load' ? 'Configuration loaded.' : 'Configuration deleted.');
  } catch (error) { notify(error.message); }
  finally { busy = false; }
}
function capture(button, key) {
  captureCleanup?.();
  button.textContent = 'Press a key…'; button.classList.add('capturing');
  let timeout;
  const finish = (event) => {
    event.preventDefault(); event.stopPropagation();
    if (event.type === 'keydown' && event.code === 'Escape') { cleanup(); render(); return; }
    const code = event.type === 'mousedown' ? ['MouseLeft','MouseMiddle','MouseRight'][event.button] : event.code;
    if (!code || !/^(Key[A-Z]|Digit[0-9]|F([1-9]|1[0-2])|Mouse(Left|Middle|Right)|Alt(Left|Right)|Shift(Left|Right)|Control(Left|Right)|Insert|Home|End|Delete|Space)$/.test(code)) { notify('That key is not supported. Escape cancels.'); return; }
    cleanup(); updateSetting(key, code); notify('Binding stored. No global hook is installed.');
  };
  const blockContext = event => event.preventDefault();
  const cleanup = () => { clearTimeout(timeout); document.removeEventListener('keydown', finish, true); document.removeEventListener('mousedown', finish, true); document.removeEventListener('contextmenu', blockContext, true); captureCleanup = null; };
  captureCleanup = cleanup;
  document.addEventListener('keydown', finish, true); document.addEventListener('mousedown', finish, true); document.addEventListener('contextmenu', blockContext, true);
  timeout = setTimeout(() => { cleanup(); render(); }, 10000);
}
document.addEventListener('click', event => {
  const button = event.target.closest('button'); if (!button) return;
  if (button.dataset.page) { page = button.dataset.page; render(); }
  if (button.dataset.toggle) updateSetting(button.dataset.toggle, !settings[button.dataset.toggle]);
  if (button.dataset.color) updateSetting('accent', button.dataset.color);
  if (button.dataset.view) { view = button.dataset.view; render(); }
  if (button.dataset.load) configAction('load', button.dataset.load);
  if (button.dataset.delete) configAction('delete', button.dataset.delete);
  if (button.dataset.key) capture(button, button.dataset.key);
});
document.addEventListener('change', event => {
  const key = event.target.dataset.setting;
  if (key) updateSetting(key, event.target.type === 'range' ? Number(event.target.value) : event.target.value);
});
document.addEventListener('input', event => {
  if (event.target.type === 'range') {
    const output = event.target.nextElementSibling;
    const suffix = output.textContent.replace(/[0-9]+/, ''); output.textContent = event.target.value + suffix;
  }
});
document.addEventListener('submit', event => { if (event.target.id === 'save-config') { event.preventDefault(); configAction('save', $('#config-name').value.trim()); } });
$('#help').onclick = () => $('#about').showModal();
$('#close-about').onclick = $('#understood').onclick = () => $('#about').close();
$('#reset').onclick = async () => {
  if (!state || busy || !confirm('Reset workspace preferences? Saved configurations will be kept.')) return;
  busy = true;
  try {
    await writeQueue;
    const defaults = {...state.defaults};
    const result = await api('/api/settings', {settings:defaults, revision:state.revision});
    state.revision = result.revision; settings = defaults; dirty = true; render(); notify('Workspace reset. Saved configurations kept.');
  } catch(error) { notify(error.message); } finally { busy = false; }
};

// All scene geometry and positions below are fabricated; there is no game data source.
function animatePreview() {
  const canvas = $('#preview-canvas'), ctx = canvas.getContext('2d');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let last = 0;
  const actors = [{x:.39,y:.46,size:1,health:84,armor:72,distance:24,name:'ACTOR 01',visible:true},
    {x:.69,y:.44,size:.73,health:62,armor:88,distance:38,name:'ACTOR 02',visible:false},
    {x:.83,y:.50,size:.5,health:95,armor:52,distance:67,name:'ACTOR 03',visible:true},
    {x:.18,y:.51,size:.65,health:100,armor:100,distance:46,name:'TEAM 01',visible:true,team:true}];
  function line(points, color, width=1) { ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.stroke(); }
  function polygon(points, fill, stroke) { ctx.fillStyle=fill;ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1;ctx.stroke();} }
  function actor(a,t,w,h) {
    if ((a.team&&!settings.teammates)||a.distance>settings.espRange) return;
    const x=w*a.x+Math.sin(t*.35+a.distance)*w*.009,y=h*a.y,scale=(h/340)*a.size;
    const color=a.team?'#8fbce8':a.visible||!settings.visibilityColors?settings.accent:'#dfaa7f';
    ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);
    const bones=[[[0,-24],[0,-9],[2,20],[0,39]], [[0,-8],[-14,0],[-20,21]], [[0,-8],[14,0],[18,18]], [[0,39],[-11,59],[-14,82]], [[0,39],[12,60],[15,82]]];
    ctx.shadowBlur=settings.glow?18:0;ctx.shadowColor=color;
    line([[0,-19],[0,37]],'#24292b',17);line([[-12,-2],[-18,24]],'#25292b',9);line([[12,-2],[20,20]],'#25292b',9);line([[-2,35],[-14,80]],'#202529',10);line([[4,35],[17,80]],'#202529',10);
    ctx.fillStyle='#383f40';ctx.beginPath();ctx.ellipse(0,-28,7,9,0,0,Math.PI*2);ctx.fill();
    if(settings.glow){ctx.globalAlpha=.25;ctx.strokeStyle=color;ctx.lineWidth=4;ctx.strokeRect(-26,-42,52,130);ctx.globalAlpha=1;}
    if(settings.skeleton){bones.forEach(b=>line(b,color,1.3));ctx.strokeStyle=color;ctx.lineWidth=1.2;ctx.beginPath();ctx.arc(0,-28,6,0,Math.PI*2);ctx.stroke();}
    const corners=[[[-29,-43],[-35,-43],[-35,-34]],[[29,-43],[35,-43],[35,-34]],[[-35,78],[-35,87],[-29,87]],[[29,87],[35,87],[35,78]]];corners.forEach(b=>line(b,color+'80'));
    ctx.font='7px monospace';ctx.textAlign='center';ctx.fillStyle=color;ctx.fillText(a.name,0,-51);ctx.fillStyle='#b7bdba';ctx.fillText(`${a.distance}m`,0,101);
    if(settings.health){ctx.fillStyle='#222a25';ctx.fillRect(-42,-43,3,130);ctx.fillStyle='#a4cb98';ctx.fillRect(-42,87-130*a.health/100,3,130*a.health/100);ctx.font='6px monospace';ctx.fillText(a.health,-41,-47);}
    if(settings.armor){ctx.fillStyle='#293038';ctx.fillRect(-27,91,54,2);ctx.fillStyle='#90b4cd';ctx.fillRect(-27,91,54*a.armor/100,2);}
    if(settings.sound){ctx.save();ctx.scale(1,.3);ctx.strokeStyle=color+'60';ctx.beginPath();ctx.arc(0,280,20+(t*15%25),0,Math.PI*2);ctx.stroke();ctx.restore();}
    ctx.restore();
  }
  function radar(w,h,t,mini=false){
    const radius=mini?Math.min(w,h)*.16:Math.min(w,h)*.37,cx=mini?w-radius-21:w/2,cy=mini?radius+45:h/2+6;
    ctx.save();ctx.translate(cx,cy);ctx.fillStyle='#11171de8';ctx.beginPath();ctx.arc(0,0,radius,0,Math.PI*2);ctx.fill();
    ctx.save();ctx.beginPath();ctx.arc(0,0,radius,0,Math.PI*2);ctx.clip();
    ctx.strokeStyle='#73817d20';ctx.lineWidth=1;for(let i=-radius;i<radius;i+=radius/4){line([[i,-radius],[i,radius]],'#73817d15');line([[-radius,i],[radius,i]],'#73817d15');}
    ctx.rotate(.25);ctx.strokeStyle='#626e7330';ctx.lineWidth=radius*.13;ctx.strokeRect(-radius*.8,-radius*.35,radius*.9,radius*.7);ctx.strokeRect(radius*.32,-radius*.9,radius*.4,radius*1.4);ctx.restore();
    for(const r of [.33,.66,1]){ctx.strokeStyle='#85958d25';ctx.lineWidth=1;ctx.beginPath();ctx.arc(0,0,radius*r,0,Math.PI*2);ctx.stroke();}
    line([[-radius,0],[radius,0]],'#85958d25');line([[0,-radius],[0,radius]],'#85958d25');
    const sweep=ctx.createConicGradient(t*.12,0,0);sweep.addColorStop(0,'#a995ff00');sweep.addColorStop(.92,'#a995ff00');sweep.addColorStop(1,'#a995ff18');ctx.fillStyle=sweep;ctx.beginPath();ctx.arc(0,0,radius,0,Math.PI*2);ctx.fill();
    for(const a of actors){if((a.team&&!settings.teammates)||a.distance>settings.espRange)continue;const angle=a.x*9;ctx.fillStyle=a.team?'#8fbce8':a.visible||!settings.visibilityColors?settings.accent:'#dfaa7f';ctx.beginPath();ctx.arc(Math.cos(angle)*radius*a.distance/90,Math.sin(angle)*radius*a.distance/90,mini?2:4,0,Math.PI*2);ctx.fill();}
    polygon([[0,-6],[-4,5],[0,2],[4,5]],'#e5dcec');ctx.fillStyle='#8a9196';ctx.font=`${mini?7:10}px monospace`;ctx.textAlign='center';ctx.fillText('N',0,-radius+12);if(!mini)ctx.fillText('SYNTHETIC POSITIONS',0,radius+23);ctx.restore();
  }
  function draw(now){
    if(!canvas.isConnected)return;
    if(now-last<33){animation=requestAnimationFrame(draw);return;}last=now;
    const dpr=Math.min(devicePixelRatio||1,2),w=canvas.clientWidth,h=canvas.clientHeight;
    if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);const t=reduced?1:now/1000;
    if(view==='radar'){
      ctx.fillStyle='#141b20';ctx.fillRect(0,0,w,h);
      if(settings.radar)radar(w,h,t);else{ctx.fillStyle='#9b93ab';ctx.font='12px sans-serif';ctx.textAlign='center';ctx.fillText('Radar preview disabled',w/2,h/2);}
    }else{
      const sky=ctx.createLinearGradient(0,0,0,h);sky.addColorStop(0,'#4c5a5b');sky.addColorStop(.43,'#7f8982');sky.addColorStop(.44,'#4a4d47');sky.addColorStop(1,'#242a2a');ctx.fillStyle=sky;ctx.fillRect(0,0,w,h);
      polygon([[0,0],[w*.34,0],[w*.34,h*.52],[0,h*.89]],'#515450','#73746a');
      polygon([[0,h*.15],[w*.24,h*.24],[w*.24,h*.53],[0,h*.74]],'#3e4442');
      polygon([[w*.61,0],[w,0],[w,h*.8],[w*.61,h*.5]],'#62675f','#848a7f');
      polygon([[w*.72,h*.14],[w*.93,h*.1],[w*.93,h*.57],[w*.72,h*.48]],'#353e3d','#73796d');
      polygon([[w*.35,h*.22],[w*.60,h*.22],[w*.60,h*.48],[w*.35,h*.48]],'#929486');
      polygon([[w*.40,h*.31],[w*.51,h*.31],[w*.51,h*.49],[w*.40,h*.49]],'#303c3d');
      for(let n=0;n<7;n++)line([[0,h*(.1+n*.1)],[w*.34,h*(.26+n*.043)]],'#272f2c35');
      for(let n=0;n<9;n++)line([[w*.45,h*.43],[w*(n/5-.4),h]],'#b6b49c10');
      for(let n=0;n<5;n++){const yy=h*(.48+n*n*.023);line([[0,yy],[w,yy]],'#b5b49f0c');}
      line([[w*.2,0],[w*.2,h*.58]],'#a2a18b44',2);line([[w*.65,0],[w*.65,h*.52]],'#313a36',3);
      // Crates give the sample scene depth, without borrowing game assets.
      polygon([[w*.06,h*.49],[w*.25,h*.44],[w*.25,h*.73],[w*.06,h*.86]],'#414943','#697063');polygon([[w*.25,h*.44],[w*.31,h*.49],[w*.31,h*.68],[w*.25,h*.73]],'#303b35');polygon([[w*.06,h*.49],[w*.13,h*.44],[w*.31,h*.42],[w*.25,h*.44]],'#686d5e');
      actors.forEach(a=>actor(a,t,w,h));
      if(settings.tracers)line([[w*.49,h*.92],[w*.39,h*.44]],settings.accent+'50');
      if(settings.radar)radar(w,h,t,true);
      line([[w/2-5,h/2],[w/2+5,h/2]],'#d1d5cc70');line([[w/2,h/2-5],[w/2,h/2+5]],'#d1d5cc70');
      if(settings.hitmarker&&Math.sin(t*1.4)>.7){for(const s of [-1,1])for(const r of [-1,1])line([[w/2+s*5,h/2+r*5],[w/2+s*9,h/2+r*9]],'#e6dee9');}
      if(settings.bomb){ctx.fillStyle='#13191cc9';ctx.fillRect(14,h-48,126,28);ctx.fillStyle='#d8c1a6';ctx.font='8px monospace';ctx.textAlign='left';ctx.fillText('BOMB  00:28  ·  DEMO',23,h-36);ctx.fillStyle='#89998f';ctx.fillText('DEFUSE 00:05',23,h-26);}
      if(settings.spectators){ctx.font='7px monospace';ctx.textAlign='right';ctx.fillStyle='#c6c9be99';ctx.fillText('SAMPLE SPECTATORS · 2',w-15,h-51);ctx.fillText('observer_01  /  observer_02',w-15,h-40);}
      const vignette=ctx.createRadialGradient(w/2,h/2,h*.1,w/2,h/2,w*.7);vignette.addColorStop(0,'#10141c00');vignette.addColorStop(1,'#0a0d1255');ctx.fillStyle=vignette;ctx.fillRect(0,0,w,h);
    }
    animation=requestAnimationFrame(draw);
  }
  animation=requestAnimationFrame(draw);
}
async function boot(){
  try{state=await api('/api/state');settings={...state.settings};render();}
  catch(error){connection(false);$('#content').innerHTML='<section class="panel"><div class="config-body"><h2>Companion unavailable</h2><p class="help-line">Start the companion and reload this page to reconnect.</p><button class="button primary" id="retry">Reconnect</button></div></section>';$('#retry').onclick=boot;return;}
  setTimeout(poll,3000);
}
async function poll(){
  try{const next=await api('/api/state');connection(true,next);}
  catch{connection(false);}
  setTimeout(poll,3000);
}
boot();
