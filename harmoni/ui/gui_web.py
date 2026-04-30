"""Harmoni OS — Web GUI (Sofia OS design).

Three-panel layout:
  LEFT   — Sidebar: logo, user, nav, new intent button
  CENTER — Main: greeting, prompt, quick actions, activity timeline
  RIGHT  — Status: CPU, memory, disk, network, suggestions

Dark mode + purple neon accents + glassmorphism.
"""

import json
import logging
import os
import platform
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

from harmoni.core.bridge import HarmoniBridge
from harmoni.core.humanizer import humanize_error

logger = logging.getLogger(__name__)

_HOST = "127.0.0.1"
_PORT = 7777
_bridge: HarmoniBridge = None  # type: ignore

_USER = os.environ.get("USER", "User")
_GREETING = "Bom dia" if time.localtime().tm_hour < 12 else (
    "Boa tarde" if time.localtime().tm_hour < 18 else "Boa noite"
)

_HTML = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Harmoni OS</title>
<style>
/* ── Reset & Base ─────────────────────────────────────── */
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0a0a0f;
  --bg-panel:rgba(16,16,24,0.75);
  --bg-card:rgba(26,28,38,0.65);
  --bg-card-hover:rgba(42,47,58,0.75);
  --bg-input:rgba(22,22,32,0.8);
  --border:rgba(255,255,255,0.06);
  --border-focus:rgba(124,111,247,0.5);
  --fg:#e2e2e8;
  --fg-dim:#6b6b7b;
  --fg-muted:#8a8a9a;
  --accent:#7c6ff7;
  --accent-glow:rgba(124,111,247,0.25);
  --success:#4ade80;
  --warning:#facc15;
  --error:#f87171;
  --purple-soft:#a78bfa;
  --radius:12px;
  --radius-lg:16px;
}
body{
  background:var(--bg);color:var(--fg);
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  height:100vh;overflow:hidden;
  display:grid;
  grid-template-columns:240px 1fr 280px;
  -webkit-font-smoothing:antialiased;
}

