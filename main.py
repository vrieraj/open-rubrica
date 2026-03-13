#!/usr/bin/env python3
"""
main.py — Firma digital de PDFs con DNIe o .p12
Uso: python main.py [--p12 cert.p12] [--pkcs11-lib /ruta/lib.so] [--puerto 8765]
Abre automáticamente el navegador en http://localhost:8765
"""

import argparse
import io
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import utils

# ─────────────────────────────────────────────────────────────────────────────
# ESTADO GLOBAL DE LA SESIÓN
# ─────────────────────────────────────────────────────────────────────────────
estado = {
    'pdf_bytes':     None,   # bytes del PDF cargado
    'pdf_nombre':    None,   # nombre original del archivo
    'output_path':   None,   # ruta de salida (_firmado.pdf)
    'total_paginas': 0,
    'paginas_info':  [],     # [(w_pts, h_pts), ...]
    'coords':        {},     # {num_pagina: (x1,y1,x2,y2)}
    'resultado':     None,   # dict con el resultado de la firma
    'servidor':      None,
    'args':          None,
}


# ─────────────────────────────────────────────────────────────────────────────
# HTML
# ─────────────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Firma PDF — DNIe</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, sans-serif;
  background: #1a1a2e; color: #eee;
  display: flex; flex-direction: column; align-items: center;
  min-height: 100vh; padding: 20px; gap: 16px;
}
h1 { font-size: 1.3rem; color: #a8d8ea; }

/* ── Paneles genéricos ── */
.panel {
  display: none; flex-direction: column; align-items: center; gap: 14px;
  width: 100%; max-width: 520px;
  background: #16213e; border-radius: 10px; padding: 28px 32px;
}
.panel h2  { color: #a8d8ea; font-size: 1.1rem; }
.panel p   { color: #aaa; font-size: 0.85rem; text-align: center; }
.panel.borde-ok  { border: 2px solid #2ecc71; }
.panel.borde-err { border: 2px solid #e74c3c; }
.panel.borde-azul{ border: 2px solid #3498db; }

/* ── Carga de archivo ── */
#panel-carga { display: flex; }
#drop-zone {
  width: 100%; border: 2px dashed #3498db; border-radius: 10px;
  padding: 40px 20px; text-align: center; cursor: pointer;
  color: #a8d8ea; transition: background 0.2s;
}
#drop-zone:hover, #drop-zone.over { background: #0f3460; }
#drop-zone input { display: none; }
#drop-zone .icono { font-size: 3rem; margin-bottom: 10px; }
#drop-zone .sub   { font-size: 0.8rem; color: #aaa; margin-top: 6px; }

/* ── Visor de páginas ── */
#panel-visor { display: none; flex-direction: column; align-items: center; gap: 12px; width: 100%; max-width: 900px; }
#status-bar {
  width: 100%; background: #16213e; border-radius: 8px;
  padding: 10px 20px; display: flex; justify-content: space-between; align-items: center;
}
#pagina-info  { font-size: 1rem; color: #a8d8ea; font-weight: 600; }
#instruccion  { font-size: 0.85rem; color: #aaa; }
#canvas-wrap  {
  position: relative; cursor: crosshair;
  border: 2px solid #333; border-radius: 4px;
  background: #111; max-width: 100%;
}
#pdf-img      { display: block; max-width: 100%; }
#rect-overlay { position: absolute; top: 0; left: 0; pointer-events: none; width: 100%; height: 100%; }
#controles    { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; width: 100%; }
#resumen      {
  width: 100%; background: #16213e; border-radius: 8px;
  padding: 10px 20px; font-size: 0.85rem; color: #aaa; display: none;
}
#resumen span { color: #a8d8ea; }
#texto-preview {
  background: #0f3460; border-radius: 6px; padding: 10px 16px;
  font-size: 0.8rem; color: #a8d8ea; white-space: pre-wrap;
  width: 100%; text-align: center;
}

/* ── Botones ── */
button {
  padding: 10px 22px; border: none; border-radius: 6px;
  font-size: 0.95rem; cursor: pointer; font-weight: 600; transition: opacity 0.15s;
}
button:hover    { opacity: 0.85; }
button:disabled { opacity: 0.4; cursor: default; }
.btn-verde   { background: #2ecc71; color: #111; }
.btn-gris    { background: #555;    color: #eee; }
.btn-azul    { background: #3498db; color: #eee; }
.btn-morado  { background: #8e44ad; color: #eee; }
.btn-naranja { background: #e67e22; color: #eee; }
.btn-rojo    { background: #e74c3c; color: #eee; }

/* ── Panel rúbrica ── */
#rubrica-canvas {
  background: white; border-radius: 6px; cursor: crosshair;
  touch-action: none; width: 100%; max-width: 520px;
  border: 2px dashed #3498db;
}

/* ── Certificados ── */
#cert-list { width: 100%; display: flex; flex-direction: column; gap: 8px; }
.cert-item {
  display: flex; align-items: center; gap: 10px;
  background: #0f3460; border-radius: 6px; padding: 10px 14px;
  cursor: pointer; border: 2px solid transparent; transition: border-color 0.15s;
}
.cert-item:hover    { border-color: #3498db; }
.cert-item.selected { border-color: #2ecc71; }
.cert-item input    { accent-color: #2ecc71; }
.cert-label   { font-weight: 600; font-size: 0.9rem; }
.cert-subject { font-size: 0.75rem; color: #aaa; margin-top: 2px; }

/* ── PIN ── */
#pin-input {
  width: 100%; padding: 10px 14px;
  background: #0f3460; border: 1px solid #444; border-radius: 6px;
  color: #eee; font-size: 1.1rem; letter-spacing: 4px; text-align: center;
}

/* ── Resultado ── */
#panel-resultado { display: none; }

/* ── Animación ── */
.progreso { font-size: 0.9rem; color: #aaa; animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

/* ── Descarga ── */
#btn-descarga { display: none; }
</style>
</head>
<body>

<div style="width:100%;max-width:900px;display:flex;justify-content:space-between;align-items:center">
  <h1>📝 Firma digital de PDF</h1>
  <button class="btn-gris" onclick="cerrarServidor()" style="font-size:0.8rem;padding:6px 14px">✕ Cerrar</button>
</div>

<!-- ── PASO 1: Cargar PDF ── -->
<div id="panel-carga" class="panel borde-azul" style="max-width:600px">
  <h2>📂 Selecciona el PDF a firmar</h2>
  <div id="drop-zone" onclick="document.getElementById('file-input').click()"
       ondragover="ev(event,'over')" ondragleave="ev(event,'')" ondrop="soltar(event)">
    <input id="file-input" type="file" accept=".pdf" onchange="cargarArchivo(this.files[0])">
    <div class="icono">📄</div>
    <div>Haz clic o arrastra un PDF aquí</div>
    <div class="sub">El archivo nunca sale de tu equipo</div>
  </div>
</div>

<!-- ── PASO 2: Visor + posicionamiento ── -->
<div id="panel-visor">
  <div id="status-bar">
    <span id="pagina-info">—</span>
    <span id="instruccion">Haz clic y arrastra para dibujar el área de firma</span>
  </div>
  <div id="texto-preview"></div>
  <div id="canvas-wrap">
    <img id="pdf-img" src="" alt="página PDF" draggable="false">
    <svg id="rect-overlay" xmlns="http://www.w3.org/2000/svg"></svg>
  </div>
  <div id="controles">
    <button class="btn-azul"    onclick="paginaAnterior()">◀ Anterior</button>
    <button class="btn-morado"  onclick="limpiarRect()">✕ Limpiar</button>
    <button class="btn-gris"    onclick="omitirPagina()">Omitir página</button>
    <button class="btn-verde"   id="btn-confirmar" onclick="confirmarPagina()" disabled>✔ Confirmar y siguiente</button>
    <button class="btn-naranja" id="btn-todas"     onclick="confirmarTodas()"  disabled>⬛ Todas las páginas</button>
  </div>
  <div id="resumen"></div>
</div>

<!-- ── PASO 3: Rúbrica ── -->
<div id="panel-rubrica" class="panel borde-azul" style="max-width:600px">
  <h2>✍ Rúbrica <span style="font-size:0.8rem;color:#aaa">(opcional)</span></h2>
  <p>Dibuja tu firma. Se añadirá como imagen con fondo transparente.<br>El texto aparecerá debajo.</p>
  <canvas id="rubrica-canvas" width="520" height="160"></canvas>
  <div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center">
    <button class="btn-morado" onclick="limpiarRubrica()">✕ Limpiar</button>
    <button class="btn-gris"   onclick="sinRubrica()">Sin rúbrica</button>
    <button class="btn-verde"  onclick="confirmarRubrica()">✔ Usar esta rúbrica</button>
  </div>
</div>

<!-- ── PASO 4a: Verificando DNIe ── -->
<div id="panel-verificando" class="panel">
  <h2>🔍 Verificando DNIe…</h2>
  <div class="progreso">Conectando con el lector de tarjetas…</div>
</div>

<!-- ── PASO 4b: Error DNIe ── -->
<div id="panel-dnie-error" class="panel borde-err">
  <h2>❌ DNIe no detectado</h2>
  <p id="dnie-error-msg"></p>
  <button class="btn-rojo" onclick="verificarDnie()">🔄 Reintentar</button>
</div>

<!-- ── PASO 4c: Selección cert + PIN ── -->
<div id="panel-auth" class="panel borde-ok">
  <h2>🔐 Certificado y PIN</h2>
  <p>Para firmar documentos usa <strong>CertFirmaDigital</strong>.</p>
  <div id="cert-list"></div>
  <h2 style="margin-top:6px">🔑 PIN del DNIe</h2>
  <p>Conexión local — el PIN no sale del equipo.</p>
  <input id="pin-input" type="password" placeholder="••••" maxlength="16" autocomplete="off">
  <button class="btn-rojo" style="width:100%" onclick="iniciarFirma()">✍ Firmar PDF</button>
</div>

<!-- ── PASO 5: Resultado ── -->
<div id="panel-resultado" class="panel">
  <div id="resultado-icono" style="font-size:2.5rem"></div>
  <div id="resultado-msg"></div>
  <a id="btn-descarga" class="btn-verde" style="padding:10px 22px;border-radius:6px;font-weight:600;text-decoration:none"
     href="/descargar" download>⬇ Descargar PDF firmado</a>
</div>

<script>
// ────────────────────────────────────────────────────────────
// ESTADO
// ────────────────────────────────────────────────────────────
let totalPaginas=0, paginaActual=1;
let imgW=0, imgH=0;          // dimensiones de la imagen renderizada (px)
let pdfW=0, pdfH=0;          // dimensiones de la página PDF (pts)
let rectCanvas=null, rectsCanvas={}, rectsPDF={};
let dibujando=false, startX=0, startY=0;
let esDnie=false, certSeleccionada=null, rubricaDataUrl=null;
let rubricaDibujando=false, rubricaCtx=null;

// ────────────────────────────────────────────────────────────
// CARGA DE ARCHIVO
// ────────────────────────────────────────────────────────────
function ev(e,cls){ e.preventDefault(); document.getElementById('drop-zone').className=cls?'over':''; }
function soltar(e){ e.preventDefault(); document.getElementById('drop-zone').className=''; cargarArchivo(e.dataTransfer.files[0]); }

async function cargarArchivo(file){
  if(!file || !file.name.endsWith('.pdf')){ alert('Selecciona un archivo PDF.'); return; }
  const fd=new FormData(); fd.append('pdf', file);
  const r=await fetch('/cargar',{method:'POST',body:fd}).then(x=>x.json());
  if(!r.ok){ alert('Error al cargar: '+r.error); return; }
  totalPaginas=r.total_paginas;
  esDnie=r.es_dnie;
  document.getElementById('texto-preview').textContent='📝 '+r.texto_firma;
  mostrarVisor();
  cargarPagina(1);
  initRubrica();
}

// ────────────────────────────────────────────────────────────
// VISOR
// ────────────────────────────────────────────────────────────
function mostrarVisor(){
  document.getElementById('panel-carga').style.display='none';
  document.getElementById('panel-visor').style.display='flex';
}

async function cargarPagina(n){
  paginaActual=n;
  const img=document.getElementById('pdf-img');
  // Añadir timestamp para forzar recarga
  img.src='/pagina/'+n+'?t='+Date.now();
  img.onload=()=>{
    imgW=img.naturalWidth; imgH=img.naturalHeight;
    const svg=document.getElementById('rect-overlay');
    svg.setAttribute('viewBox',`0 0 ${imgW} ${imgH}`);
    svg.style.width=imgW+'px'; svg.style.height=imgH+'px';
    rectCanvas=rectsCanvas[n]||null;
    dibujarOverlay(); actualizarBotones();
  };
  // Obtener dimensiones PDF reales
  const info=await fetch('/pagina_info/'+n).then(x=>x.json());
  pdfW=info.w; pdfH=info.h;
  document.getElementById('pagina-info').textContent=`Página ${n} / ${totalPaginas}`;
}

// Convierte coordenadas de imagen (px pantalla) a coordenadas PDF (pts, origen abajo-izquierda)
function imgAPdf(r){
  // Usar dimensiones mostradas en pantalla (no las naturales), ya que el ratón
  // devuelve coordenadas relativas al elemento renderizado por CSS
  const imgEl=document.getElementById('pdf-img');
  const dispW=imgEl.getBoundingClientRect().width;
  const dispH=imgEl.getBoundingClientRect().height;
  const sx=pdfW/dispW, sy=pdfH/dispH;
  const x1=Math.min(r.x1,r.x2)*sx,  x2=Math.max(r.x1,r.x2)*sx;
  const iy1=Math.min(r.y1,r.y2),    iy2=Math.max(r.y1,r.y2);
  const y1=pdfH - iy2*sy,            y2=pdfH - iy1*sy;
  return {x1,y1,x2,y2};
}

// ── Dibujar con ratón ──
const wrap=document.getElementById('canvas-wrap');
wrap.addEventListener('mousedown', e=>{
  e.preventDefault();                      // evita arrastre nativo del navegador
  const r=wrap.getBoundingClientRect();
  startX=e.clientX-r.left; startY=e.clientY-r.top;
  dibujando=true;
});
wrap.addEventListener('mousemove', e=>{
  if(!dibujando) return;
  const r=wrap.getBoundingClientRect();
  rectCanvas={x1:startX,y1:startY,x2:e.clientX-r.left,y2:e.clientY-r.top};
  dibujarOverlay(); actualizarBotones();
});
wrap.addEventListener('mouseup', ()=>{ dibujando=false; });
wrap.addEventListener('mouseleave',()=>{ dibujando=false; });

function dibujarOverlay(){
  const svg=document.getElementById('rect-overlay'); svg.innerHTML='';
  if(!rectCanvas) return;
  const x1=Math.min(rectCanvas.x1,rectCanvas.x2), y1=Math.min(rectCanvas.y1,rectCanvas.y2);
  const x2=Math.max(rectCanvas.x1,rectCanvas.x2), y2=Math.max(rectCanvas.y1,rectCanvas.y2);
  const r=document.createElementNS('http://www.w3.org/2000/svg','rect');
  r.setAttribute('x',x1); r.setAttribute('y',y1);
  r.setAttribute('width',x2-x1); r.setAttribute('height',y2-y1);
  r.setAttribute('fill','rgba(231,76,60,0.18)');
  r.setAttribute('stroke','#e74c3c');
  r.setAttribute('stroke-width','2');
  r.setAttribute('stroke-dasharray','6,3');
  svg.appendChild(r);
  const t=document.createElementNS('http://www.w3.org/2000/svg','text');
  t.setAttribute('x',x1+4); t.setAttribute('y',y1+14);
  t.setAttribute('fill','#e74c3c'); t.setAttribute('font-size','11'); t.setAttribute('font-weight','bold');
  t.textContent='FIRMA'; svg.appendChild(t);
}

function actualizarBotones(){
  document.getElementById('btn-confirmar').disabled=!rectCanvas;
  document.getElementById('btn-todas').disabled=!rectCanvas;
  document.getElementById('btn-anterior').disabled=paginaActual<=1;
}

function limpiarRect(){ rectCanvas=null; dibujarOverlay(); actualizarBotones(); }

async function enviarCoord(pagina, coords){
  await fetch('/coordenadas',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({pagina, ...coords})});
}
async function omitirPagina(){
  await fetch('/coordenadas',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({pagina:paginaActual, omitir:true})});
  delete rectsCanvas[paginaActual]; delete rectsPDF[paginaActual];
  avanzar();
}
async function confirmarPagina(){
  if(!rectCanvas) return;
  const pdf=imgAPdf(rectCanvas);
  rectsCanvas[paginaActual]={...rectCanvas}; rectsPDF[paginaActual]=pdf;
  await enviarCoord(paginaActual, pdf);
  actualizarResumen(); avanzar();
}
async function confirmarTodas(){
  if(!rectCanvas) return;
  const pdf=imgAPdf(rectCanvas);
  for(let p=1;p<=totalPaginas;p++){
    rectsCanvas[p]={...rectCanvas}; rectsPDF[p]=pdf;
    await enviarCoord(p, pdf);
  }
  actualizarResumen(); mostrarRubrica();
}
function avanzar(){
  if(paginaActual<totalPaginas){ cargarPagina(paginaActual+1); }
  else mostrarRubrica();
}
function paginaAnterior(){ if(paginaActual>1) cargarPagina(paginaActual-1); }

function actualizarResumen(){
  const pags=Object.keys(rectsPDF).map(Number).sort((a,b)=>a-b);
  const div=document.getElementById('resumen');
  if(!pags.length){ div.style.display='none'; return; }
  div.style.display='block';
  div.innerHTML='✔ Páginas con firma: '+pags.map(p=>`<span>pág.${p}</span>`).join(', ');
}

// ────────────────────────────────────────────────────────────
// RÚBRICA
// ────────────────────────────────────────────────────────────
function initRubrica(){
  const c=document.getElementById('rubrica-canvas');
  rubricaCtx=c.getContext('2d');
  rubricaCtx.strokeStyle='#1a3a6b';
  rubricaCtx.lineWidth=2.5;
  rubricaCtx.lineCap='round';
  rubricaCtx.lineJoin='round';
  const xy=(e,c)=>{ const r=c.getBoundingClientRect(); return {x:(e.clientX-r.left)*(c.width/r.width),y:(e.clientY-r.top)*(c.height/r.height)}; };
  c.addEventListener('mousedown',e=>{ rubricaDibujando=true; const p=xy(e,c); rubricaCtx.beginPath(); rubricaCtx.moveTo(p.x,p.y); });
  c.addEventListener('mousemove',e=>{ if(!rubricaDibujando)return; const p=xy(e,c); rubricaCtx.lineTo(p.x,p.y); rubricaCtx.stroke(); });
  c.addEventListener('mouseup',  ()=>{ rubricaDibujando=false; });
  c.addEventListener('mouseleave',()=>{ rubricaDibujando=false; });
  c.addEventListener('touchstart',e=>{ e.preventDefault(); rubricaDibujando=true; const p=xy(e.touches[0],c); rubricaCtx.beginPath(); rubricaCtx.moveTo(p.x,p.y); },{passive:false});
  c.addEventListener('touchmove', e=>{ e.preventDefault(); if(!rubricaDibujando)return; const p=xy(e.touches[0],c); rubricaCtx.lineTo(p.x,p.y); rubricaCtx.stroke(); },{passive:false});
  c.addEventListener('touchend',  ()=>{ rubricaDibujando=false; });
}
function limpiarRubrica(){ rubricaCtx.clearRect(0,0,520,160); }
function mostrarRubrica(){
  document.getElementById('panel-visor').style.display='none';
  mostrarPanel('panel-rubrica');
}
function confirmarRubrica(){
  const c=document.getElementById('rubrica-canvas');
  const d=rubricaCtx.getImageData(0,0,c.width,c.height).data;
  if(!d.some(v=>v!==0)){ alert('Dibuja tu rúbrica o pulsa "Sin rúbrica".'); return; }
  // Recolorear trazos a azul marino, fondo a transparente
  const off=document.createElement('canvas'); off.width=c.width; off.height=c.height;
  const ox=off.getContext('2d'); ox.drawImage(c,0,0);
  const id=ox.getImageData(0,0,off.width,off.height), pd=id.data;
  for(let i=0;i<pd.length;i+=4){
    if(pd[i+3]>10 && (pd[i]+pd[i+1]+pd[i+2])/3 < 220){
      pd[i]=26; pd[i+1]=58; pd[i+2]=107; pd[i+3]=Math.min(255,pd[i+3]+80);
    } else { pd[i+3]=0; }
  }
  ox.putImageData(id,0,0);
  rubricaDataUrl=off.toDataURL('image/png');
  irAAuth();
}
function sinRubrica(){ rubricaDataUrl=null; irAAuth(); }

// ────────────────────────────────────────────────────────────
// AUTENTICACIÓN
// ────────────────────────────────────────────────────────────
function irAAuth(){
  if(!esDnie){ iniciarFirma(); return; }
  verificarDnie();
}
async function verificarDnie(){
  mostrarPanel('panel-verificando');
  try {
    const r=await fetch('/certs_dnie').then(x=>x.json());
    if(!r.ok) throw new Error(r.error);
    const lista=document.getElementById('cert-list'); lista.innerHTML='';
    r.certs.forEach((cert,i)=>{
      const div=document.createElement('div');
      div.className='cert-item'+(i===0?' selected':'');
      div.innerHTML=`<input type="radio" name="cert" ${i===0?'checked':''}>`+
        `<div><div class="cert-label">🔏 ${cert.label}</div>`+
        `<div class="cert-subject">${cert.subject}</div></div>`;
      div.addEventListener('click',()=>{
        document.querySelectorAll('.cert-item').forEach(el=>el.classList.remove('selected'));
        div.classList.add('selected');
        certSeleccionada={label:cert.label,key_label:cert.key_label,nombre:cert.nombre};
      });
      if(i===0) certSeleccionada={label:cert.label,key_label:cert.key_label,nombre:cert.nombre};
      lista.appendChild(div);
    });
    mostrarPanel('panel-auth');
    const pin=document.getElementById('pin-input');
    pin.focus();
    pin.onkeydown=e=>{ if(e.key==='Enter') iniciarFirma(); };
  } catch(e) {
    mostrarPanel('panel-dnie-error');
    document.getElementById('dnie-error-msg').textContent=e.message;
  }
}

// ────────────────────────────────────────────────────────────
// FIRMA
// ────────────────────────────────────────────────────────────
async function iniciarFirma(){
  const pin=document.getElementById('pin-input')?.value||'';
  mostrarPanel('panel-verificando');
  document.querySelector('#panel-verificando h2').textContent='✍ Firmando…';
  document.querySelector('#panel-verificando .progreso').textContent='Por favor espera, esto puede tardar unos segundos…';
  await fetch('/firmar',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      pin,
      cert_label:  certSeleccionada?.label    || null,
      key_label:   certSeleccionada?.key_label || null,
      nombre_cert: certSeleccionada?.nombre   || null,
      rubrica:     rubricaDataUrl,
    }),
  });
  const iv=setInterval(async()=>{
    const r=await fetch('/resultado').then(x=>x.json());
    if(r.estado!=='esperando'){ clearInterval(iv); mostrarResultado(r.ok, r.mensaje); }
  }, 800);
}

function mostrarResultado(ok, msg){
  mostrarPanel(null);
  const p=document.getElementById('panel-resultado');
  p.style.display='flex'; p.className='panel '+(ok?'borde-ok':'borde-err');
  document.getElementById('resultado-icono').textContent=ok?'✅':'❌';
  document.getElementById('resultado-msg').innerHTML=msg;
  if(ok) document.getElementById('btn-descarga').style.display='inline-block';
}

// ────────────────────────────────────────────────────────────
// UTILIDADES
// ────────────────────────────────────────────────────────────
async function cerrarServidor(){
  if(!confirm('¿Cerrar el servidor y salir?')) return;
  await fetch('/cerrar',{method:'POST'}).catch(()=>{});
  document.body.innerHTML='<p style="color:#aaa;text-align:center;margin-top:40px">Servidor cerrado. Puedes cerrar esta pestaña.</p>';
}

function mostrarPanel(id){
  ['panel-verificando','panel-dnie-error','panel-auth','panel-rubrica'].forEach(pid=>{
    document.getElementById(pid).style.display='none';
  });
  if(id) document.getElementById(id).style.display='flex';
}
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# SERVIDOR HTTP
# ─────────────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        p = self.path.split('?')[0]  # ignorar query string

        if p == '/':
            self._send(200, 'text/html; charset=utf-8', HTML.encode())

        elif p.startswith('/pagina/'):
            try:
                n   = int(p.split('/')[-1])
                png = utils.renderizar_pagina(estado['pdf_bytes'], n)
                self._send(200, 'image/png', png)
            except Exception as e:
                self._send(500, 'text/plain', str(e).encode())

        elif p.startswith('/pagina_info/'):
            try:
                n    = int(p.split('/')[-1])
                _, info = utils.info_paginas(estado['pdf_bytes'])
                w, h = info[n - 1]
                self._json({'w': w, 'h': h})
            except Exception as e:
                self._json({'error': str(e)})

        elif p == '/certs_dnie':
            try:
                certs = utils.listar_certificados(estado['args'].pkcs11_lib)
                self._json({'ok': True, 'certs': certs})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)})

        elif p == '/resultado':
            r = estado['resultado']
            self._json(r if r else {'estado': 'esperando'})

        elif p == '/descargar':
            path = estado.get('output_path')
            if path and os.path.exists(path):
                with open(path, 'rb') as f:
                    data = f.read()
                nombre = os.path.basename(path)
                self.send_response(200)
                self.send_header('Content-Type', 'application/pdf')
                self.send_header('Content-Disposition', f'attachment; filename="{nombre}"')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._send(404, 'text/plain', b'No hay archivo para descargar.')

        else:
            self._send(404, 'text/plain', b'Not found')

    def do_POST(self):
        p = self.path

        if p == '/cargar':
            # multipart/form-data — parseo manual sencillo
            try:
                ct      = self.headers.get('Content-Type', '')
                length  = int(self.headers.get('Content-Length', 0))
                raw     = self.rfile.read(length)
                boundary = ct.split('boundary=')[-1].encode()
                parts    = raw.split(b'--' + boundary)
                pdf_bytes = None
                nombre    = 'documento.pdf'
                for part in parts:
                    if b'filename=' in part and b'.pdf' in part:
                        # Extraer nombre
                        for line in part.split(b'\r\n'):
                            if b'filename=' in line:
                                nombre = line.split(b'filename=')[-1].strip(b'"').decode(errors='replace')
                        # Cuerpo tras doble CRLF
                        body_start = part.find(b'\r\n\r\n')
                        if body_start != -1:
                            pdf_bytes = part[body_start + 4:].rstrip(b'\r\n')

                if not pdf_bytes:
                    self._json({'ok': False, 'error': 'No se recibió ningún PDF.'})
                    return

                total, info = utils.info_paginas(pdf_bytes)
                args = estado['args']
                output_path = utils.nombre_salida(
                    os.path.join(os.getcwd(), nombre)
                )

                estado['pdf_bytes']     = pdf_bytes
                estado['pdf_nombre']    = nombre
                estado['output_path']   = output_path
                estado['total_paginas'] = total
                estado['paginas_info']  = info
                estado['coords']        = {}
                estado['resultado']     = None

                texto = utils.texto_firma_default(args.nombre or 'Firmante')
                estado['config_sello']  = {
                    'texto':     texto,
                    'font_size': args.font_size,
                }

                self._json({
                    'ok':           True,
                    'total_paginas': total,
                    'es_dnie':      args.dnie,
                    'texto_firma':  texto,
                    'output_path':  output_path,
                })

            except Exception as e:
                import traceback; traceback.print_exc()
                self._json({'ok': False, 'error': str(e)})

        elif p == '/coordenadas':
            body = self._body()
            pagina = int(body['pagina'])
            if body.get('omitir'):
                estado['coords'].pop(pagina, None)
            else:
                estado['coords'][pagina] = (body['x1'], body['y1'], body['x2'], body['y2'])
            self._json({'ok': True})

        elif p == '/firmar':
            body = self._body()
            threading.Thread(
                target=_ejecutar_firma,
                args=(
                    body.get('pin', ''),
                    body.get('cert_label'),
                    body.get('key_label'),
                    body.get('nombre_cert'),
                    body.get('rubrica'),
                ),
                daemon=True,
            ).start()
            self._json({'ok': True})

        elif p == '/cerrar':
            self._json({'ok': True})
            threading.Thread(target=estado['servidor'].shutdown, daemon=True).start()

        else:
            self._send(404, 'text/plain', b'Not found')

    # ── helpers ──
    def _body(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _send(self, code, ct, data):
        self.send_response(code)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self._send(200, 'application/json', data)

    def log_message(self, *_):
        pass  # silenciar logs del servidor


# ─────────────────────────────────────────────────────────────────────────────
# FIRMA (hilo aparte)
# ─────────────────────────────────────────────────────────────────────────────
def _ejecutar_firma(pin, cert_label, key_label, nombre_cert, rubrica_b64):
    args         = estado['args']
    config_sello = estado['config_sello']
    coords       = dict(estado['coords'])

    if not coords:
        estado['resultado'] = {
            'estado': 'listo', 'ok': False,
            'mensaje': 'No hay páginas con firma posicionada.',
        }
        return

    # Usar nombre del certificado si está disponible
    texto = config_sello['texto']
    if nombre_cert and 'Firmante' in texto:
        texto = texto.replace('Firmante', nombre_cert)

    try:
        utils.firmar_pdf(
            pdf_bytes   = estado['pdf_bytes'],
            output_path = estado['output_path'],
            coords      = coords,
            texto_firma = texto,
            font_size   = config_sello.get('font_size', 9),
            rubrica_b64 = rubrica_b64,
            dnie        = args.dnie,
            pkcs11_lib  = args.pkcs11_lib,
            slot        = args.slot,
            pin         = pin,
            cert_label  = cert_label or 'CertFirmaDigital',
            key_label   = key_label,
            p12_path    = args.p12,
            p12_pass    = args.password,
        )
        n = len(coords)
        estado['resultado'] = {
            'estado': 'listo', 'ok': True,
            'mensaje': f'Firmado en {n} página{"s" if n != 1 else ""}.<br>'
                       f'<small>{os.path.basename(estado["output_path"])}</small>',
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        estado['resultado'] = {
            'estado': 'listo', 'ok': False,
            'mensaje': f'Error al firmar:<br><code>{e}</code>',
        }


# ─────────────────────────────────────────────────────────────────────────────
# ARRANQUE
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='Firma PDFs con DNIe o .p12 — interfaz web local'
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument('--dnie', action='store_true', default=True,
                   help='Usar DNIe (por defecto)')
    g.add_argument('--p12',  metavar='ARCHIVO',
                   help='Certificado .p12/.pfx')
    parser.add_argument('--pkcs11-lib', default=utils.DEFAULT_PKCS11_LIB,
                        metavar='RUTA', help='Librería PKCS#11 del DNIe')
    parser.add_argument('--slot',     type=int, default=0,
                        help='Slot del lector (por defecto 0)')
    parser.add_argument('--password', metavar='PASS',
                        help='Contraseña del .p12 (si aplica)')
    parser.add_argument('--nombre',   metavar='NOMBRE',
                        help='Nombre del firmante (si no se lee del certificado)')
    parser.add_argument('--font-size', type=int, default=9,
                        dest='font_size', help='Tamaño de letra del sello (por defecto 9)')
    parser.add_argument('--puerto',   type=int, default=8765,
                        help='Puerto local (por defecto 8765)')
    args = parser.parse_args()

    # Si se pasa --p12, desactivar --dnie
    if args.p12:
        args.dnie = False

    # Verificar dependencias críticas
    try:
        import fitz  # noqa
    except ImportError:
        print('❌  Falta pymupdf. Instala con:\n   pip install pymupdf')
        sys.exit(1)
    try:
        from pyhanko.sign import signers  # noqa
    except ImportError:
        print('❌  Falta pyhanko. Instala con:\n   pip install pyhanko')
        sys.exit(1)

    estado['args'] = args

    servidor = HTTPServer(('localhost', args.puerto), Handler)
    estado['servidor'] = servidor

    url = f'http://localhost:{args.puerto}'
    print(f'\n🔏 Firma digital de PDFs')
    print(f'🌐 Interfaz en {url}')
    print(f'   Ctrl+C para salir\n')
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print('\nServidor detenido.')


if __name__ == '__main__':
    main()