/* ── Responsive ───────────────────────────────────────── */
@media(max-width:1200px){
  body{grid-template-columns:220px 1fr 260px}
}
@media(max-width:1024px){
  body{grid-template-columns:200px 1fr 0}
  .status-panel{display:none}
}
@media(max-width:768px){
  body{grid-template-columns:1fr;grid-template-rows:auto 1fr}
  .sidebar{
    flex-direction:row;padding:8px 12px;gap:4px;
    overflow-x:auto;border-right:none;border-bottom:1px solid var(--border);
  }
  .sidebar-brand,.sidebar-user,.sidebar-footer,.btn-intent{display:none}
  .nav-item{padding:8px 10px;font-size:11px;white-space:nowrap}
  .nav-item .icon{font-size:14px;width:auto}
  .status-panel{display:none}
  .main{padding:16px}
  .quick-grid{grid-template-columns:repeat(2,1fr)}
  .greeting h1{font-size:18px}
  .prompt-wrap input{font-size:14px;padding:12px 0}
  .file-actions{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:480px){
  body{grid-template-columns:1fr;grid-template-rows:auto 1fr}
  .sidebar{padding:6px 8px}
  .nav-item{padding:6px 8px;font-size:10px}
  .main{padding:12px}
  .quick-grid{grid-template-columns:1fr}
  .file-actions{grid-template-columns:1fr}
  .greeting h1{font-size:16px}
  .prompt-wrap{padding:0 12px}
  .prompt-wrap input{font-size:13px;padding:10px 0}
  .qcard{padding:12px 10px}
}

/* ── Sidebar (Left) ───────────────────────────────────── */
.sidebar{
  background:var(--bg-panel);
  border-right:1px solid var(--border);
  backdrop-filter:blur(20px);
  display:flex;flex-direction:column;
  padding:24px 16px;
  gap:8px;
}
.sidebar-brand{
  display:flex;align-items:center;gap:10px;
  padding:0 8px 20px;border-bottom:1px solid var(--border);margin-bottom:12px;
}
.sidebar-brand .logo{
  width:36px;height:36px;border-radius:10px;
  background:linear-gradient(135deg,var(--accent),#a78bfa);
  display:flex;align-items:center;justify-content:center;
  font-size:18px;font-weight:700;color:#fff;
}
.sidebar-brand .brand-text{font-size:14px;font-weight:600;color:var(--fg)}
.sidebar-brand .brand-sub{font-size:10px;color:var(--fg-dim)}

.sidebar-user{
  display:flex;align-items:center;gap:10px;
  padding:12px;border-radius:var(--radius);
  background:var(--bg-card);margin-bottom:8px;
}
.sidebar-user .avatar{
  width:34px;height:34px;border-radius:50%;
  background:linear-gradient(135deg,#7c6ff7,#a78bfa);
  display:flex;align-items:center;justify-content:center;
  font-size:14px;font-weight:600;color:#fff;
}
.sidebar-user .user-info{font-size:12px}
.sidebar-user .user-name{color:var(--fg);font-weight:500}
.sidebar-user .user-role{color:var(--fg-dim);font-size:10px}

.btn-intent{
  display:flex;align-items:center;justify-content:center;gap:8px;
  padding:11px;border-radius:var(--radius);
  background:linear-gradient(135deg,var(--accent),#9061f9);
  color:#fff;font-size:13px;font-weight:500;
  border:none;cursor:pointer;margin:8px 0 12px;
  transition:box-shadow .2s;
}
.btn-intent:hover{box-shadow:0 0 20px var(--accent-glow)}

.nav-item{
  display:flex;align-items:center;gap:10px;
  padding:9px 12px;border-radius:8px;
  font-size:12px;color:var(--fg-muted);cursor:pointer;
  transition:background .15s,color .15s;
}
.nav-item:hover,.nav-item.active{background:var(--bg-card);color:var(--fg)}
.nav-item .icon{font-size:15px;width:20px;text-align:center}

.sidebar-footer{
  margin-top:auto;padding:12px 8px 0;
  border-top:1px solid var(--border);
  font-size:10px;color:var(--fg-dim);line-height:1.6;
}

/* ── Main Panel (Center) ──────────────────────────────── */
.main{
  padding:32px 40px;overflow-y:auto;
  display:flex;flex-direction:column;gap:24px;
}
.greeting h1{font-size:24px;font-weight:600;color:var(--fg)}
.greeting h1 span{color:var(--accent)}
.greeting p{font-size:13px;color:var(--fg-dim);margin-top:4px}

.prompt-wrap{
  border:1.5px solid var(--border);border-radius:var(--radius-lg);
  background:var(--bg-input);
  transition:border-color .2s,box-shadow .2s;
  display:flex;align-items:center;padding:0 16px;
}
.prompt-wrap:focus-within{
  border-color:var(--border-focus);
  box-shadow:0 0 24px var(--accent-glow);
}
.prompt-wrap .prompt-icon{font-size:18px;color:var(--fg-dim);margin-right:12px}
.prompt-wrap input{
  flex:1;padding:16px 0;font-size:15px;
  color:var(--fg);background:transparent;border:none;outline:none;
  font-family:inherit;
}
.prompt-wrap input::placeholder{color:var(--fg-dim)}
.prompt-wrap .prompt-send{
  background:var(--accent);border:none;border-radius:8px;
  padding:8px 14px;cursor:pointer;color:#fff;font-size:12px;
  font-weight:500;transition:background .15s,transform .1s;
  position:relative;overflow:hidden;
}
.prompt-wrap .prompt-send:hover{background:#6b5ce7}
.prompt-wrap .prompt-send:active{transform:scale(0.94)}

/* Instant feedback states */
.prompt-wrap.processing{
  border-color:var(--accent);
  box-shadow:0 0 24px var(--accent-glow);
  animation:processingPulse 2s ease infinite;
}
.prompt-wrap.processing .prompt-icon{
  animation:iconSpin 1s linear infinite;
}
.prompt-wrap.processing input{opacity:0.5;pointer-events:none}
@keyframes processingPulse{
  0%,100%{box-shadow:0 0 16px var(--accent-glow)}
  50%{box-shadow:0 0 32px var(--accent-glow)}
}
@keyframes iconSpin{
  from{transform:rotate(0deg)}to{transform:rotate(360deg)}
}

/* Mic button */
.mic-btn{
  width:36px;height:36px;border-radius:50%;border:none;
  background:var(--bg-card);color:var(--fg-dim);font-size:16px;
  cursor:pointer;margin-left:8px;transition:all .15s;
  display:flex;align-items:center;justify-content:center;
  position:relative;
}
.mic-btn:hover{background:var(--bg-card-hover);color:var(--fg)}
.mic-btn.listening{
  background:var(--accent);color:#fff;
  animation:micGlow 1.5s ease infinite;
}
@keyframes micGlow{
  0%,100%{box-shadow:0 0 8px var(--accent-glow)}
  50%{box-shadow:0 0 24px rgba(124,111,247,0.5)}
}

/* Waveform (shown during STT) */
.waveform{
  display:none;align-items:center;gap:2px;height:20px;margin-left:8px;
}
.waveform.active{display:flex}
.waveform-bar{
  width:3px;border-radius:2px;background:var(--accent);
  animation:waveBar 0.8s ease-in-out infinite;
}
.waveform-bar:nth-child(1){height:8px;animation-delay:0s}
.waveform-bar:nth-child(2){height:14px;animation-delay:0.1s}
.waveform-bar:nth-child(3){height:20px;animation-delay:0.2s}
.waveform-bar:nth-child(4){height:14px;animation-delay:0.3s}
.waveform-bar:nth-child(5){height:8px;animation-delay:0.4s}
@keyframes waveBar{
  0%,100%{transform:scaleY(0.4);opacity:0.5}
  50%{transform:scaleY(1);opacity:1}
}

/* Ripple effect on buttons */
.ripple{
  position:absolute;border-radius:50%;
  background:rgba(255,255,255,0.3);
  transform:scale(0);animation:rippleAnim .4s ease-out;
  pointer-events:none;
}
@keyframes rippleAnim{to{transform:scale(2.5);opacity:0}}

/* ── Unified Loading Spinner (#83) ────────────────────── */
.loading-spinner{
  display:inline-block;width:16px;height:16px;
  border:2px solid rgba(124,111,247,0.2);
  border-top-color:var(--accent);border-radius:50%;
  animation:spinnerRotate .6s linear infinite;
}
.loading-spinner.sm{width:12px;height:12px;border-width:1.5px}
.loading-spinner.lg{width:24px;height:24px;border-width:3px}
@keyframes spinnerRotate{to{transform:rotate(360deg)}}

/* Unified loading overlay (for any section) */
.loading-state{
  display:flex;align-items:center;justify-content:center;
  gap:10px;padding:20px;color:var(--fg-dim);font-size:12px;
  animation:loadFadeIn .2s ease;
}
@keyframes loadFadeIn{from{opacity:0}to{opacity:1}}

/* ── Enhanced interactions (#80, #81) ─────────────────── */
.qcard:active{transform:scale(0.97);transition:transform .08s}
.nav-item{position:relative;overflow:hidden}
.nav-item:active{transform:scale(0.97)}
.nav-item::after{
  content:'';position:absolute;inset:0;
  background:radial-gradient(circle at var(--ripple-x,50%) var(--ripple-y,50%),rgba(124,111,247,0.15) 0%,transparent 70%);
  opacity:0;transition:opacity .3s;pointer-events:none;
}
.nav-item:active::after{opacity:1}

/* Timeline items fade in */
.tl-item{animation:tlSlideIn .3s ease;animation-fill-mode:both}
.tl-item:nth-child(1){animation-delay:0s}
.tl-item:nth-child(2){animation-delay:.05s}
.tl-item:nth-child(3){animation-delay:.1s}
.tl-item:nth-child(4){animation-delay:.15s}
.tl-item:nth-child(5){animation-delay:.2s}
@keyframes tlSlideIn{from{opacity:0;transform:translateX(-8px)}to{opacity:1;transform:translateX(0)}}

/* Metric bars animate on load */
.metric-fill{animation:barGrow .8s ease;animation-fill-mode:both}
@keyframes barGrow{from{width:0%}}

/* Cards stagger fade-in */
.list-card{animation:cardFadeIn .25s ease;animation-fill-mode:both}
.list-card:nth-child(1){animation-delay:0s}
.list-card:nth-child(2){animation-delay:.04s}
.list-card:nth-child(3){animation-delay:.08s}
.list-card:nth-child(4){animation-delay:.12s}
.list-card:nth-child(5){animation-delay:.16s}
@keyframes cardFadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}

/* Quick Actions */
.section-title{font-size:13px;font-weight:600;color:var(--fg-muted);margin-bottom:12px}
.quick-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.qcard{
  background:var(--bg-card);border:1px solid var(--border);
  border-radius:var(--radius);padding:16px 14px;
  cursor:pointer;transition:background .15s,border-color .15s,transform .15s;
}
.qcard:hover{
  background:var(--bg-card-hover);border-color:rgba(124,111,247,0.2);
  transform:translateY(-2px);
}
.qcard .qicon{font-size:22px;margin-bottom:8px}
.qcard .qlabel{font-size:12px;font-weight:500;color:var(--fg)}
.qcard .qdesc{font-size:10px;color:var(--fg-dim);margin-top:3px}

/* Execution Feed */
#feed{min-height:20px}
.step{
  font-size:13px;color:var(--fg-muted);padding:6px 0;
  display:flex;align-items:center;gap:8px;
  opacity:0;transform:translateY(5px);animation:stepIn .3s ease forwards;
}
.step::before{
  content:'';display:inline-block;width:6px;height:6px;
  border-radius:50%;background:var(--accent);flex-shrink:0;
}
.step.done{color:var(--fg-dim)}
.step.done::before{background:var(--success)}
@keyframes stepIn{to{opacity:1;transform:translateY(0)}}
@keyframes pulse{0%,100%{opacity:.3}50%{opacity:1}}
.step.thinking::after{
  content:'';display:inline-block;width:5px;height:5px;
  background:var(--accent);border-radius:50%;margin-left:6px;
  animation:pulse 1s ease infinite;
}
.stream-progress{
  height:2px;background:rgba(124,111,247,0.15);border-radius:1px;
  margin:8px 0;overflow:hidden;
}
.stream-progress-bar{
  height:100%;background:linear-gradient(90deg,var(--accent),#a78bfa);
  border-radius:1px;transition:width .3s ease;width:0%;
}

/* Result */
#result{text-align:center;opacity:0;transform:translateY(6px);transition:opacity .4s,transform .4s}
#result.visible{opacity:1;transform:translateY(0);animation:resultFadeIn .4s ease}
#result-title{font-size:16px;font-weight:600;margin-bottom:4px}
@keyframes resultFadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
#result-title.success{color:var(--success)}
#result-title.recovered{color:var(--warning)}
#result-title.error{color:var(--error)}
#result-body{font-size:13px;color:var(--fg-muted);line-height:1.6;white-space:pre-line}

/* Confirm */
#confirm{
  display:none;text-align:center;
  background:var(--bg-card);border:1px solid var(--border);
  border-radius:var(--radius);padding:18px 24px;
}
#confirm.visible{display:block}
#confirm-msg{font-size:13px;color:var(--fg);margin-bottom:14px}
.cbtn{
  font-size:12px;font-weight:500;padding:8px 22px;
  border:none;border-radius:8px;cursor:pointer;font-family:inherit;
}
.cbtn-yes{background:var(--accent);color:#fff;margin-right:8px}
.cbtn-yes:hover{background:#6b5ce7}
.cbtn-no{background:var(--bg-input);color:var(--fg-dim)}
.cbtn-no:hover{background:rgba(42,47,58,0.8)}

/* Activity Timeline */
.timeline{display:flex;flex-direction:column;gap:8px}
.tl-item{
  display:flex;align-items:center;gap:10px;
  padding:10px 12px;border-radius:8px;
  background:var(--bg-card);border:1px solid var(--border);
  font-size:11px;
}
.tl-icon{font-size:14px}
.tl-icon.success{color:var(--success)}
.tl-icon.error{color:var(--error)}
.tl-icon.recovered{color:var(--warning)}
.tl-text{flex:1;color:var(--fg-muted)}
.tl-time{color:var(--fg-dim);font-size:10px}

/* ── Right Panel ──────────────────────────────────────── */
.status-panel{
  background:var(--bg-panel);
  border-left:1px solid var(--border);
  backdrop-filter:blur(20px);
  padding:24px 16px;overflow-y:auto;
  display:flex;flex-direction:column;gap:16px;
}
.status-title{font-size:13px;font-weight:600;color:var(--fg-muted);margin-bottom:8px}

.metric{
  background:var(--bg-card);border:1px solid var(--border);
  border-radius:var(--radius);padding:14px;
}
.metric-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.metric-label{font-size:11px;color:var(--fg-muted)}
.metric-value{font-size:12px;font-weight:600;color:var(--fg)}
.metric-bar{height:6px;border-radius:3px;background:rgba(255,255,255,0.06);overflow:hidden}
.metric-fill{height:100%;border-radius:3px;transition:width .6s ease}
.metric-fill.cpu{background:linear-gradient(90deg,var(--accent),#a78bfa)}
.metric-fill.mem{background:linear-gradient(90deg,#06b6d4,#22d3ee)}
.metric-fill.disk{background:linear-gradient(90deg,var(--success),#86efac)}
.metric-fill.net{background:linear-gradient(90deg,#f59e0b,var(--warning))}

.env-info{
  background:var(--bg-card);border:1px solid var(--border);
  border-radius:var(--radius);padding:14px;
  font-size:10px;color:var(--fg-dim);line-height:1.8;
}
.env-info strong{color:var(--fg-muted)}

.security-badge{
  display:flex;align-items:center;gap:8px;
  padding:12px;border-radius:var(--radius);
  background:rgba(74,222,128,0.08);border:1px solid rgba(74,222,128,0.15);
  font-size:11px;color:var(--success);
}

.suggestions{display:flex;flex-direction:column;gap:6px}
.sug-item{
  display:flex;align-items:center;gap:8px;
  padding:10px 12px;border-radius:8px;
  background:var(--bg-card);border:1px solid var(--border);
  font-size:11px;color:var(--fg-muted);cursor:pointer;
  transition:background .15s;
}
.sug-item:hover{background:var(--bg-card-hover)}
.sug-item .sug-icon{font-size:14px}

/* ── Pages (crossfade transitions #82) ────────────────── */
.page{
  display:flex;flex-direction:column;gap:20px;
  animation:pageFadeIn .25s ease;
}
.page.hidden{display:none}
@keyframes pageFadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.page-header h2{font-size:20px;font-weight:600;color:var(--fg)}
.page-header p{font-size:12px;color:var(--fg-dim);margin-top:4px}

.card-list{display:flex;flex-direction:column;gap:8px}
.list-card{
  display:flex;align-items:center;gap:12px;
  padding:14px 16px;border-radius:var(--radius);
  background:var(--bg-card);border:1px solid var(--border);
  transition:background .15s;
}
.list-card:hover{background:var(--bg-card-hover)}
.list-card .lc-icon{font-size:20px;width:28px;text-align:center}
.list-card .lc-body{flex:1}
.list-card .lc-title{font-size:12px;font-weight:500;color:var(--fg)}
.list-card .lc-sub{font-size:10px;color:var(--fg-dim);margin-top:2px}
.list-card .lc-badge{
  font-size:10px;padding:3px 10px;border-radius:6px;
  background:rgba(124,111,247,0.12);color:var(--accent);
}
.list-card .lc-action{
  font-size:11px;padding:5px 14px;border-radius:6px;
  background:var(--accent);color:#fff;border:none;cursor:pointer;
  transition:background .15s;
}
.list-card .lc-action:hover{background:#6b5ce7}

.file-actions{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}

/* Settings */
.settings-grid{display:flex;flex-direction:column;gap:8px}
.setting-item{
  display:flex;justify-content:space-between;align-items:center;
  padding:14px 16px;border-radius:var(--radius);
  background:var(--bg-card);border:1px solid var(--border);
}
.setting-label{font-size:12px;color:var(--fg-muted)}
.setting-value{font-size:12px;color:var(--fg);font-weight:500}
</style>
</head>
<body>
"""

_HTML_BODY = """
<!-- ── SIDEBAR ────────────────────────────────────────── -->
<div class="sidebar">
  <div class="sidebar-brand">
    <div class="logo">H</div>
    <div><div class="brand-text">Harmoni OS</div><div class="brand-sub">AI-first interface</div></div>
  </div>

  <div class="sidebar-user">
    <div class="avatar">{{INITIAL}}</div>
    <div class="user-info">
      <div class="user-name">{{USER}}</div>
      <div class="user-role">Developer</div>
    </div>
  </div>

  <button class="btn-intent" onclick="navTo('home')">✦ Nova Intenção</button>

  <div class="nav-item active" data-page="home" onclick="navTo('home')"><span class="icon">🏠</span> Início</div>
  <div class="nav-item" data-page="projects" onclick="navTo('projects')"><span class="icon">📂</span> Projetos</div>
  <div class="nav-item" data-page="files" onclick="navTo('files')"><span class="icon">📁</span> Arquivos</div>
  <div class="nav-item" data-page="system" onclick="navTo('system')"><span class="icon">⚙️</span> Sistema</div>
  <div class="nav-item" data-page="services" onclick="navTo('services')"><span class="icon">🔌</span> Serviços</div>
  <div class="nav-item" data-page="history" onclick="navTo('history')"><span class="icon">📋</span> Histórico</div>
  <div class="nav-item" data-page="settings" onclick="navTo('settings')"><span class="icon">🔧</span> Configurações</div>

  <div class="sidebar-footer">
    Harmoni v{{VERSION}}
  </div>
</div>

<!-- ── MAIN PANEL ─────────────────────────────────────── -->
<div class="main" id="main-panel">

  <!-- ══ PAGE: HOME ══ -->
  <div class="page" id="page-home">
    <div class="greeting">
      <h1>{{GREETING}}, <span>{{USER}}</span>.</h1>
      <p>O que vamos construir hoje?</p>
    </div>

    <div class="prompt-wrap" id="prompt-wrap">
      <span class="prompt-icon" id="prompt-icon">✦</span>
      <input id="input" type="text" placeholder="Descreva o que você precisa..." autofocus autocomplete="off" spellcheck="false">
      <div class="waveform" id="waveform">
        <div class="waveform-bar"></div><div class="waveform-bar"></div><div class="waveform-bar"></div><div class="waveform-bar"></div><div class="waveform-bar"></div>
      </div>
      <button class="mic-btn" id="mic-btn" onclick="toggleMic()" title="Falar">🎙️</button>
      <button class="prompt-send" onclick="submitInput()">Enviar</button>
    </div>

    <div>
      <div class="section-title">⚡ Ações Rápidas</div>
      <div class="quick-grid" id="quick-grid">
        <div class="qcard" onclick="card('organize my downloads')"><div class="qicon">📁</div><div class="qlabel">Organizar Arquivos</div><div class="qdesc">Organizar downloads por tipo</div></div>
        <div class="qcard" onclick="card('my computer is slow')"><div class="qicon">📊</div><div class="qlabel">Status do Sistema</div><div class="qdesc">Verificar saúde do sistema</div></div>
        <div class="qcard" onclick="card('kill process on port 3000')"><div class="qicon">🔌</div><div class="qlabel">Gerenciar Processos</div><div class="qdesc">Encerrar processos por porta</div></div>
        <div class="qcard" onclick="card('status')"><div class="qicon">🌐</div><div class="qlabel">Serviços Ativos</div><div class="qdesc">Ver portas e serviços</div></div>
        <div class="qcard" onclick="card('start my backend')"><div class="qicon">🚀</div><div class="qlabel">Iniciar Projeto</div><div class="qdesc">Detectar e iniciar servidor</div></div>
        <div class="qcard" onclick="card('show logs')"><div class="qicon">📋</div><div class="qlabel">Ver Logs</div><div class="qdesc">Analisar erros recentes</div></div>
      </div>
    </div>

    <div id="feed"></div>
    <div id="confirm"><div id="confirm-msg"></div><button class="cbtn cbtn-yes" onclick="confirmYes()">Confirmar</button><button class="cbtn cbtn-no" onclick="confirmNo()">Cancelar</button></div>
    <div id="result"><div id="result-title"></div><div id="result-body"></div></div>

    <div id="activity-section">
      <div class="section-title">🕐 Atividades Recentes</div>
      <div class="timeline" id="timeline"></div>
    </div>
  </div>

  <!-- ══ PAGE: PROJECTS ══ -->
  <div class="page hidden" id="page-projects">
    <div class="page-header"><h2>📂 Projetos</h2><p>Projetos detectados no sistema</p></div>
    <div id="projects-list" class="card-list"></div>
  </div>

  <!-- ══ PAGE: FILES ══ -->
  <div class="page hidden" id="page-files">
    <div class="page-header"><h2>📁 Arquivos</h2><p>Navegação rápida de diretórios</p></div>
    <div class="file-actions">
      <div class="qcard" onclick="card('organize my downloads');navTo('home')"><div class="qicon">📥</div><div class="qlabel">Organizar Downloads</div></div>
      <div class="qcard" onclick="card('organize my desktop');navTo('home')"><div class="qicon">🖥️</div><div class="qlabel">Organizar Desktop</div></div>
      <div class="qcard" onclick="card('organize my documents');navTo('home')"><div class="qicon">📄</div><div class="qlabel">Organizar Documentos</div></div>
    </div>
    <div class="section-title" style="margin-top:20px">📂 Diretórios</div>
    <div id="files-list" class="card-list"></div>
  </div>

  <!-- ══ PAGE: SYSTEM ══ -->
  <div class="page hidden" id="page-system">
    <div class="page-header"><h2>⚙️ Sistema</h2><p>Informações e saúde do sistema</p></div>
    <div id="system-info" class="card-list"></div>
    <div class="section-title" style="margin-top:20px">🔧 Ações do Sistema</div>
    <div class="quick-grid">
      <div class="qcard" onclick="card('my computer is slow');navTo('home')"><div class="qicon">📊</div><div class="qlabel">Diagnóstico</div><div class="qdesc">Verificar performance</div></div>
      <div class="qcard" onclick="card('free disk space');navTo('home')"><div class="qicon">🧹</div><div class="qlabel">Limpar Sistema</div><div class="qdesc">Liberar espaço em disco</div></div>
      <div class="qcard" onclick="card('show logs');navTo('home')"><div class="qicon">📋</div><div class="qlabel">Ver Logs</div><div class="qdesc">Analisar erros recentes</div></div>
    </div>
  </div>

  <!-- ══ PAGE: SERVICES ══ -->
  <div class="page hidden" id="page-services">
    <div class="page-header"><h2>🔌 Serviços</h2><p>Portas e processos ativos</p></div>
    <div id="services-list" class="card-list"></div>
    <button class="btn-intent" style="margin-top:16px;width:auto;padding:10px 24px" onclick="loadServices()">🔄 Atualizar</button>
  </div>

  <!-- ══ PAGE: HISTORY ══ -->
  <div class="page hidden" id="page-history">
    <div class="page-header"><h2>📋 Histórico</h2><p>Todas as ações executadas</p></div>
    <div id="history-list" class="timeline"></div>
  </div>

  <!-- ══ PAGE: SETTINGS ══ -->
  <div class="page hidden" id="page-settings">
    <div class="page-header"><h2>🔧 Configurações</h2><p>Preferências do Harmoni</p></div>
    <div class="settings-grid">
      <div class="setting-item"><div class="setting-label">Modelo Local (Ollama)</div><div class="setting-value">mistral</div></div>
      <div class="setting-item"><div class="setting-label">Modelo Remoto (Bedrock)</div><div class="setting-value">claude-3-haiku</div></div>
      <div class="setting-item"><div class="setting-label">Timeout de Comandos</div><div class="setting-value">120s</div></div>
      <div class="setting-item"><div class="setting-label">Máximo de Retries</div><div class="setting-value">1</div></div>
      <div class="setting-item"><div class="setting-label">Diretório de Dados</div><div class="setting-value">~/.harmoni</div></div>
      <div class="setting-item"><div class="setting-label">Interface</div><div class="setting-value">Web (porta 7777)</div></div>
    </div>
  </div>

</div>

<!-- ── STATUS PANEL (Right) ───────────────────────────── -->
<div class="status-panel">
  <div class="status-title">📈 Status do Sistema</div>

  <div class="metric">
    <div class="metric-header"><span class="metric-label">CPU</span><span class="metric-value" id="cpu-val">--</span></div>
    <div class="metric-bar"><div class="metric-fill cpu" id="cpu-bar" style="width:0%"></div></div>
  </div>
  <div class="metric">
    <div class="metric-header"><span class="metric-label">Memória</span><span class="metric-value" id="mem-val">--</span></div>
    <div class="metric-bar"><div class="metric-fill mem" id="mem-bar" style="width:0%"></div></div>
  </div>
  <div class="metric">
    <div class="metric-header"><span class="metric-label">Disco</span><span class="metric-value" id="disk-val">--</span></div>
    <div class="metric-bar"><div class="metric-fill disk" id="disk-bar" style="width:0%"></div></div>
  </div>
  <div class="metric">
    <div class="metric-header"><span class="metric-label">Rede</span><span class="metric-value" id="net-val">--</span></div>
    <div class="metric-bar"><div class="metric-fill net" id="net-bar" style="width:30%"></div></div>
  </div>

  <div class="env-info">
    <strong>Ambiente</strong><br>
    Host: {{HOSTNAME}}<br>
    Kernel: {{KERNEL}}<br>
    Interface: Web UI
  </div>

  <div class="security-badge">🛡️ Tudo sob controle</div>

  <div>
    <div class="status-title">💡 Sugestões para Você</div>
    <div class="suggestions">
      <div class="sug-item" onclick="card('organize my downloads')"><span class="sug-icon">📁</span> Organizar seus downloads</div>
      <div class="sug-item" onclick="card('my computer is slow')"><span class="sug-icon">🔍</span> Verificar performance</div>
      <div class="sug-item" onclick="card('show logs')"><span class="sug-icon">📋</span> Revisar logs do sistema</div>
    </div>
  </div>
</div>

<script>
const I=document.getElementById('input'),F=document.getElementById('feed'),
R=document.getElementById('result'),RT=document.getElementById('result-title'),
RB=document.getElementById('result-body'),CF=document.getElementById('confirm'),
CM=document.getElementById('confirm-msg'),QG=document.getElementById('quick-grid'),
AS=document.getElementById('activity-section'),
PW=document.getElementById('prompt-wrap'),PI=document.getElementById('prompt-icon'),
MB=document.getElementById('mic-btn'),WF=document.getElementById('waveform');
let busy=0,pend=null,currentPage='home',listening=false;

I.addEventListener('keydown',e=>{if(e.key==='Enter'&&!busy)submitInput()});

// ── Instant Feedback ──
function startProcessing(){
  busy=1;I.disabled=1;
  PW.classList.add('processing');
  QG.style.display='none';AS.style.display='none';
  clearFeed();clearResult();
  // Progress bar + thinking step appear in <50ms
  const prog=document.createElement('div');prog.className='stream-progress';
  prog.innerHTML='<div class="stream-progress-bar" id="stream-bar"></div>';
  F.appendChild(prog);
  addStep('Entendendo…',1);
}
function stopProcessing(){
  busy=0;I.disabled=0;I.value='';I.focus();
  PW.classList.remove('processing');
  QG.style.display='grid';AS.style.display='block';
}

// ── Mic / STT ──
function toggleMic(){
  if(busy)return;
  if(listening){stopListening();return}
  // INSTANT feedback (<16ms)
  listening=true;
  MB.classList.add('listening');
  WF.classList.add('active');
  I.placeholder='Escutando…';
  // Start recording via API
  fetch('/api/stt',{method:'POST'}).then(r=>r.json()).then(d=>{
    stopListening();
    if(d.text){I.value=d.text;submitInput()}
  }).catch(()=>stopListening());
}
function stopListening(){
  listening=false;
  MB.classList.remove('listening');
  WF.classList.remove('active');
  I.placeholder='Descreva o que você precisa...';
}

// ── Navigation ──
function navTo(page){
  if(currentPage===page)return;
  // Hide all pages
  document.querySelectorAll('.page').forEach(p=>p.classList.add('hidden'));
  // Show target with fresh animation
  const target=document.getElementById('page-'+page);
  if(target){
    target.classList.remove('hidden');
    // Re-trigger animation by removing and re-adding element
    target.style.animation='none';
    target.offsetHeight; // force reflow
    target.style.animation='';
  }
  // Update active nav
  document.querySelectorAll('.nav-item').forEach(n=>{
    n.classList.toggle('active',n.dataset.page===page);
  });
  currentPage=page;
  // Load data for the page
  if(page==='projects')loadProjects();
  if(page==='files')loadFiles();
  if(page==='system')loadSystemInfo();
  if(page==='services')loadServices();
  if(page==='history')loadHistory();
  if(page==='home'){I.focus();loadActivity();}
}

// ── Page data loaders ──
async function loadProjects(){
  const el=document.getElementById('projects-list');
  showLoading(el,'Buscando projetos…');
  try{
    const d=await(await fetch('/api/projects')).json();
    el.innerHTML='';
    if(!d.length){el.innerHTML='<div class="list-card"><div class="lc-icon">📭</div><div class="lc-body"><div class="lc-title">Nenhum projeto detectado</div><div class="lc-sub">Navegue até um diretório com package.json ou requirements.txt</div></div></div>';return}
    d.forEach(p=>{
      el.innerHTML+=`<div class="list-card"><div class="lc-icon">${p.type==='node'?'🟢':'🐍'}</div><div class="lc-body"><div class="lc-title">${p.name}</div><div class="lc-sub">${p.path}</div></div><span class="lc-badge">${p.type}</span><button class="lc-action" onclick="card('start my backend');navTo('home')">Iniciar</button></div>`;
    });
  }catch(e){el.innerHTML='';console.error(e)}
}

async function loadFiles(){
  const el=document.getElementById('files-list');
  showLoading(el,'Carregando…');
  try{
    const d=await(await fetch('/api/files')).json();
    el.innerHTML='';
    d.forEach(f=>{
      el.innerHTML+=`<div class="list-card"><div class="lc-icon">${f.icon}</div><div class="lc-body"><div class="lc-title">${f.name}</div><div class="lc-sub">${f.count} itens</div></div></div>`;
    });
  }catch(e){el.innerHTML='';console.error(e)}
}

async function loadSystemInfo(){
  const el=document.getElementById('system-info');
  showLoading(el,'Verificando sistema…');
  try{
    const d=await(await fetch('/status')).json();
    el.innerHTML=`
      <div class="list-card"><div class="lc-icon">💻</div><div class="lc-body"><div class="lc-title">Processador</div><div class="lc-sub">${d.cpu_cores} cores · ${d.cpu_percent}% em uso</div></div></div>
      <div class="list-card"><div class="lc-icon">🧠</div><div class="lc-body"><div class="lc-title">Memória</div><div class="lc-sub">${d.mem_used_gb} / ${d.mem_total_gb} GB (${d.mem_percent}%)</div></div></div>
      <div class="list-card"><div class="lc-icon">💾</div><div class="lc-body"><div class="lc-title">Disco</div><div class="lc-sub">${d.disk_free_gb} GB livre de ${d.disk_total_gb} GB (${d.disk_percent}%)</div></div></div>
      <div class="list-card"><div class="lc-icon">🌐</div><div class="lc-body"><div class="lc-title">Rede</div><div class="lc-sub">Enviado: ${d.net_sent_mb} MB · Recebido: ${d.net_recv_mb} MB</div></div></div>
      <div class="list-card"><div class="lc-icon">🖥️</div><div class="lc-body"><div class="lc-title">Host</div><div class="lc-sub">${d.hostname} · Kernel ${d.kernel}</div></div></div>
    `;
  }catch(e){el.innerHTML='';console.error(e)}
}

async function loadServices(){
  const el=document.getElementById('services-list');
  showLoading(el,'Verificando serviços…');
  try{
    const d=await(await fetch('/api/services')).json();
    el.innerHTML='';
    if(!d.length){el.innerHTML='<div class="list-card"><div class="lc-icon">😴</div><div class="lc-body"><div class="lc-title">Nenhum serviço ativo</div></div></div>';return}
    d.forEach(s=>{
      el.innerHTML+=`<div class="list-card"><div class="lc-icon">🔌</div><div class="lc-body"><div class="lc-title">Porta ${s.port}</div><div class="lc-sub">${s.name} · PID ${s.pid||'?'}</div></div><button class="lc-action" onclick="card('kill process on port ${s.port}');navTo('home')">Encerrar</button></div>`;
    });
  }catch(e){el.innerHTML='';console.error(e)}
}

async function loadHistory(){
  try{
    const items=await(await fetch('/api/history')).json();
    const el=document.getElementById('history-list');
    el.innerHTML='';
    if(!items.length){el.innerHTML='<div style="font-size:12px;color:var(--fg-dim);padding:12px">Nenhuma atividade registrada</div>';return}
    items.forEach(it=>{
      el.innerHTML+=`<div class="tl-item"><span class="tl-icon ${it.outcome}">${it.icon}</span><span class="tl-text">${it.text}</span><span class="tl-time">${it.time}</span></div>`;
    });
  }catch(e){console.error(e)}
}

// ── Existing functions ──
function focusInput(){navTo('home');I.focus();I.select()}
function submitInput(){if(busy)return;const t=I.value.trim();if(t)go(t)}
function card(cmd){if(busy)return;I.value=cmd;go(cmd)}

async function go(t){
  if(currentPage!=='home')navTo('home');
  startProcessing();  // INSTANT feedback (<50ms)

  // Try SSE streaming first, fallback to classic POST
  try{
    const resp=await fetch('/stream',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({i:t})});
    if(resp.ok && resp.headers.get('content-type')?.includes('text/event-stream')){
      // Remove initial thinking step — real steps will stream in
      const thinkStep=F.querySelector('.step.thinking');
      if(thinkStep)thinkStep.remove();

      const reader=resp.body.getReader();
      const decoder=new TextDecoder();
      let buf='';
      while(true){
        const{done,value}=await reader.read();
        if(done)break;
        buf+=decoder.decode(value,{stream:true});
        const lines=buf.split('\n');
        buf=lines.pop()||'';
        let evtType='',evtData='';
        for(const line of lines){
          if(line.startsWith('event: '))evtType=line.slice(7);
          else if(line.startsWith('data: ')){
            evtData=line.slice(6);
            if(evtType&&evtData){
              handleSSE(evtType,evtData,t);
              evtType='';evtData='';
            }
          }
        }
      }
    }else{
      // Fallback to classic
      const r=await resp.json();
      if(r.confirm){CM.textContent=r.confirm;CF.classList.add('visible');pend=t;stopProcessing();return}
      showResult(r);
    }
  }catch(e){clearFeed();setResult('Algo deu errado',e.message,'error');stopProcessing()}
}

function handleSSE(type,data,originalInput){
  try{
    const d=JSON.parse(data);
    if(type==='step'){
      // Update progress bar
      const bar=document.getElementById('stream-bar');
      if(bar&&d.total>0){bar.style.width=Math.round(((d.index+1)/d.total)*100)+'%'}
      else if(bar){bar.style.width='50%'}
      addStep(d.step)
    }
    else if(type==='confirm'){CM.textContent=d.confirm;CF.classList.add('visible');pend=originalInput;stopProcessing()}
    else if(type==='result'){
      // Mark all steps as done
      document.querySelectorAll('.step').forEach(e=>e.classList.add('done'));
      // Complete progress bar
      const bar=document.getElementById('stream-bar');
      if(bar)bar.style.width='100%';
      const titles={success:'Concluído',recovered:'Corrigido',error:'Problema'};
      setResult(titles[d.status]||'Concluído',d.result||'',d.status||'success');
    }
    else if(type==='done'){stopProcessing();loadActivity()}
    else if(type==='error'){
      clearFeed();setResult('Algo deu errado',d.result||'Erro desconhecido','error');stopProcessing();
    }
  }catch(e){console.error('SSE parse error',e)}
}

async function confirmYes(){
  CF.classList.remove('visible');if(!pend)return;const t=pend;pend=null;
  startProcessing();
  try{
    const r=await(await fetch('/x',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({i:t,c:1})})).json();
    showResult(r);
  }catch(e){clearFeed();setResult('Algo deu errado',e.message,'error');stopProcessing()}
}
function confirmNo(){CF.classList.remove('visible');pend=null;setResult('Cancelado','Nenhuma alteração feita','success');stopProcessing()}

function showResult(d){
  clearFeed();const s=d.steps||[];
  s.forEach((x,i)=>setTimeout(()=>addStep(x),i*300));
  const dl=s.length*300+200;
  setTimeout(()=>{
    document.querySelectorAll('.step').forEach(e=>e.classList.add('done'));
    const titles={success:'Concluído',recovered:'Corrigido',error:'Problema'};
    setResult(titles[d.status]||'Concluído',d.result||'',d.status||'success');
    stopProcessing();loadActivity();
  },dl);
}

function addStep(t,th){const e=document.createElement('div');e.className='step'+(th?' thinking':'');e.textContent=t;F.appendChild(e)}
function clearFeed(){F.innerHTML=''}
function clearResult(){R.classList.remove('visible');RT.textContent='';RB.textContent=''}
function setResult(t,b,s){RT.textContent=((s==='error'?'✗ ':'✓ '))+t;RT.className=s;RB.textContent=b;R.classList.add('visible')}

// ── Utility: Ripple effect on any element ──
function addRipple(e,el){
  const rect=el.getBoundingClientRect();
  const ripple=document.createElement('span');
  ripple.className='ripple';
  const size=Math.max(rect.width,rect.height);
  ripple.style.width=ripple.style.height=size+'px';
  ripple.style.left=(e.clientX-rect.left-size/2)+'px';
  ripple.style.top=(e.clientY-rect.top-size/2)+'px';
  el.appendChild(ripple);
  setTimeout(()=>ripple.remove(),400);
}
// Attach ripple to quick action cards
document.addEventListener('click',e=>{
  const card=e.target.closest('.qcard,.btn-intent,.prompt-send');
  if(card)addRipple(e,card);
});

// ── Utility: Show loading state in a container ──
function showLoading(container,text='Carregando…'){
  container.innerHTML=`<div class="loading-state"><span class="loading-spinner"></span>${text}</div>`;
}

async function pollStatus(){
  try{
    const d=await(await fetch('/status')).json();
    document.getElementById('cpu-val').textContent=d.cpu_percent+'%';
    document.getElementById('cpu-bar').style.width=d.cpu_percent+'%';
    document.getElementById('mem-val').textContent=d.mem_used_gb+' / '+d.mem_total_gb+' GB';
    document.getElementById('mem-bar').style.width=d.mem_percent+'%';
    document.getElementById('disk-val').textContent=d.disk_free_gb+' GB livre';
    document.getElementById('disk-bar').style.width=d.disk_percent+'%';
    document.getElementById('net-val').textContent='↑'+d.net_sent_mb+' ↓'+d.net_recv_mb+' MB';
  }catch(e){}
}

async function loadActivity(){
  try{
    const items=await(await fetch('/activity')).json();
    const tl=document.getElementById('timeline');
    tl.innerHTML='';
    if(!items.length){tl.innerHTML='<div style="font-size:11px;color:var(--fg-dim);padding:8px">Nenhuma atividade ainda</div>';return}
    items.forEach(it=>{
      const el=document.createElement('div');el.className='tl-item';
      el.innerHTML='<span class="tl-icon '+it.outcome+'">'+it.icon+'</span><span class="tl-text">'+it.text+'</span><span class="tl-time">'+it.time+'</span>';
      tl.appendChild(el);
    });
  }catch(e){}
}

pollStatus();setInterval(pollStatus,5000);
loadActivity();
</script>
</body></html>
"""


def _get_services() -> list[dict]:
    """Get list of listening ports/services."""
    from harmoni.skills.process_control import list_listening_ports
    return list_listening_ports()


def _get_projects() -> list[dict]:
    """Scan common directories for projects."""
    from pathlib import Path
    projects = []
    home = Path.home()
    scan_dirs = [home, home / "projects", home / "dev", home / "code",
                 home / "workspace", home / "repos", Path.cwd()]
    seen = set()
    for d in scan_dirs:
        if not d.is_dir():
            continue
        for child in d.iterdir():
            if not child.is_dir() or child.name.startswith(".") or child in seen:
                continue
            seen.add(child)
            if (child / "package.json").exists():
                try:
                    import json as _json
                    pkg = _json.loads((child / "package.json").read_text())
                    name = pkg.get("name", child.name)
                except Exception:
                    name = child.name
                projects.append({"name": name, "path": str(child), "type": "node"})
            elif (child / "requirements.txt").exists() or (child / "pyproject.toml").exists():
                projects.append({"name": child.name, "path": str(child), "type": "python"})
    return projects[:20]


def _get_directories() -> list[dict]:
    """Get key user directories with item counts."""
    from pathlib import Path
    home = Path.home()
    dirs = [
        ("📥", "Downloads", home / "Downloads"),
        ("🖥️", "Desktop", home / "Desktop"),
        ("📄", "Documentos", home / "Documents"),
        ("🖼️", "Imagens", home / "Pictures"),
        ("🎵", "Música", home / "Music"),
        ("🎬", "Vídeos", home / "Videos"),
    ]
    result = []
    for icon, name, path in dirs:
        if path.is_dir():
            try:
                count = sum(1 for f in path.iterdir() if not f.name.startswith("."))
            except PermissionError:
                count = 0
            result.append({"icon": icon, "name": name, "path": str(path), "count": count})
    return result


def _render_html() -> str:
    """Render the HTML with dynamic values injected."""
    import sys
    from harmoni import __version__
    html = _HTML + _HTML_BODY
    html = html.replace("{{USER}}", _USER.capitalize())
    html = html.replace("{{INITIAL}}", _USER[0].upper() if _USER else "U")
    html = html.replace("{{GREETING}}", _GREETING)
    html = html.replace("{{HOSTNAME}}", platform.node())
    html = html.replace("{{KERNEL}}", platform.release())
    html = html.replace("{{PYVER}}", f"{sys.version_info.major}.{sys.version_info.minor}")
    html = html.replace("{{VERSION}}", __version__)
    return html


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/status":
            self._json(_bridge.get_system_status())
        elif self.path == "/activity":
            self._json(_bridge.get_recent_activity())
        elif self.path == "/api/services":
            self._json(_get_services())
        elif self.path == "/api/projects":
            self._json(_get_projects())
        elif self.path == "/api/files":
            self._json(_get_directories())
        elif self.path == "/api/history":
            self._json(_bridge.get_recent_activity())
        else:
            body = _render_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        if self.path == "/stream":
            self._handle_stream()
            return
        if self.path == "/api/stt":
            self._handle_stt()
            return
        if self.path != "/x":
            self.send_response(404)
            self.end_headers()
            return
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n)) if n else {}
        inp = body.get("i", "").strip()
        confirmed = body.get("c", False)
        try:
            data = _bridge.execute_command(inp, confirmed=bool(confirmed))
            self._json(data)
        except Exception as e:
            self._json({"steps": [], "result": humanize_error(str(e)), "status": "error"})

    def _handle_stream(self):
        """SSE endpoint: streams steps in real-time as the planner executes."""
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n)) if n else {}
        inp = body.get("i", "").strip()
        confirmed = body.get("c", False)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Track whether connection is still alive
        connection_alive = True

        def on_step(step_text: str, index: int, total: int):
            """Callback: stream each step to the client in real-time."""
            nonlocal connection_alive
            if not connection_alive:
                return
            try:
                self.wfile.write(
                    f"event: step\ndata: {json.dumps({'step': step_text, 'index': index, 'total': total})}\n\n".encode()
                )
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                connection_alive = False

        try:
            data = _bridge.execute_streaming(inp, confirmed=bool(confirmed), on_step=on_step)

            if not connection_alive:
                return

            # If confirmation needed, send it as a single event
            if data.get("confirm"):
                self._sse_event("confirm", json.dumps({"confirm": data["confirm"]}))
                return

            # Send final result
            self._sse_event("result", json.dumps({
                "result": data.get("result", ""),
                "status": data.get("status", "success"),
                "voice_mode": data.get("voice_mode", "full"),
            }))
            self._sse_event("done", "{}")
        except Exception as e:
            self._sse_event("error", json.dumps({"result": humanize_error(str(e))}))

    def _sse_event(self, event: str, data: str):
        """Write a single SSE event."""
        try:
            self.wfile.write(f"event: {event}\ndata: {data}\n\n".encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_stt(self):
        """STT endpoint: record audio and return transcribed text."""
        try:
            from harmoni.infra.voice import VoiceManager
            voice = VoiceManager()
            if not voice.stt_available:
                self._json({"text": "", "error": "STT not available"})
                return
            text = voice.listen(duration=5.0)
            self._json({"text": text or ""})
        except Exception as e:
            self._json({"text": "", "error": str(e)})

    def _json(self, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def run_gui_web() -> None:
    """Start the Harmoni web GUI."""
    global _bridge
    _bridge = HarmoniBridge()
    srv = HTTPServer((_HOST, _PORT), _Handler)
    url = f"http://{_HOST}:{_PORT}"
    print(f"Harmoni OS running at {url}")

    # Signal splash screen that we're ready
    try:
        from harmoni.ui.splash import signal_splash_done
        signal_splash_done()
    except Exception:
        pass

    threading.Thread(target=lambda: (time.sleep(0.8), webbrowser.open(url)), daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _bridge.close()
        srv.server_close()
