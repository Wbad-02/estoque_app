// ═══════════════════════════════════════════════════
// Utilidades
// ═══════════════════════════════════════════════════
const _escDiv = document.createElement('div');
function esc(str){
  if(str == null) return '';
  _escDiv.textContent = String(str);
  return _escDiv.innerHTML;
}

// ═══════════════════════════════════════════════════
// Searchable Select — componente reutilizável
// ═══════════════════════════════════════════════════
/**
 * tornarPesquisavel(selectId)
 * Transforma um <select> nativo em um componente com campo de busca.
 * Idempotente: se chamado duas vezes no mesmo select, não duplica.
 * Observa mudanças nas <option> via MutationObserver.
 */
function tornarPesquisavel(selectId) {
  const select = document.getElementById(selectId);
  if (!select) return;

  // Idempotência: se já foi transformado, apenas sincroniza o label
  if (select._searchableInit) {
    _syncSearchableLabel(select);
    return;
  }
  select._searchableInit = true;

  // Esconde o select original mas mantém no DOM (valor acessível)
  select.style.display = 'none';

  // Wrapper posicionado (para o dropdown absoluto funcionar)
  const wrapper = document.createElement('div');
  wrapper.className = 'ss-wrapper';
  wrapper.style.cssText = 'position:relative;display:block;';
  select.parentNode.insertBefore(wrapper, select);
  wrapper.appendChild(select);

  // Input visível
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'ss-input';
  input.autocomplete = 'off';
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-expanded', 'false');
  // Herda aria-label do select se houver
  if (select.getAttribute('aria-label')) {
    input.setAttribute('aria-label', select.getAttribute('aria-label'));
  }
  // Seta indicadora (▼) via padding-right — injetada via CSS abaixo
  input.style.cssText = 'padding-right:28px;cursor:pointer;';
  wrapper.insertBefore(input, select);

  // Dropdown
  const dropdown = document.createElement('div');
  dropdown.className = 'ss-dropdown';
  dropdown.style.cssText = [
    'position:absolute;top:calc(100% + 3px);left:0;right:0;',
    'background:var(--branco);border:1.5px solid var(--verde-escuro);',
    'border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.14);',
    'z-index:999;max-height:220px;overflow-y:auto;display:none;',
  ].join('');
  wrapper.appendChild(dropdown);

  // ── Helpers internos ────────────────────────────
  function getOptions() {
    return Array.from(select.options);
  }

  function labelDaOpcao(opt) {
    return opt ? opt.textContent.trim() : '';
  }

  function renderDropdown(filtro) {
    const termo = (filtro || '').toLowerCase();
    const opts = getOptions();
    const matches = opts.filter(o =>
      o.value !== '' && labelDaOpcao(o).toLowerCase().includes(termo)
    );
    if (!matches.length) {
      dropdown.innerHTML =
        '<div class="ss-item ss-empty" style="padding:10px 12px;font-size:13px;color:var(--muted)">Nenhum resultado</div>';
      return;
    }
    dropdown.innerHTML = matches.map(o => {
      const sel = o.value === select.value ? ' ss-selected' : '';
      return `<div class="ss-item${sel}" data-value="${_escAttr(o.value)}"
        style="padding:9px 12px;font-size:13.5px;cursor:pointer;"
        >${esc(labelDaOpcao(o))}</div>`;
    }).join('');

    // Eventos de clique nas opções
    dropdown.querySelectorAll('.ss-item:not(.ss-empty)').forEach(item => {
      item.addEventListener('mousedown', e => {
        e.preventDefault(); // evita blur do input
        selecionar(item.dataset.value);
      });
    });

    // Hover style
    dropdown.querySelectorAll('.ss-item:not(.ss-empty)').forEach(item => {
      item.addEventListener('mouseenter', () => {
        item.style.background = 'var(--verde-escuro)';
        item.style.color = 'var(--branco)';
      });
      item.addEventListener('mouseleave', () => {
        if (item.classList.contains('ss-selected')) {
          item.style.background = 'rgba(27,58,45,.08)';
          item.style.color = '';
        } else {
          item.style.background = '';
          item.style.color = '';
        }
      });
    });

    // Destaque no item selecionado
    dropdown.querySelectorAll('.ss-item.ss-selected').forEach(item => {
      item.style.background = 'rgba(27,58,45,.08)';
    });
  }

  function _escAttr(str) {
    return String(str || '').replace(/"/g, '&quot;');
  }

  function abrirDropdown() {
    input.value = '';
    input.placeholder = 'Buscar...';
    renderDropdown('');
    dropdown.style.display = 'block';
    input.setAttribute('aria-expanded', 'true');
  }

  function fecharDropdown() {
    dropdown.style.display = 'none';
    input.setAttribute('aria-expanded', 'false');
    // Restaura label da opção selecionada
    _syncSearchableLabel(select);
  }

  function selecionar(value) {
    select.value = value;
    // Dispara change no select original (mantém onchange do HTML funcionando)
    select.dispatchEvent(new Event('change', { bubbles: true }));
    fecharDropdown();
  }

  // ── Eventos ────────────────────────────────────
  // Abre ao clicar. blur fecha após 150ms (permite mousedown do dropdown primeiro).
  // Não usamos 'focus' para abrir pois dispara antes do 'click', causando
  // abrir+fechar imediato quando o campo ainda não estava focado.
  let _justMousedDown = false;
  input.addEventListener('mousedown', () => { _justMousedDown = true; });
  input.addEventListener('click', () => {
    if (_justMousedDown) {
      _justMousedDown = false;
      if (dropdown.style.display === 'block') {
        fecharDropdown();
      } else {
        abrirDropdown();
      }
    }
  });

  // Tab-focus abre o dropdown
  input.addEventListener('focus', () => {
    if (!_justMousedDown) abrirDropdown();
  });

  input.addEventListener('input', () => {
    renderDropdown(input.value);
    dropdown.style.display = 'block';
  });

  input.addEventListener('blur', () => {
    setTimeout(fecharDropdown, 150);
  });

  // Navegação por teclado
  function _focusarItem(items, idx) {
    items.forEach(it => {
      it.classList.remove('ss-focused');
      it.style.background = it.classList.contains('ss-selected') ? 'rgba(27,58,45,.08)' : '';
      it.style.color = '';
    });
    if (items[idx]) {
      items[idx].classList.add('ss-focused');
      items[idx].style.background = 'var(--verde-escuro)';
      items[idx].style.color = 'var(--branco)';
      items[idx].scrollIntoView({ block: 'nearest' });
    }
  }

  input.addEventListener('keydown', e => {
    const items = Array.from(dropdown.querySelectorAll('.ss-item:not(.ss-empty)'));
    const active = dropdown.querySelector('.ss-item.ss-focused');
    let idx = items.indexOf(active);

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (dropdown.style.display === 'none') { abrirDropdown(); return; }
      _focusarItem(items, (idx + 1) % items.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (dropdown.style.display === 'none') { abrirDropdown(); return; }
      _focusarItem(items, (idx - 1 + items.length) % items.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const focused = dropdown.querySelector('.ss-item.ss-focused');
      if (focused) selecionar(focused.dataset.value);
      else fecharDropdown();
    } else if (e.key === 'Escape') {
      fecharDropdown();
    }
  });

  // ── MutationObserver: detecta troca de options ──
  const observer = new MutationObserver(() => {
    if (dropdown.style.display === 'block') {
      renderDropdown(input.value);
    }
    _syncSearchableLabel(select);
  });
  observer.observe(select, { childList: true, subtree: false });

  // Inicializa label
  _syncSearchableLabel(select);
}

/**
 * Sincroniza o texto do input visível com a opção selecionada no select original.
 * Chamada após seleção e após MutationObserver.
 */
function _syncSearchableLabel(select) {
  const wrapper = select.parentNode;
  if (!wrapper || !wrapper.classList.contains('ss-wrapper')) return;
  const input = wrapper.querySelector('.ss-input');
  if (!input) return;
  const opt = select.options[select.selectedIndex];
  const label = opt ? opt.textContent.trim() : '';
  // Só mostra se não for o placeholder (value vazio)
  if (opt && opt.value !== '') {
    input.value = label;
    input.placeholder = '';
  } else {
    input.value = '';
    input.placeholder = label || 'Selecione...';
  }
}

// CSS do componente: injetado uma vez no <head>
(function _injectSearchableCSS() {
  if (document.getElementById('_ss-style')) return;
  const style = document.createElement('style');
  style.id = '_ss-style';
  style.textContent = `
    .ss-wrapper { position: relative; display: block; }
    .ss-input {
      width: 100%;
      padding: 9px 28px 9px 12px !important;
      border: 1.5px solid var(--border);
      border-radius: 8px;
      font-size: 14px;
      outline: none;
      transition: border-color .15s, box-shadow .15s;
      background: var(--surface) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%235A716B' stroke-width='1.8' fill='none' stroke-linecap='round'/%3E%3C/svg%3E") no-repeat right 10px center;
      background-size: 12px 8px;
      color: var(--text);
      cursor: pointer;
      box-sizing: border-box;
    }
    .ss-input:focus {
      border-color: var(--verde-escuro);
      box-shadow: 0 0 0 3px rgba(27,58,45,.1);
      cursor: text;
    }
    .ss-dropdown { font-family: system-ui, sans-serif; }
    .ss-item { transition: background .1s, color .1s; }
  `;
  document.head.appendChild(style);
})();

// ═══════════════════════════════════════════════════
// Estado
// ═══════════════════════════════════════════════════
const S = {
  token: localStorage.getItem('token') || '',
  grupo: localStorage.getItem('grupo') || '',
  nome:  localStorage.getItem('nome')  || '',
  email: localStorage.getItem('email') || '',
  materiais:[], categorias:[], grupos:[], usuarios:[], historico:[],
};

const $   = id => document.getElementById(id);
const fmt = d  => d ? new Date(d).toLocaleDateString('pt-BR') : '—';
const fmtDT = d => d ? new Date(d).toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'}) : '—';

function fecharModal(id){ $(id).style.display='none'; }
// Fecha o modal apenas quando o clique/toque ocorre diretamente no overlay
// (não em elementos filhos). Usa currentTarget para compatibilidade iOS/Android.
function fecharModalSe(e,id){
  if(e.target===e.currentTarget || e.target.id===id) fecharModal(id);
}
function toast(msg, tipo='success'){
  const el=$('toast'); el.textContent=msg; el.className=`show ${tipo}`;
  setTimeout(()=>{ el.className=''; },3200);
}

// ═══════════════════════════════════════════════════
// Utilitário: desabilita botão durante requisição
// ═══════════════════════════════════════════════════
function withBtn(btn, fn) {
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  btn.style.opacity = '.7';
  const sp = document.createElement('span');
  sp.className = 'btn-spinner';
  btn.prepend(sp);
  Promise.resolve(fn()).finally(() => {
    btn.disabled = false;
    btn.style.opacity = '';
    sp.remove();
  });
}

// ═══════════════════════════════════════════════════
// API
// ═══════════════════════════════════════════════════
async function api(method, path, body){
  const opts={method, headers:{'Content-Type':'application/json', Authorization:`Bearer ${S.token}`}};
  if(body) opts.body=JSON.stringify(body);
  const r=await fetch('/api'+path, opts);
  if(r.status===401){logout();return null;}
  if(!r.ok){const e=await r.json().catch(()=>({})); toast(e.detail||'Erro','error'); return null;}
  if(r.status===204) return true;
  return r.json();
}


// ═══════════════════════════════════════════════════
// Sidebar mobile (drawer)
// ═══════════════════════════════════════════════════
function toggleSidebar(){
  const sb  = document.querySelector('.sidebar');
  const ov  = $('sidebar-overlay');
  const isOpen = sb.classList.contains('open');
  sb.classList.toggle('open', !isOpen);
  ov.classList.toggle('open', !isOpen);
  document.body.style.overflow = isOpen ? '' : 'hidden';
}

function fecharSidebar(){
  const sb = document.querySelector('.sidebar');
  const ov = $('sidebar-overlay');
  sb.classList.remove('open');
  ov.classList.remove('open');
  document.body.style.overflow = '';
}

// Atualizar badge de alertas na topbar mobile
function _atualizarTopbarBadge(total){
  const badge = $('topbar-badge');
  if(!badge) return;
  badge.textContent = total;
  badge.style.display = total > 0 ? 'inline-block' : 'none';
}

// Fechar sidebar com ESC
document.addEventListener('keydown', e => { if(e.key === 'Escape') fecharSidebar(); });

// Detectar orientação e ajustar
window.addEventListener('resize', () => {
  if(window.innerWidth > 1024) fecharSidebar();
});

// ═══════════════════════════════════════════════════
// Auth
// ═══════════════════════════════════════════════════
async function fazerLogin(){
  const email=$('login-email').value.trim(), senha=$('login-senha').value;
  $('login-error').style.display='none';
  try{
    const r=await fetch('/api/auth/login',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({email,senha}),
    });
    if(!r.ok){const e=await r.json(); $('login-error').textContent=e.detail||'Inválido'; $('login-error').style.display='block'; return;}
    const d=await r.json();
    S.token=d.access_token; S.grupo=d.grupo; S.nome=d.nome; S.email=d.email||'';
    localStorage.setItem('token',S.token); localStorage.setItem('grupo',S.grupo); localStorage.setItem('nome',S.nome); localStorage.setItem('email',S.email);
    iniciarApp();
  }catch{ toast('Servidor inacessível','error'); }
}
function logout(){
  localStorage.clear(); S.token=S.grupo=S.nome=S.email='';
  $('app').style.display='none'; $('login-screen').style.display='flex';
  $('topbar').style.display='none';
}
$('login-senha').addEventListener('keydown', e=>{ if(e.key==='Enter') fazerLogin(); });

// ═══════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════
function iniciarApp(){
  $('login-screen').style.display='none'; $('app').style.display='block';
  $('topbar').style.display='';
  $('sidebar-user').textContent=S.nome;
  const grupoLabel={mestre:'Mestre',admin:'Admin',editor:'Editor',viewer:'Viewer'};
  $('sidebar-grupo').textContent=grupoLabel[S.grupo]||'';

  const isMestre=S.grupo==='mestre';
  const isAdmin =S.grupo==='admin'||isMestre;
  const isEditor=S.grupo==='editor'||isAdmin;

  document.querySelectorAll('.admin-only').forEach(el=>el.style.display=isAdmin?'':'none');
  document.querySelectorAll('.editor-only').forEach(el=>el.style.display=isEditor?'':'none');

  // Reset tab state to defaults
  _reqTabAtual = 'req';
  $('tab-panel-req') && ($('tab-panel-req').style.display='');
  $('tab-panel-sol') && ($('tab-panel-sol').style.display='none');
  $('tab-btn-req')   && ($('tab-btn-req').classList.add('active'));
  $('tab-btn-sol')   && ($('tab-btn-sol').classList.remove('active'));

  // Mestre: mostra as opções admin e mestre no select de usuários
  if(isMestre){
    const selGrupo=$('usr-grupo');
    if(selGrupo){
      // Mostrar admin
      const optAdmin=selGrupo.querySelector('[value="admin"]');
      if(optAdmin) optAdmin.style.display='';
      // Adicionar mestre se não existir
      if(!selGrupo.querySelector('[value="mestre"]')){
        const opt=document.createElement('option');
        opt.value='mestre'; opt.textContent='Mestre — acesso total';
        selGrupo.appendChild(opt);
      }
    }
  }

  // Navega direto para a página indicada no hash (ex: link de e-mail /#requerimentos)
  const hashPage = window.location.hash.replace('#', '').trim();
  const paginasValidas = ['dashboard','materiais','retiradas','categorias','ativos',
    'categ-ativos','usuarios','importacao','notificacoes','requerimentos','perfil','relatorios'];
  if(hashPage && paginasValidas.includes(hashPage)){
    navegar(hashPage);
  } else {
    carregarDashboard();
  }

  // Badge de requerimentos + solicitações: busca em background para exibir antes de navegar até a aba
  if(S.grupo !== 'viewer'){
    Promise.all([
      api('GET', '/requerimentos/'),
      api('GET', '/solicitacoes/'),
    ]).then(([req, sol]) => { _atualizarBadgeReq(req, sol); });
  }

  _startPolling();
}

// ═══════════════════════════════════════════════════
// Navegação
// ═══════════════════════════════════════════════════
function navegar(p){
  _paginaAtual = p;
  document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));
  document.querySelectorAll('.nav-item,.nav-sub-item').forEach(x=>x.classList.remove('active'));
  $('page-'+p).classList.add('active');
  const navEl = document.querySelector(`[data-page="${p}"]`);
  if(navEl) navEl.classList.add('active');

  // Manter o header do grupo Cadastros ativo quando subpage está ativa
  const subPages = ['categorias','categ-ativos'];
  const cadastrosHeader = $('nav-cadastros-header');
  if(cadastrosHeader){
    if(subPages.includes(p)){
      cadastrosHeader.classList.add('active');
      // Expandir o grupo automaticamente
      $('nav-cadastros-items')?.classList.add('open');
      $('nav-cadastros-chev').textContent='▼';
    } else {
      cadastrosHeader.classList.remove('active');
    }
  }

  fecharSidebar();
  ({dashboard:carregarDashboard, materiais:carregarMateriais,
    retiradas:carregarRetiradas, categorias:carregarCategorias,
    ativos:carregarAtivos, 'categ-ativos':carregarCategoriasAtivo,
    usuarios:carregarUsuarios, importacao:carregarImportacao,
    notificacoes:carregarNotificacoes,
    requerimentos:carregarRequerimentos,
    perfil:carregarPerfil,
    relatorios:carregarRelatorios})[p]?.();
}

function toggleNavGroup(grupo){
  const items = $(`nav-${grupo}-items`);
  const chev  = $(`nav-${grupo}-chev`);
  const isOpen = items.classList.contains('open');
  items.classList.toggle('open', !isOpen);
  chev.textContent = isOpen ? '▶' : '▼';
  $(`nav-${grupo}-header`).classList.toggle('open', !isOpen);
}

// ═══════════════════════════════════════════════════
// Dashboard
// ═══════════════════════════════════════════════════
async function carregarDashboard(){
  const mats=await api('GET','/materiais/'); if(!mats) return;
  const totalAlertas=mats.filter(m=>m.alerta_minimo).length;
  const cats=new Set(mats.map(m=>m.grupo.categoria.nome)).size;

  const totalValorEstoque = mats.reduce((acc,m)=>acc+(m.valor_total||0),0);
  const valorStr = totalValorEstoque>0 ? 'R$ '+totalValorEstoque.toFixed(2) : '—';

  $('dash-summary').innerHTML=`
    <div class="summary-card"><div class="val">${mats.length}</div><div class="lbl">Itens cadastrados</div></div>
    <div class="summary-card"><div class="val">${cats}</div><div class="lbl">Categorias</div></div>
    <div class="summary-card ${totalAlertas>0?'warn':''}">
      <div class="val">${totalAlertas}</div><div class="lbl">Itens em alerta</div></div>
    <div class="summary-card">
      <div class="val" style="font-size:22px">${valorStr}</div>
      <div class="lbl">Valor total em estoque</div></div>`;

  $('dash-alert-banner').innerHTML=totalAlertas>0
    ?`<div class="alert-banner">⚠ ${totalAlertas} item(s) abaixo do estoque mínimo do grupo</div>`:'';
  $('dash-alerta-tag').textContent=totalAlertas>0?`(${totalAlertas} em alerta ⚠)`:'';
  _atualizarTopbarBadge(totalAlertas);

  _dashMateriais = mats;
  _popularFiltrosDash(mats);
  _renderizarDashBody(mats);
}

// ═══════════════════════════════════════════════════
// Materiais
// ═══════════════════════════════════════════════════
async function carregarMateriais(){
  const [mats,cats,grps]=await Promise.all([
    api('GET','/materiais/?incluir_zerados=true'), api('GET','/categorias/'), api('GET','/grupos/'),
  ]);
  if(!mats) return;
  S.materiais=mats; S.categorias=cats||[]; S.grupos=grps||[];

  $('mat-cat-filtro').innerHTML='<option value="">Todas as categorias</option>'+
    S.categorias.map(c=>`<option value="${c.id}">${esc(c.nome)}</option>`).join('');

  renderizarMateriais(mats);
}

function mudarCatFiltro(){
  const catId=$('mat-cat-filtro').value;
  const grpsFilt=catId?S.grupos.filter(g=>g.categoria_id==catId):S.grupos;
  $('mat-grp-filtro').innerHTML='<option value="">Todos os grupos</option>'+
    grpsFilt.map(g=>`<option value="${g.id}">${esc(g.nome)}</option>`).join('');
  filtrarMateriais();
}

function filtrarMateriais(){
  const busca=$('mat-busca').value.toLowerCase();
  const catId=$('mat-cat-filtro').value, grpId=$('mat-grp-filtro').value;
  const alerta=$('mat-apenas-alerta').checked;
  renderizarMateriais(S.materiais.filter(m=>{
    if(busca&&!m.nome.toLowerCase().includes(busca)) return false;
    if(catId&&m.grupo.categoria_id!=catId) return false;
    if(grpId&&m.grupo_id!=grpId) return false;
    if(alerta&&!m.alerta_minimo) return false;
    return true;
  }));
}

function renderizarMateriais(lista){
  const canEdit=S.grupo==='admin'||S.grupo==='editor'||S.grupo==='mestre';
  const canAdmin=S.grupo==='admin'||S.grupo==='mestre';
  const container=$('mat-lista');
  if(!lista.length){container.innerHTML='<div class="empty"><span>📭</span>Nenhum material</div>';return;}

  const porGrupo={};
  lista.forEach(m=>{
    if(!porGrupo[m.grupo_id]) porGrupo[m.grupo_id]={grupo:m.grupo,itens:[]};
    porGrupo[m.grupo_id].itens.push(m);
  });

  let html='';
  Object.values(porGrupo).forEach(({grupo,itens})=>{
    const minTxt=grupo.quantidade_minima>0?`Mín. grupo: ${grupo.quantidade_minima}`:'Sem mínimo';
    const grpAlert=itens.some(m=>m.alerta_minimo);
    html+=`
      <div class="grupo-header ${grpAlert?'row-alert':''}">
        <span>
          <span style="opacity:.55;font-size:11px">${grupo.categoria.nome} /</span> ${esc(grupo.nome)}
          ${grpAlert?'<span class="badge badge-alert" style="margin-left:6px">⚠ Alerta</span>':''}
        </span>
        <span class="grupo-min-tag">${minTxt}</span>
      </div>
      <table>
        <thead><tr>
          <th>Nome</th><th>Qtd.</th><th>Cadastrado em</th><th>Última retirada</th>
          <th>Status</th>${canEdit?'<th>Ações</th>':''}
        </tr></thead><tbody>`;
    itens.forEach(m=>{
      const semEstoque = m.quantidade <= 0;
      const tagBadge=m.tag==='novo'?'<span class="badge badge-novo" style="margin-left:5px">Novo</span>'
        :m.tag==='usado'?'<span class="badge badge-usado" style="margin-left:5px">Usado</span>':'';
      html+=`<tr class="${m.alerta_minimo?'row-alert':''}" style="cursor:pointer;${semEstoque?'opacity:.55;':''}\" onclick="toggleMatDetail(${m.id},this)">
        <td>
          <span class="mat-expand-btn" title="Expandir">▶</span>
          <strong style="margin-left:4px">${esc(m.nome)}</strong>${tagBadge}
          ${semEstoque?'<span style="margin-left:6px;font-size:10px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.4px">Sem estoque</span>':''}
          ${m.descricao?`<br><small style="color:var(--muted);margin-left:18px">${esc(m.descricao)}</small>`:''}
        </td>
        <td style="${semEstoque?'color:var(--muted)':''}">${m.quantidade} ${m.unidade}</td>
        <td>${fmt(m.criado_em)}</td>
        <td>${m.ultima_retirada?fmtDT(m.ultima_retirada):'—'}</td>
        <td>${semEstoque
          ?'<span class="badge" style="background:#e0e0e0;color:#888">Atribuído</span>'
          :m.alerta_minimo
            ?'<span class="badge badge-alert">⚠ Alerta</span>'
            :'<span class="badge badge-ok">✓ OK</span>'}</td>
        <td style="white-space:nowrap" onclick="event.stopPropagation()">
          ${canEdit?`<button class="btn btn-secondary btn-sm" onclick="editarMaterial(${m.id})">Editar</button>`:''}
          ${canAdmin?`<button class="btn btn-danger btn-sm" onclick="removerMaterial(${m.id},'${m.nome.replace(/'/g,"\\'")}')">✕</button>`:''}
        </td>
      </tr>
      <tr class="mat-detail-row" id="mat-detail-${m.id}">
        <td class="mat-detail-cell" colspan="${canEdit?6:5}">
          ${!!m.usa_patrimonio
            ? `<div style="font-size:12px;color:var(--muted);margin-bottom:8px">Carregando unidades…</div>`
            : `<div class="mat-detail-grid">
            <div class="mat-detail-item">
              <span class="lbl">Valor unitário</span>
              <span class="val">${m.valor_unitario!=null?'R$ '+m.valor_unitario.toFixed(2):'—'}</span>
            </div>
            ${m.valor_total>0?`<div class="mat-detail-item">
              <span class="lbl">Valor total estimado</span>
              <span class="val">R$ ${m.valor_total.toFixed(2)}</span>
            </div>`:''}
            <div class="mat-detail-item">
              <span class="lbl">Tag</span>
              <span class="val">${m.tag==='novo'?'<span class="badge badge-novo">Novo</span>':m.tag==='usado'?'<span class="badge badge-usado">Usado</span>':'<span style="color:var(--muted)">—</span>'}</span>
            </div>
            <div class="mat-detail-item">
              <span class="lbl">Patrimônio individual</span>
              <span class="val">${m.usa_patrimonio?'Sim':'Não'}</span>
            </div>
          </div>`}
        </td>
      </tr>`;
    });
    html+='</tbody></table>';
  });
  container.innerHTML=html;
}

async function abrirModalMaterial(){
  if(!S.categorias.length) S.categorias=await api('GET','/categorias/')||[];
  $('mat-id').value=''; $('mat-nome').value=''; $('mat-desc').value='';
  $('mat-qtd').value=0; $('mat-un').value='un'; $('mat-valor').value='';
  $('modal-mat-title').textContent='Novo material';
  $('mat-qty-un-row').style.display='none';
  $('mat-cat-sel').innerHTML=S.categorias.map(c=>`<option value="${c.id}">${esc(c.nome)}</option>`).join('');
  await carregarGruposModal();
  $('modal-material').style.display='flex';
}

async function abrirModalMaterialNoGrupo(grupoId, catId){
  if(!S.categorias.length) S.categorias=await api('GET','/categorias/')||[];
  $('mat-id').value=''; $('mat-nome').value=''; $('mat-desc').value='';
  $('mat-qtd').value=0; $('mat-un').value='un'; $('mat-valor').value='';
  $('modal-mat-title').textContent='Novo material';
  $('mat-qty-un-row').style.display='none';
  $('mat-cat-sel').innerHTML=S.categorias.map(c=>
    `<option value="${c.id}" ${c.id===catId?'selected':''}>${esc(c.nome)}</option>`).join('');
  const grps=await api('GET',`/grupos/?categoria_id=${catId}`);
  $('mat-grp-sel').innerHTML=(grps||[]).map(g=>
    `<option value="${g.id}" ${g.id===grupoId?'selected':''}>${esc(g.nome)}</option>`).join('');
  $('modal-material').style.display='flex';
}

async function carregarGruposModal(){
  const catId=$('mat-cat-sel').value;
  const grps=await api('GET',catId?`/grupos/?categoria_id=${catId}`:'/grupos/');
  $('mat-grp-sel').innerHTML=!grps||!grps.length
    ?'<option value="">— Nenhum grupo —</option>'
    :grps.map(g=>`<option value="${g.id}">${esc(g.nome)}</option>`).join('');
}

async function editarMaterial(id){
  const m=S.materiais.find(x=>x.id===id); if(!m) return;
  if(!S.categorias.length) S.categorias=await api('GET','/categorias/')||[];
  $('mat-id').value=id; $('mat-nome').value=m.nome; $('mat-desc').value=m.descricao||'';
  $('mat-qtd').value=m.quantidade; $('mat-un').value=m.unidade;
  $('mat-valor').value=m.valor_unitario!=null?m.valor_unitario:'';
  $('modal-mat-title').textContent='Editar material';
  $('mat-qty-un-row').style.display='grid';
  $('mat-cat-sel').innerHTML=S.categorias.map(c=>
    `<option value="${c.id}" ${c.id===m.grupo.categoria_id?'selected':''}>${esc(c.nome)}</option>`).join('');
  const grps=await api('GET',`/grupos/?categoria_id=${m.grupo.categoria_id}`);
  $('mat-grp-sel').innerHTML=(grps||[]).map(g=>
    `<option value="${g.id}" ${g.id===m.grupo_id?'selected':''}>${esc(g.nome)}</option>`).join('');
  $('modal-material').style.display='flex';
}

async function salvarMaterial(){
  const id=$('mat-id').value;
  const valorRaw=$('mat-valor').value;
  const body={nome:$('mat-nome').value.trim(), descricao:$('mat-desc').value.trim()||null,
    grupo_id:parseInt($('mat-grp-sel').value),
    valor_unitario: valorRaw!==''?parseFloat(valorRaw):null};
  if(id){
    body.quantidade=parseFloat($('mat-qtd').value)||0;
    body.unidade=$('mat-un').value.trim()||'un';
  } else {
    body.tag='novo';
  }
  if(!body.nome){toast('Nome obrigatório','error');return;}
  if(!body.grupo_id){toast('Selecione um grupo','error');return;}
  const r=id?await api('PUT',`/materiais/${id}`,body):await api('POST','/materiais/',body);
  if(r){fecharModal('modal-material');toast('Material salvo!');carregarMateriais();}
}

async function removerMaterial(id,nome){
  if(!confirm(`Remover "${nome}"?`)) return;
  const r=await api('DELETE',`/materiais/${id}`);
  if(r!==null){toast('Material removido');carregarMateriais();}
}

// ═══════════════════════════════════════════════════
// Retiradas
// ═══════════════════════════════════════════════════
async function carregarRetiradas(){
  const [cats,grps,hist,motivosResp]=await Promise.all([
    api('GET','/categorias/'), api('GET','/grupos/'), api('GET','/retiradas/'),
    api('GET','/motivos/'),
  ]);
  S.categorias=cats||[]; S.grupos=grps||[]; S.historico=hist||[];

  $('ret-cat').innerHTML='<option value="">Selecione…</option>'+
    S.categorias.map(c=>`<option value="${c.id}">${esc(c.nome)}</option>`).join('');
  $('ret-grp').innerHTML='<option value="">Selecione…</option>';
  $('ret-mat').innerHTML='<option value="">Selecione…</option>';
  $('ret-estoque-info').style.display='none';

  _carregarOpcoesMotivo(motivosResp);
  renderizarHistorico(S.historico);
}

function _carregarOpcoesMotivo(dados){
  if(!dados) return;
  const sel=$('ret-motivo'); if(!sel) return;
  const padrao=(dados.padrao||[]).map(m=>`<option value="${esc(m.nome)}">${esc(m.label)}</option>`).join('');
  const custom=(dados.customizados||[]).map(m=>`<option value="${esc(m.nome)}">${esc(m.nome)}</option>`).join('');
  const opcs=padrao+(custom?`<optgroup label="Personalizados">${custom}</optgroup>`:'');
  sel.innerHTML=opcs;
  const filtro=$('hist-motivo-filtro');
  if(filtro) filtro.innerHTML='<option value="">Todos os motivos</option>'+opcs;
}

async function carregarGruposRet(){
  const catId=$('ret-cat').value;
  $('ret-grp').innerHTML='<option value="">Selecione…</option>';
  $('ret-mat').innerHTML='<option value="">Selecione…</option>';
  $('ret-unidade').innerHTML='<option value="">Selecione o material primeiro…</option>';
  $('ret-estoque-info').style.display='none';
  if(!catId) return;
  const grps=await api('GET',`/grupos/?categoria_id=${catId}`);
  $('ret-grp').innerHTML='<option value="">Selecione…</option>'+
    (grps||[]).map(g=>`<option value="${g.id}">${esc(g.nome)}</option>`).join('');
}

async function carregarMateriaisRet(){
  const grpId=$('ret-grp').value;
  $('ret-mat').innerHTML='<option value="">Selecione…</option>';
  $('ret-unidade').innerHTML='<option value="">Selecione o material primeiro…</option>';
  $('ret-estoque-info').style.display='none';
  if(!grpId) return;
  const mats=await api('GET',`/materiais/?grupo_id=${grpId}`);
  $('ret-mat').innerHTML='<option value="">Selecione…</option>'+
    (mats||[]).map(m=>`<option value="${m.id}" data-un="${m.unidade}">${esc(m.nome)}</option>`).join('');
}

async function mostrarEstoqueAtual(){
  const sel=$('ret-mat');
  const opt=sel.options[sel.selectedIndex];
  const info=$('ret-estoque-info');
  const uSel=$('ret-unidade');
  if(!opt||!opt.value){
    info.style.display='none';
    uSel.innerHTML='<option value="">Selecione o material primeiro…</option>';
    return;
  }
  const matId=parseInt(opt.value);
  const unidades=await api('GET',`/patrimonio/${matId}/unidades`)||[];
  const disponiveis=unidades.filter(u=>u.status==='ativo'&&u.tag!=='atribuido');
  info.textContent=`Disponível: ${disponiveis.length} ${opt.dataset.un}`;
  info.style.display='block';
  if(!disponiveis.length){
    uSel.innerHTML='<option value="">Sem unidades disponíveis</option>';
    return;
  }
  uSel.innerHTML='<option value="">Selecione…</option>'+
    disponiveis.map(u=>`<option value="${u.id}">${u.codigo||'Unidade #'+u.id} (${u.tag||'novo'})</option>`).join('');
}

async function registrarRetirada(){
  const matId=parseInt($('ret-mat').value);
  const unidadeId=parseInt($('ret-unidade').value);
  const motivo=$('ret-motivo').value;
  const obs=$('ret-obs').value.trim();
  if(!matId){toast('Selecione um material','error');return;}
  if(!unidadeId){toast('Selecione uma unidade','error');return;}

  const r=await api('POST',`/patrimonio/${matId}/retirar-unidade`,{
    unidade_id:unidadeId, motivo, observacao:obs||null,
  });
  if(r){
    toast('Retirada registrada!');
    $('ret-obs').value='';
    await mostrarEstoqueAtual();
    const hist=await api('GET','/retiradas/');
    S.historico=hist||[];
    renderizarHistorico(S.historico);
  }
}

function filtrarHistorico(){
  const motivo=$('hist-motivo-filtro').value;
  renderizarHistorico(motivo?S.historico.filter(h=>h.motivo===motivo):S.historico);
}

function renderizarHistorico(lista){
  const tbody=$('hist-body');
  if(!lista.length){
    tbody.innerHTML='<tr><td colspan="7"><div class="empty"><span>📋</span>Nenhuma retirada registrada</div></td></tr>';
    return;
  }
  const labelMotivo={colaborador:'Colaborador',defeito:'Defeito'};
  const badgeMotivo={colaborador:'badge-colab',defeito:'badge-defeito'};
  tbody.innerHTML=lista.map(h=>`
    <tr>
      <td>${fmtDT(h.criado_em)}</td>
      <td><strong>${esc(h.nome_material)}</strong></td>
      <td class="hide-mobile"><span style="color:var(--muted);font-size:12px">${esc(h.categoria_nome)} / </span>${esc(h.grupo_nome)}</td>
      <td>${h.quantidade}</td>
      <td><span class="badge ${badgeMotivo[h.motivo]||''}">${labelMotivo[h.motivo]||h.motivo}</span></td>
      <td class="hide-mobile">${h.observacao||'—'}</td>
      <td class="hide-mobile" style="font-size:12px;color:var(--muted)">${esc(h.nome_usuario)}</td>
    </tr>`).join('');
}

// ═══════════════════════════════════════════════════
// Categorias + Grupos (expansível)
// ═══════════════════════════════════════════════════
async function carregarCategorias(){
  const [cats,grps]=await Promise.all([api('GET','/categorias/'),api('GET','/grupos/')]);
  if(!cats) return;
  S.categorias=cats; S.grupos=grps||[];
  renderizarCategorias();
}

function renderizarCategorias(){
  const canEdit=S.grupo==='admin'||S.grupo==='editor';
  const container=$('cat-lista');
  if(!S.categorias.length){
    container.innerHTML='<div class="empty"><span>📂</span>Nenhuma categoria cadastrada</div>';
    return;
  }

  let html='';
  S.categorias.forEach(c=>{
    const grpsDaCat=S.grupos.filter(g=>g.categoria_id===c.id);
    html+=`
    <div class="cat-row" onclick="toggleCategoria(${c.id})">
      <span>
        <span class="cat-chevron" id="chev-${c.id}">▶</span>
        <span class="cat-nome" style="margin-left:8px">${esc(c.nome)}</span>
        ${c.descricao?`<span style="color:var(--muted);font-size:12px;margin-left:8px">— ${esc(c.descricao)}</span>`:''}
        <span style="color:var(--muted);font-size:11px;margin-left:8px">(${grpsDaCat.length} grupo(s))</span>
      </span>
      ${canEdit?`<span onclick="event.stopPropagation()" style="display:flex;gap:6px">
        <button class="btn btn-secondary btn-sm" onclick="editarCategoria(${c.id})">Editar</button>
        <button class="btn btn-danger btn-sm" onclick="removerCategoria(${c.id},'${c.nome.replace(/'/g,"\\'")}')">Remover</button>
      </span>`:''}
    </div>
    <div class="cat-grupos" id="grupos-${c.id}">`;

    // Inserir placeholder do formulário no TOPO (antes dos grupos)
    html+=`<!--FORM_GRUPO_${c.id}-->`;
    grpsDaCat.forEach(g=>{
      html+=`
      <div class="grupo-row">
        <span>
          <strong>${esc(g.nome)}</strong>
          ${g.descricao?`<span style="color:var(--muted);font-size:12px"> — ${esc(g.descricao)}</span>`:''}
          <span style="color:var(--muted);font-size:11px;margin-left:6px">
            Mín: ${g.quantidade_minima>0?g.quantidade_minima:'—'}
          </span>
        </span>
        ${canEdit?`<span style="display:flex;gap:6px">
          <button class="btn btn-primary btn-sm" onclick="abrirModalMaterialNoGrupo(${g.id},${c.id})">+ Material</button>
          <button class="btn btn-secondary btn-sm" onclick="editarGrupo(${g.id})">Editar</button>
          <button class="btn btn-danger btn-sm" onclick="removerGrupo(${g.id},'${g.nome.replace(/'/g,"\\'")}')">Remover</button>
        </span>`:''}
      </div>`;
    });

    if(canEdit){
      // Formulário de novo grupo fica NO TOPO, antes dos grupos listados
      html=html.replace(
        `<!--FORM_GRUPO_${c.id}-->`,
        `<div style="padding:8px 14px;border-bottom:1px solid var(--border);background:#F8FAF9">
          <button class="btn btn-secondary btn-sm" onclick="toggleFormGrupo(${c.id})">+ Adicionar grupo</button>
        </div>
        <div class="novo-grupo-form" id="form-grp-${c.id}">
          <input type="text" id="novo-grp-nome-${c.id}" placeholder="Nome do grupo" style="flex:2"/>
          <input type="number" id="novo-grp-min-${c.id}" placeholder="Mínimo (0=sem alerta)" min="0" step="0.01" value="0" style="flex:1"/>
          <button class="btn btn-primary btn-sm" onclick="withBtn(this,()=>criarGrupoInline(${c.id}))">Criar</button>
        </div>`
      );
    }

    html+=`</div>`;
  });
  container.innerHTML=html;
}

function toggleCategoria(catId){
  const grupos=$(`grupos-${catId}`);
  const chev=$(`chev-${catId}`);
  const catRow=grupos.previousElementSibling;
  const isOpen=grupos.classList.contains('open');
  grupos.classList.toggle('open',!isOpen);
  catRow.classList.toggle('open',!isOpen);
  chev.textContent=isOpen?'▶':'▼';
}

function toggleFormGrupo(catId){
  $(`form-grp-${catId}`).classList.toggle('open');
}

async function criarGrupoInline(catId){
  const nome=$(`novo-grp-nome-${catId}`).value.trim();
  const min=parseFloat($(`novo-grp-min-${catId}`).value)||0;
  if(!nome){toast('Nome do grupo obrigatório','error');return;}
  const r=await api('POST','/grupos/',{nome, quantidade_minima:min, categoria_id:catId});
  if(r){toast('Grupo criado!'); await carregarCategorias(); toggleCategoria(catId);}
}

function abrirModalCategoria(){
  $('cat-id').value=''; $('cat-nome').value=''; $('cat-desc').value='';
  $('modal-cat-title').textContent='Nova categoria';
  $('modal-categoria').style.display='flex';
}

function editarCategoria(id){
  const c=S.categorias.find(x=>x.id===id); if(!c) return;
  $('cat-id').value=id; $('cat-nome').value=c.nome; $('cat-desc').value=c.descricao||'';
  $('modal-cat-title').textContent='Editar categoria';
  $('modal-categoria').style.display='flex';
}

async function salvarCategoria(){
  const id=$('cat-id').value;
  const body={nome:$('cat-nome').value.trim(), descricao:$('cat-desc').value.trim()||null};
  if(!body.nome){toast('Nome obrigatório','error');return;}
  const r=id?await api('PUT',`/categorias/${id}`,body):await api('POST','/categorias/',body);
  if(r){fecharModal('modal-categoria');toast('Categoria salva!');carregarCategorias();}
}

async function removerCategoria(id,nome){
  if(!confirm(`Remover "${nome}"? Os grupos dentro dela também serão removidos.`)) return;
  const r=await api('DELETE',`/categorias/${id}`);
  if(r!==null){toast('Categoria removida');carregarCategorias();}
}

function editarGrupo(id){
  const g=S.grupos.find(x=>x.id===id); if(!g) return;
  $('grp-edit-id').value=id; $('grp-edit-nome').value=g.nome;
  $('grp-edit-desc').value=g.descricao||''; $('grp-edit-min').value=g.quantidade_minima;
  $('modal-grupo').style.display='flex';
}

async function salvarGrupoEdit(){
  const id=$('grp-edit-id').value;
  const body={nome:$('grp-edit-nome').value.trim(),
    descricao:$('grp-edit-desc').value.trim()||null,
    quantidade_minima:parseFloat($('grp-edit-min').value)||0};
  if(!body.nome){toast('Nome obrigatório','error');return;}
  const r=await api('PUT',`/grupos/${id}`,body);
  if(r){fecharModal('modal-grupo');toast('Grupo atualizado!');carregarCategorias();}
}

async function removerGrupo(id,nome){
  if(!confirm(`Remover grupo "${nome}"?`)) return;
  const r=await api('DELETE',`/grupos/${id}`);
  if(r!==null){toast('Grupo removido');carregarCategorias();}
}

// ═══════════════════════════════════════════════════
// Usuários
// ═══════════════════════════════════════════════════
async function carregarUsuarios(){
  const usrs=await api('GET','/usuarios/'); if(!usrs) return;
  S.usuarios=usrs;
  $('usr-body').innerHTML=usrs.map(u=>`
    <tr>
      <td><strong>${esc(u.nome)}</strong></td>
      <td class="hide-mobile" style="font-size:12px;color:var(--muted)">${u.email}</td>
      <td><span class="badge badge-${u.grupo}">${u.grupo}</span></td>
      <td class="hide-mobile">${u.ativo?'<span class="badge badge-ok">Ativo</span>':'<span class="badge" style="background:#eee;color:#999">Inativo</span>'}</td>
      <td>
        <button class="btn btn-secondary btn-sm" onclick="editarUsuario(${u.id})">Editar</button>
        <button class="btn btn-gold btn-sm" onclick="abrirModalSenhaAdmin(${u.id},'${u.nome.replace(/'/g,"\\'")}')">Senha</button>
        ${u.ativo?`<button class="btn btn-danger btn-sm" onclick="desativarUsuario(${u.id},'${u.nome.replace(/'/g,"\\'")}')">Desativar</button>`:''}
      </td>
    </tr>`).join('');
}

function limparFormUsuario(){
  $('usr-id').value=''; $('usr-nome').value=''; $('usr-email').value='';
  $('usr-senha').value=''; $('usr-grupo').value='viewer';
  $('usr-email').disabled=false; $('usr-senha-wrap').style.display='block';
  $('usr-form-title').textContent='Novo usuário'; $('usr-cancelar').style.display='none';
}

function editarUsuario(id){
  const u=S.usuarios.find(x=>x.id===id); if(!u) return;
  $('usr-id').value=id; $('usr-nome').value=u.nome; $('usr-email').value=u.email;
  $('usr-email').disabled=true; $('usr-senha-wrap').style.display='none';
  $('usr-grupo').value=u.grupo; $('usr-form-title').textContent='Editar usuário';
  $('usr-cancelar').style.display=''; window.scrollTo(0,0);
}

async function salvarUsuario(){
  const id=$('usr-id').value;
  if(id){
    const body={nome:$('usr-nome').value.trim(),grupo:$('usr-grupo').value};
    const r=await api('PUT',`/usuarios/${id}`,body);
    if(r){toast('Usuário atualizado!');limparFormUsuario();carregarUsuarios();}
  } else {
    const body={nome:$('usr-nome').value.trim(),email:$('usr-email').value.trim(),
      senha:$('usr-senha').value,grupo:$('usr-grupo').value};
    if(!body.nome||!body.email||!body.senha){toast('Preencha todos os campos','error');return;}
    const r=await api('POST','/usuarios/',body);
    if(r){toast('Usuário criado!');limparFormUsuario();carregarUsuarios();}
  }
}

async function desativarUsuario(id,nome){
  if(!confirm(`Desativar "${nome}"?`)) return;
  const r=await api('DELETE',`/usuarios/${id}`);
  if(r!==null){toast('Usuário desativado');carregarUsuarios();}
}

// ═══════════════════════════════════════════════════
// Importação NF-e
// ═══════════════════════════════════════════════════
let _nfeArquivo=null;

async function carregarImportacao(){
  const [cats,grps]=await Promise.all([api('GET','/categorias/'),api('GET','/grupos/')]);
  S.categorias=cats||[]; S.grupos=grps||[];
  _nfeArquivo=null; $('nfe-arquivo').value='';
  $('nfe-emitente').style.display='none';
  $('nfe-aviso-duplicata').style.display='none';
  $('nfe-btn-confirmar').style.display='none';
  $('nfe-resultado').style.display='none';
  $('nfe-preview-body').innerHTML='<tr><td colspan="7"><div class="empty"><span>📄</span>Carregue um XML</div></td></tr>';
  $('nfe-count').textContent='';
  if(S.grupo==='admin'||S.grupo==='mestre') _carregarHistoricoNfe();
}

async function _carregarHistoricoNfe(){
  const dados=await api('GET','/importacao/historico');
  const tbody=$('nfe-historico-body');
  if(!tbody) return;
  if(!dados||!dados.length){
    tbody.innerHTML='<tr><td colspan="4"><div class="empty"><span>📋</span>Nenhuma NF-e importada</div></td></tr>';
    return;
  }
  tbody.innerHTML=dados.map(r=>`
    <tr>
      <td><strong>${esc(r.nf_numero||'—')}</strong></td>
      <td style="font-size:12px">${esc(r.emitente||'—')}</td>
      <td style="font-size:12px;color:var(--muted)">${r.importado_em}</td>
      <td><button class="btn btn-danger btn-sm" onclick="withBtn(this,()=>liberarReimportacao('${r.chave}'))">Liberar reimportação</button></td>
    </tr>`).join('');
}

async function liberarReimportacao(chave){
  if(!confirm('Remover registro? A nota poderá ser reimportada.')) return;
  const r=await api('DELETE',`/importacao/${chave}`);
  if(r!==null) { toast('Registro removido. Agora você pode reimportar a nota.'); _carregarHistoricoNfe(); }
}


// ── Grupo pesquisável por linha ──────────────────────
function _nfeGrpHtml(idx){
  return `<div class="nfe-grp-wrap" data-idx="${idx}" style="position:relative">
    <input type="text" class="nfe-grp-input" data-idx="${idx}"
           placeholder="Buscar grupo…" autocomplete="off"
           oninput="_nfeGrpInput(this)" onfocus="_nfeGrpInput(this)"
           onblur="_nfeGrpBlur(this)"
           style="width:100%;font-size:12px;box-sizing:border-box"/>
    <input type="hidden" class="nfe-grp-id" data-idx="${idx}" value=""/>
    <div class="nfe-grp-drop" data-idx="${idx}"
         style="display:none;position:absolute;top:100%;left:0;right:0;z-index:100;
                background:#fff;border:1px solid #ccc;border-radius:4px;
                max-height:200px;overflow-y:auto;box-shadow:0 4px 12px rgba(0,0,0,0.15)">
    </div>
  </div>`;
}

function _nfeGrpInput(el){
  const idx=el.dataset.idx;
  const q=(el.value||'').toLowerCase().trim();
  const drop=document.querySelector(`.nfe-grp-drop[data-idx="${idx}"]`);
  if(!drop) return;

  let html='';
  S.categorias.forEach(cat=>{
    const grpsCat=S.grupos.filter(g=>g.categoria_id==cat.id &&
      (!q || g.nome.toLowerCase().includes(q)));
    if(!grpsCat.length) return;
    html+=`<div style="padding:4px 10px;font-size:10px;color:#888;text-transform:uppercase;
                        background:#f5f5f5;letter-spacing:.5px">${esc(cat.nome)}</div>`;
    grpsCat.forEach(g=>{
      html+=`<div class="nfe-grp-opt"
                  onmousedown="_nfeGrpSelecionar(${idx},${g.id},'${esc(g.nome).replace(/'/g,"\\'")}')  "
                  style="padding:6px 12px;font-size:12px;cursor:pointer"
                  onmouseover="this.style.background='var(--green)';this.style.color='#fff'"
                  onmouseout="this.style.background='';this.style.color=''">${esc(g.nome)}</div>`;
    });
  });

  if(!html) html='<div style="padding:8px 12px;font-size:12px;color:#888">Nenhum resultado</div>';
  drop.innerHTML=html;
  drop.style.display='block';
}

function _nfeGrpBlur(el){
  setTimeout(()=>{
    const idx=el.dataset.idx;
    const idEl=document.querySelector(`.nfe-grp-id[data-idx="${idx}"]`);
    const drop=document.querySelector(`.nfe-grp-drop[data-idx="${idx}"]`);
    if(drop) drop.style.display='none';
    // Se não há grupo selecionado, limpa o texto digitado
    if(idEl && !idEl.value) el.value='';
  },150);
}

function _nfeGrpSelecionar(idx, grupoId, grupoNome){
  const inputEl=document.querySelector(`.nfe-grp-input[data-idx="${idx}"]`);
  const idEl=document.querySelector(`.nfe-grp-id[data-idx="${idx}"]`);
  const drop=document.querySelector(`.nfe-grp-drop[data-idx="${idx}"]`);
  if(inputEl) inputEl.value=grupoNome;
  if(idEl) idEl.value=grupoId;
  if(drop) drop.style.display='none';
}

async function previewNFe(){
  const input=$('nfe-arquivo');
  if(!input.files.length) return;
  _nfeArquivo=input.files[0];
  $('nfe-resultado').style.display='none';
  $('nfe-aviso-duplicata').style.display='none';
  const form=new FormData(); form.append('arquivo',_nfeArquivo);
  $('nfe-preview-body').innerHTML='<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--muted)">Analisando…</td></tr>';
  try{
    const r=await fetch('/api/importacao/preview',{method:'POST',headers:{Authorization:`Bearer ${S.token}`},body:form});
    if(!r.ok){const e=await r.json().catch(()=>({}));toast(e.detail||'Erro ao analisar XML','error');return;}
    const dados=await r.json();
    $('nfe-emit-nome').textContent=dados.emitente.nome;
    $('nfe-numero').textContent=dados.nf_numero+' — '+(dados.nf_data||'');
    $('nfe-emitente').style.display='block';
    $('nfe-count').textContent=`${dados.itens.length} item(s)`;
    if(dados.ja_importada){
      const av=$('nfe-aviso-duplicata');
      av.textContent=`Esta NF-e já foi importada (${(dados.importado_em||'').substring(0,10)}). Confirme só se liberou a reimportação.`;
      av.style.display='block';
    }
    $('nfe-preview-body').innerHTML=dados.itens.map((it,idx)=>`
      <tr>
        <td style="font-size:12px;color:var(--muted)">${it.codigo}</td>
        <td><strong>${esc(it.nome)}</strong></td>
        <td>${it.quantidade}</td><td>${it.unidade}</td>
        <td>R$ ${it.valor_unit.toFixed(2)}</td>
        <td style="text-align:center"><input type="checkbox" class="nfe-patrimonio-cb" data-idx="${idx}" checked title="Marcar como patrimônio individual"/></td>
        <td style="min-width:180px">${_nfeGrpHtml(idx)}</td>
      </tr>`).join('');
    $('nfe-btn-confirmar').style.display='block';
  }catch{toast('Falha ao enviar arquivo','error');}
}

async function confirmarNFe(){
  if(!_nfeArquivo){toast('Selecione um XML','error');return;}
  const sels=[...document.querySelectorAll('.nfe-grp-id')];
  if(!sels.length){toast('Carregue um XML primeiro','error');return;}
  if(sels.some(s=>!s.value)){toast('Selecione o grupo para todos os itens','error');return;}
  const grupoIds=sels.map(s=>s.value).join(',');
  const patrimonioIndices=[...document.querySelectorAll('.nfe-patrimonio-cb:checked')]
    .map(cb=>cb.dataset.idx).join(',');
  const form=new FormData(); form.append('arquivo',_nfeArquivo);
  form.append('patrimonio_indices', patrimonioIndices);
  form.append('grupo_ids', grupoIds);
  try{
    const r=await fetch('/api/importacao/confirmar',
      {method:'POST',headers:{Authorization:`Bearer ${S.token}`},body:form});
    if(!r.ok){const e=await r.json().catch(()=>({}));toast(e.detail||'Erro na importação','error');return;}
    const res=await r.json();
    $('nfe-btn-confirmar').style.display='none';
    $('nfe-resultado').style.display='block';
    $('nfe-resultado-detalhe').innerHTML=`
      <p><strong>Emitente:</strong> ${esc(res.emitente)}</p>
      <p style="margin-top:6px"><strong>NF-e nº:</strong> ${esc(res.nf_numero)}</p>
      <p style="margin-top:12px;color:var(--green)">
        <strong>${res.criados.length}</strong> criado(s) &nbsp;·&nbsp;
        <strong>${res.atualizados.length}</strong> atualizado(s)
      </p>
      ${res.criados.length?`<ul style="margin-top:8px;padding-left:20px;font-size:12px;color:var(--muted)">${res.criados.map(n=>`<li>+ ${esc(n.nome)} <span style="color:var(--gold);font-size:11px">${esc(n.grupo)}</span></li>`).join('')}</ul>`:''}
      ${res.atualizados.length?`<ul style="padding-left:20px;font-size:12px;color:var(--muted)">${res.atualizados.map(n=>`<li>↑ ${esc(n.nome)} <span style="color:var(--gold);font-size:11px">${esc(n.grupo)}</span></li>`).join('')}</ul>`:''}`;
    toast(`Importação concluída! ${res.total} item(s)`);
    if(S.grupo==='admin'||S.grupo==='mestre') _carregarHistoricoNfe();
  }catch{toast('Falha ao confirmar','error');}
}

// ═══════════════════════════════════════════════════
// Relatórios
// ═══════════════════════════════════════════════════
function exportar(tipo,alertas){
  fetch(`/api/relatorios/${tipo}?apenas_alertas=${alertas}`,{headers:{Authorization:`Bearer ${S.token}`}})
    .then(r=>r.blob()).then(blob=>{
      const link=document.createElement('a');
      link.href=URL.createObjectURL(blob);
      link.download=`estoque_${Date.now()}.${tipo==='excel'?'xlsx':'pdf'}`;
      link.click(); URL.revokeObjectURL(link.href);
    }).catch(()=>toast('Erro ao gerar relatório','error'));
}





function exportarAtivos(tipo){
  const status=$('rel-ativos-status')?.value||'ativo';
  fetch(`/api/relatorios/ativos/${tipo}?status=${status}`,{headers:{Authorization:`Bearer ${S.token}`}})
    .then(r=>r.blob()).then(blob=>{
      const link=document.createElement('a');
      link.href=URL.createObjectURL(blob);
      link.download=`ativos_${Date.now()}.${tipo==='excel'?'xlsx':'pdf'}`;
      link.click(); URL.revokeObjectURL(link.href);
    }).catch(()=>toast('Erro ao gerar relatório','error'));
}

function exportarNotificacoes(tipo){
  fetch(`/api/relatorios/notificacoes/${tipo}`,{headers:{Authorization:`Bearer ${S.token}`}})
    .then(r=>r.blob()).then(blob=>{
      const link=document.createElement('a');
      link.href=URL.createObjectURL(blob);
      link.download=`notificacoes_${Date.now()}.xlsx`;
      link.click(); URL.revokeObjectURL(link.href);
    }).catch(()=>toast('Erro ao gerar relatório','error'));
}

// ═══════════════════════════════════════════════════
// Modal lista de unidades de patrimônio
// ═══════════════════════════════════════════════════
let _unidMatId    = null;
let _unidMatNome  = '';
let _unidSelecionada = null;

async function abrirListaUnidades(matId, matNome){
  _unidMatId   = matId;
  _unidMatNome = matNome;
  _unidSelecionada = null;
  $('unid-titulo').textContent      = 'Unidades — ' + matNome;
  $('unid-nome-material').textContent = '';
  $('unid-form-add').style.display  = 'none';
  $('unid-painel').innerHTML = '<p style="color:var(--muted);font-size:13px;text-align:center;margin-top:40px">← Selecione uma unidade para ver os detalhes</p>';
  $('modal-unidades').style.display = 'flex';
  await _carregarCardsUnidades();
}

async function _carregarCardsUnidades(){
  const unidades = await api('GET', `/patrimonio/${_unidMatId}/unidades`);
  if(!unidades) return;

  const ativas    = unidades.filter(u=>u.status==='ativo');
  const retiradas = unidades.filter(u=>u.status==='retirado');
  $('unid-resumo').textContent = `${ativas.length} em estoque · ${retiradas.length} retirada(s)`;

  const container = $('unid-lista-cards');
  if(!unidades.length){
    container.innerHTML = '<p style="color:var(--muted);font-size:13px;padding:16px">Nenhuma unidade cadastrada ainda.</p>';
    return;
  }

  const origemTag = {
    manual: '<span class="origem-tag origem-manual">Manual</span>',
    xml:    '<span class="origem-tag origem-xml">XML</span>',
  };

  container.innerHTML = unidades.map(u=>`
    <div class="uni-card ${u.status==='retirado'?'retirada':''}"
         id="uni-card-${u.id}"
         onclick="selecionarUnidade(${u.id}, ${JSON.stringify(u).replace(/"/g,'&quot;')})">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
        <span class="uni-status-dot ${u.status}"></span>
        <strong style="font-size:13px">${u.codigo || '<em style="color:var(--muted);font-weight:400">Sem código</em>'}</strong>
        <span style="margin-left:auto">${origemTag[u.origem]||origemTag.manual}</span>
      </div>
      <div style="font-size:11px;color:var(--muted)">
        ${new Date(u.criado_em).toLocaleDateString('pt-BR')} ·
        ${u.status==='ativo'?'Em estoque':'<span class="badge badge-saida" style="font-size:10px">Saída</span>'}
      </div>
    </div>`).join('');
}

function selecionarUnidade(id, u){
  // Destacar card selecionado
  document.querySelectorAll('.uni-card').forEach(el=>el.classList.remove('selected'));
  const card = $('uni-card-'+id);
  if(card) card.classList.add('selected');
  _unidSelecionada = u;

  const canEdit = S.grupo==='admin' || S.grupo==='editor';
  const origemLabel = {manual:'Cadastro manual',xml:'Importação NF-e',sistema:'Sistema'}[u.origem]||u.origem;
  const origemCor   = u.origem==='xml'?'#1B5E20':'#303F9F';

  let html = `
    <div style="display:flex;align-items:start;justify-content:space-between;margin-bottom:16px">
      <div>
        <div style="font-size:17px;font-weight:700;color:var(--green);margin-bottom:2px">
          ${u.codigo||'<span style="color:var(--muted);font-weight:400;font-size:14px">Sem código de patrimônio</span>'}
        </div>
        <div style="font-size:12px;color:var(--muted)">Unidade #${u.id}</div>
      </div>
      <span class="badge ${u.status==='ativo'?'badge-ok':'badge-alert'}" style="font-size:12px">
        ${u.status==='ativo'?'Em estoque':'Retirado'}
      </span>
    </div>

    <div style="display:flex;flex-direction:column;gap:10px;font-size:13px">
      <div style="display:flex;gap:8px;align-items:center">
        <span style="color:var(--muted);min-width:100px">Origem</span>
        <span style="font-weight:600;color:${origemCor}">${origemLabel}</span>
        ${u.nf_numero?`<span style="font-size:11px;color:var(--muted)">NF-e ${u.nf_numero}</span>`:''}
      </div>
      <div style="display:flex;gap:8px">
        <span style="color:var(--muted);min-width:100px">Cadastrado em</span>
        <span>${new Date(u.criado_em).toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'})}</span>
      </div>
      ${u.observacao?`<div style="display:flex;gap:8px">
        <span style="color:var(--muted);min-width:100px">Observação</span>
        <span>${esc(u.observacao)}</span>
      </div>`:''}
      ${u.status==='retirado'&&u.retirado_em?`
      <div style="display:flex;gap:8px">
        <span style="color:var(--muted);min-width:100px">Retirado em</span>
        <span style="color:var(--danger)">${new Date(u.retirado_em).toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'})}</span>
      </div>
      ${u.retirado_por?`<div style="display:flex;gap:8px">
        <span style="color:var(--muted);min-width:100px">Retirado por</span>
        <span>${esc(u.retirado_por)}</span>
      </div>`:''}
      ${u.motivo_saida?`<div style="display:flex;gap:8px">
        <span style="color:var(--muted);min-width:100px">Motivo</span>
        <span class="badge ${u.motivo_saida==='colaborador'?'badge-colab':'badge-defeito'}">
          ${u.motivo_saida==='colaborador'?'Atribuído a colaborador':'Defeito / Ruim'}
        </span>
      </div>`:''}
      `:''}
    </div>`;

  // Seção de patrimônio (edição de código)
  if(canEdit){
    html += `
    <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
      <p style="font-size:12px;font-weight:600;color:var(--green);margin-bottom:8px">Código de patrimônio</p>
      <div style="display:flex;gap:8px">
        <input type="text" id="patr-codigo-input" class="patr-input"
          placeholder="Ex: TI-001, MON-005"
          value="${u.codigo||''}"
          style="flex:1;font-size:14px"
          oninput="this.value=this.value.toUpperCase()"
          onkeydown="if(event.key==='Enter') salvarCodigoPatrimonio(${u.id})"/>
        <button class="btn btn-primary btn-sm" onclick="salvarCodigoPatrimonio(${u.id})">Salvar</button>
      </div>
      <p style="font-size:11px;color:var(--muted);margin-top:5px">
        Formato: letras + números, com hífen opcional (ex: TI-001, MON-005, NB2024)
      </p>
    </div>`;
  }

  $('unid-painel').innerHTML = html;
}

async function salvarCodigoPatrimonio(unidadeId){
  const codigo = $('patr-codigo-input').value.trim().toUpperCase();
  if(!codigo){ toast('Informe o código de patrimônio','error'); return; }

  const r = await api('PATCH', `/patrimonio/${_unidMatId}/unidades/${unidadeId}/codigo`, {codigo});
  if(r){
    toast('Código salvo: ' + r.codigo);
    await _carregarCardsUnidades();
    // Atualizar painel com dados atualizados
    selecionarUnidade(r.id, r);
  }
}

function abrirAtribuirCodigo(matId, unidadeId, codigoAtual){
  $('codigo-mat-id').value = matId;
  $('codigo-unidade-id').value = unidadeId;
  $('codigo-valor').value = codigoAtual || '';
  $('codigo-unidade-info').textContent = `Unidade #${unidadeId} — ${codigoAtual ? 'Editar código: '+codigoAtual : 'Sem código ainda'}`;
  $('modal-codigo-unidade').style.display = 'flex';
  setTimeout(()=>$('codigo-valor').focus(), 100);
}

async function salvarCodigoInline(){
  const matId = $('codigo-mat-id').value;
  const unidadeId = $('codigo-unidade-id').value;
  const codigo = $('codigo-valor').value.trim().toUpperCase();
  if(!codigo){ toast('Informe o código','error'); return; }
  const r = await api('PATCH', `/patrimonio/${matId}/unidades/${unidadeId}/codigo`, {codigo});
  if(r){
    fecharModal('modal-codigo-unidade');
    toast('Código salvo: ' + r.codigo);
    // Reabrir a linha expandida para refletir o novo código
    const row = document.getElementById('mat-detail-'+matId);
    if(row && row.style.display !== 'none'){
      const mat = S.materiais.find(m=>m.id===parseInt(matId));
      if(mat) toggleMatDetail(parseInt(matId), null, true);
    }
  }
}

function abrirFormAddUnidadeLista(){
  $('unid-form-add').style.display = 'block';
  $('unid-add-rows').innerHTML = `
    <div class="unid-add-row" style="display:grid;grid-template-columns:1fr 1fr auto;gap:8px;margin-bottom:8px;align-items:end">
      <div>
        <label style="font-size:11px;font-weight:600;color:var(--muted);display:block;margin-bottom:4px">Código de patrimônio</label>
        <input type="text" class="patr-input" placeholder="ex: TI-001"
          oninput="this.value=this.value.toUpperCase()"/>
      </div>
      <div>
        <label style="font-size:11px;font-weight:600;color:var(--muted);display:block;margin-bottom:4px">Observação</label>
        <input type="text" placeholder="ex: Sala 3, Recepção…"/>
      </div>
      <button class="btn btn-danger btn-sm" onclick="this.closest('.unid-add-row').remove()" style="margin-bottom:0">✕</button>
    </div>`;
}

function adicionarLinhaUnidadeLista(){
  const div = document.createElement('div');
  div.className = 'unid-add-row';
  div.style.cssText = 'display:grid;grid-template-columns:1fr 1fr auto;gap:8px;margin-bottom:8px;align-items:end';
  div.innerHTML = `
    <div>
      <label style="font-size:11px;font-weight:600;color:var(--muted);display:block;margin-bottom:4px">Código de patrimônio</label>
      <input type="text" class="patr-input" placeholder="ex: TI-001"
        oninput="this.value=this.value.toUpperCase()"/>
    </div>
    <div>
      <label style="font-size:11px;font-weight:600;color:var(--muted);display:block;margin-bottom:4px">Observação</label>
      <input type="text" placeholder="ex: Sala 3…"/>
    </div>
    <button class="btn btn-danger btn-sm" onclick="this.closest('.unid-add-row').remove()" style="margin-bottom:0">✕</button>`;
  $('unid-add-rows').appendChild(div);
}

async function salvarUnidadesLista(){
  const rows = document.querySelectorAll('#unid-add-rows .unid-add-row');
  const payload = Array.from(rows).map(row=>{
    const inputs = row.querySelectorAll('input');
    const codigo = inputs[0].value.trim().toUpperCase();
    return { codigo: codigo||null, observacao: inputs[1].value.trim()||null, origem:'manual' };
  });

  if(!payload.length){ toast('Adicione ao menos uma linha','error'); return; }

  const r = await api('POST', `/patrimonio/${_unidMatId}/unidades`, payload);
  if(r){
    toast(`${r.criadas} unidade(s) adicionada(s)!`);
    $('unid-form-add').style.display = 'none';
    await _carregarCardsUnidades();
    if(S.materiais.length) await carregarMateriais();
  }
}

// ═══════════════════════════════════════════════════
// Detalhes / Timeline / Patrimônio
// ═══════════════════════════════════════════════════
let _detMatId = null;
let _detUsaPatrimonio = false;

async function abrirDetalhes(matId){
  _detMatId = matId;
  $('det-timeline').innerHTML = '<div class="tl-empty">Carregando…</div>';
  $('det-form-unidade').style.display = 'none';
  $('det-form-retirada-unidade').style.display = 'none';
  $('modal-detalhes').style.display = 'flex';

  const dados = await api('GET', `/patrimonio/${matId}/timeline`);
  if(!dados){ fecharModal('modal-detalhes'); return; }

  const mat = dados.material;
  _detUsaPatrimonio = mat.usa_patrimonio;

  $('det-titulo').textContent = mat.nome;
  $('det-subtitulo').textContent = `${mat.categoria} / ${mat.grupo}`;
  $('det-qtd-badge').textContent = `${mat.quantidade} ${mat.unidade} em estoque`;
  $('det-qtd-badge').className = `badge ${mat.quantidade > 0 ? 'badge-ok' : 'badge-alert'}`;

  const canEdit = S.grupo === 'admin' || S.grupo === 'editor';

  // Botão adicionar unidade só aparece para materiais com patrimônio
  const btnAdd = $('det-btn-add-unidade');
  btnAdd.style.display = (mat.usa_patrimonio && canEdit) ? '' : 'none';

  // Botão retirar unidade específica
  const btnRet = $('det-form-retirada-unidade');
  if(mat.usa_patrimonio && canEdit){
    // Carregar unidades ativas para o select
    const unidades = await api('GET', `/patrimonio/${matId}/unidades`);
    const ativas = (unidades||[]).filter(u => u.status === 'ativo');
    $('ret-uni-sel').innerHTML = ativas.length
      ? ativas.map(u => `<option value="${u.id}">${u.codigo || 'Sem código'} — cadastrado em ${new Date(u.criado_em).toLocaleDateString('pt-BR')}</option>`).join('')
      : '<option value="">Nenhuma unidade ativa</option>';
  }

  _renderizarTimeline(dados.eventos, mat.usa_patrimonio, mat.quantidade, canEdit);
}

function _renderizarTimeline(eventos, usaPatrimonio, qtdAtual, canEdit){
  const container = $('det-timeline');

  if(!eventos.length){
    container.innerHTML = '<div class="tl-empty">Nenhuma movimentação registrada ainda.</div>';
    return;
  }

  const motivo_label = {colaborador:'Atribuído a colaborador', defeito:'Defeito / Ruim'};

  // Agrupar por código de patrimônio se usa_patrimonio
  if(usaPatrimonio){
    const porCodigo = {};
    eventos.forEach(e=>{
      const chave = e.codigo || '(sem código)';
      if(!porCodigo[chave]) porCodigo[chave] = [];
      porCodigo[chave].push(e);
    });

    let html = '';
    Object.entries(porCodigo).forEach(([codigo, evts])=>{
      const ultimo = evts[evts.length-1];
      const retirado = evts.some(e=>e.tipo==='saida');
      html += `<div style="margin-bottom:20px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <span style="font-weight:600;font-size:13px;color:var(--green)">
            🏷 ${codigo}
          </span>
          <span class="badge ${retirado?'badge-alert':'badge-ok'}">${retirado?'Retirado':'Em estoque'}</span>
        </div>
        <div class="timeline">`;

      evts.forEach(e=>{
        const data = new Date(e.data).toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'});
        if(e.tipo==='entrada'){
          html += `<div class="tl-item">
            <div class="tl-dot entrada"></div>
            <div class="tl-card entrada">
              <div class="tl-data">${data}</div>
              <div class="tl-titulo">↑ Entrada cadastrada</div>
              ${e.observacao?`<div class="tl-detalhe">${esc(e.observacao)}</div>`:''}
            </div>
          </div>`;
        } else {
          html += `<div class="tl-item">
            <div class="tl-dot saida"></div>
            <div class="tl-card saida">
              <div class="tl-data">${data}</div>
              <div class="tl-titulo">↓ Retirada — ${motivo_label[e.motivo]||e.motivo}</div>
              <div class="tl-detalhe">
                ${e.observacao?esc(e.observacao)+' · ':''} por ${esc(e.usuario||'Sistema')}
              </div>
            </div>
          </div>`;
        }
      });
      html += `</div></div>`;
    });
    container.innerHTML = html;

    // Mostrar botão de retirar unidade específica
    if(canEdit && qtdAtual > 0){
      $('det-form-retirada-unidade').style.display = 'block';
    }

  } else {
    // Material sem patrimônio — timeline simples
    let html = '<div class="timeline">';
    eventos.forEach(e=>{
      const data = new Date(e.data).toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'});
      if(e.tipo==='entrada'){
        html += `<div class="tl-item">
          <div class="tl-dot entrada"></div>
          <div class="tl-card entrada">
            <div class="tl-data">${data}</div>
            <div class="tl-titulo">↑ Entrada — ${e.quantidade} ${e.subtipo==='movimentacao'?'un':''}</div>
            ${e.observacao?`<div class="tl-detalhe">${esc(e.observacao)}</div>`:''}
          </div>
        </div>`;
      } else {
        html += `<div class="tl-item">
          <div class="tl-dot saida"></div>
          <div class="tl-card saida">
            <div class="tl-data">${data}</div>
            <div class="tl-titulo">↓ Saída — ${e.quantidade} un · ${motivo_label[e.motivo]||e.motivo||''}</div>
            <div class="tl-detalhe">
              ${e.observacao?esc(e.observacao)+' · ':''} por ${esc(e.usuario||'Sistema')}
            </div>
          </div>
        </div>`;
      }
    });
    html += '</div>';
    container.innerHTML = html;
  }
}

function abrirFormAddUnidade(){
  $('det-form-unidade').style.display = 'block';
  $('det-unidades-inputs').innerHTML = `
    <div class="det-uni-row" style="display:flex;gap:8px;margin-bottom:8px">
      <input type="text" placeholder="Código de patrimônio (opcional)" style="flex:2"/>
      <input type="text" placeholder="Observação" style="flex:2"/>
      <button class="btn btn-danger btn-sm" onclick="this.closest('.det-uni-row').remove()" style="flex:none">✕</button>
    </div>`;
}

function adicionarLinhaUnidade(){
  const div = document.createElement('div');
  div.className = 'det-uni-row';
  div.style.cssText = 'display:flex;gap:8px;margin-bottom:8px';
  div.innerHTML = `
    <input type="text" placeholder="Código de patrimônio (opcional)" style="flex:2"/>
    <input type="text" placeholder="Observação" style="flex:2"/>
    <button class="btn btn-danger btn-sm" onclick="this.closest('.det-uni-row').remove()" style="flex:none">✕</button>`;
  $('det-unidades-inputs').appendChild(div);
}

async function salvarUnidades(){
  const rows = document.querySelectorAll('#det-unidades-inputs .det-uni-row');
  const payload = Array.from(rows).map(row=>{
    const inputs = row.querySelectorAll('input');
    return { codigo: inputs[0].value.trim()||null, observacao: inputs[1].value.trim()||null };
  }).filter(u=>u.codigo!==null||true); // aceita sem código

  if(!payload.length){ toast('Adicione ao menos uma unidade','error'); return; }

  const r = await api('POST', `/patrimonio/${_detMatId}/unidades`, payload);
  if(r){
    toast(`${r.criadas} unidade(s) adicionada(s)!`);
    $('det-form-unidade').style.display = 'none';
    await abrirDetalhes(_detMatId); // recarregar timeline
    // Atualizar lista principal de materiais
    if(S.materiais.length) await carregarMateriais();
  }
}

async function confirmarRetiradaUnidade(){
  const unidadeId = parseInt($('ret-uni-sel').value);
  const motivo    = $('ret-uni-motivo').value;
  const obs       = $('ret-uni-obs').value.trim();
  if(!unidadeId){ toast('Selecione uma unidade','error'); return; }

  const r = await api('POST', `/patrimonio/${_detMatId}/retirar-unidade`,{
    unidade_id: unidadeId, motivo, observacao: obs||null,
  });
  if(r){
    toast('Retirada registrada!');
    $('ret-uni-obs').value = '';
    await abrirDetalhes(_detMatId);
    if(S.materiais.length) await carregarMateriais();
  }
}

// ═══════════════════════════════════════════════════
// Dashboard — filtros
// ═══════════════════════════════════════════════════
let _dashMateriais = [];   // cache da lista completa para filtrar localmente

function _popularFiltrosDash(mats){
  const cats = {}; const grps = {};
  mats.forEach(m=>{
    cats[m.grupo.categoria.id] = m.grupo.categoria.nome;
    grps[m.grupo_id] = m.grupo.nome;
  });
  const catSel = $('dash-cat-filtro');
  const grpSel = $('dash-grp-filtro');
  catSel.innerHTML = '<option value="">Todas as categorias</option>' +
    Object.entries(cats).map(([id,nome])=>`<option value="${id}">${nome}</option>`).join('');
  grpSel.innerHTML = '<option value="">Todos os grupos</option>' +
    Object.entries(grps).map(([id,nome])=>`<option value="${id}">${nome}</option>`).join('');
}

function filtrarDashboard(){
  const catId  = $('dash-cat-filtro').value;
  const grpId  = $('dash-grp-filtro').value;
  const alerta = $('dash-apenas-alerta').checked;

  // Atualizar grupos no segundo filtro conforme categoria
  if(catId){
    const grpsFilt = _dashMateriais.filter(m=>m.grupo.categoria.id==catId);
    const grpsUniq = {};
    grpsFilt.forEach(m=>{ grpsUniq[m.grupo_id]=m.grupo.nome; });
    $('dash-grp-filtro').innerHTML = '<option value="">Todos os grupos</option>' +
      Object.entries(grpsUniq).map(([id,nome])=>`<option value="${id}">${nome}</option>`).join('');
  } else {
    const grpsUniq = {};
    _dashMateriais.forEach(m=>{ grpsUniq[m.grupo_id]=m.grupo.nome; });
    $('dash-grp-filtro').innerHTML = '<option value="">Todos os grupos</option>' +
      Object.entries(grpsUniq).map(([id,nome])=>`<option value="${id}">${nome}</option>`).join('');
  }

  const lista = _dashMateriais.filter(m=>{
    if(catId  && m.grupo.categoria.id != catId) return false;
    if(grpId  && m.grupo_id != grpId)           return false;
    if(alerta && !m.alerta_minimo)               return false;
    return true;
  });

  // Resumo agregado quando há filtro ativo
  const filtroAtivo = catId || grpId || alerta;
  const sumEl = $('dash-filter-summary');
  if(filtroAtivo && lista.length){
    const totalItens = lista.length;
    const totalQtd   = lista.reduce((acc,m)=>acc+m.quantidade,0);
    const totalValor = lista.reduce((acc,m)=>acc+(m.valor_total||0),0);
    const emAlerta   = lista.filter(m=>m.alerta_minimo).length;
    const label = catId
      ? (grpId ? lista[0]?.grupo.nome : lista[0]?.grupo.categoria.nome)
      : 'Seleção';
    sumEl.innerHTML = `
      <div class="dash-filter-summary">
        <div class="fs-item"><span class="fs-val">${totalItens}</span><span class="fs-lbl">Itens filtrados</span></div>
        <div class="fs-item"><span class="fs-val">${totalQtd.toFixed(2).replace('.00','')}</span><span class="fs-lbl">Qtd. total</span></div>
        ${totalValor>0?`<div class="fs-item"><span class="fs-val">R$ ${totalValor.toFixed(2)}</span><span class="fs-lbl">Valor total estimado</span></div>`:''}
        ${emAlerta>0?`<div class="fs-item"><span class="fs-val warn">${emAlerta}</span><span class="fs-lbl">Em alerta</span></div>`:''}
        <div class="fs-item" style="margin-left:auto;align-self:center">
          <span style="font-size:12px;color:var(--muted)">Filtro: <strong>${label}</strong></span>
        </div>
      </div>`;
    sumEl.style.display='block';
  } else {
    sumEl.style.display='none';
  }

  _renderizarDashBody(lista);
}

function _renderizarDashBody(lista){
  $('dash-body').innerHTML = !lista.length
    ? '<tr><td colspan="8"><div class="empty"><span>📭</span>Nenhum item encontrado</div></td></tr>'
    : lista.map(m=>`
      <tr class="${m.alerta_minimo?'row-alert':''}">
        <td><strong>${esc(m.nome)}</strong></td>
        <td class="hide-mobile">${m.grupo.categoria.nome}</td>
        <td>${m.grupo.nome}</td>
        <td>${m.quantidade} ${m.unidade}</td>
        <td class="hide-mobile">${m.grupo.quantidade_minima>0?m.grupo.quantidade_minima+' '+m.unidade:'—'}</td>
        <td class="hide-mobile">${fmt(m.criado_em)}</td>
        <td class="hide-mobile">${m.ultima_retirada?fmtDT(m.ultima_retirada):'—'}</td>
        <td>${m.alerta_minimo
          ?'<span class="badge badge-alert">⚠ Alerta</span>'
          :'<span class="badge badge-ok">✓ OK</span>'}</td>
      </tr>`).join('');
}

// ═══════════════════════════════════════════════════
// Exportar saídas
// ═══════════════════════════════════════════════════
function exportarSaidas(tipo){
  const motivo = $('rel-saida-motivo').value;
  const inicio = $('rel-saida-inicio').value;
  const fim    = $('rel-saida-fim').value;
  let url = `/api/relatorios/saidas/${tipo}?`;
  if(motivo) url += `motivo=${motivo}&`;
  if(inicio) url += `data_inicio=${inicio}&`;
  if(fim)    url += `data_fim=${fim}&`;

  fetch(url, {headers:{Authorization:`Bearer ${S.token}`}})
    .then(r=>r.blob()).then(blob=>{
      const link=document.createElement('a');
      link.href=URL.createObjectURL(blob);
      link.download=`saidas_${Date.now()}.${tipo==='excel'?'xlsx':'pdf'}`;
      link.click(); URL.revokeObjectURL(link.href);
    }).catch(()=>toast('Erro ao gerar relatório','error'));
}

// ═══════════════════════════════════════════════════
// Perfil próprio
// ═══════════════════════════════════════════════════
async function carregarPerfil(){
  const me = await api('GET','/usuarios/me');
  if(!me) return;
  $('perfil-nome').value  = me.nome;
  $('perfil-email').value = me.email;
  $('perfil-grupo').value = {admin:'Admin',editor:'Editor',viewer:'Viewer'}[me.grupo]||me.grupo;
  // Limpar campos de senha
  $('perfil-senha-atual').value='';
  $('perfil-nova-senha').value='';
  $('perfil-confirma-senha').value='';
}

async function salvarPerfil(){
  const nome = $('perfil-nome').value.trim();
  if(!nome){toast('Nome obrigatório','error');return;}
  const r = await api('PUT','/usuarios/me/perfil',{nome});
  if(r){
    S.nome = r.nome;
    localStorage.setItem('nome', r.nome);
    $('sidebar-user').textContent = r.nome;
    toast('Nome atualizado com sucesso!');
  }
}

async function salvarMinhaSenha(){
  const atual   = $('perfil-senha-atual').value;
  const nova    = $('perfil-nova-senha').value;
  const confirma= $('perfil-confirma-senha').value;
  if(!atual||!nova||!confirma){toast('Preencha todos os campos','error');return;}
  if(nova !== confirma){toast('As senhas não coincidem','error');return;}
  if(nova.length < 6){toast('Nova senha deve ter ao menos 6 caracteres','error');return;}
  const r = await api('PUT','/usuarios/me/senha',{senha_atual:atual,nova_senha:nova});
  if(r !== null){
    toast('Senha alterada com sucesso!');
    $('perfil-senha-atual').value='';
    $('perfil-nova-senha').value='';
    $('perfil-confirma-senha').value='';
  }
}

// ═══════════════════════════════════════════════════
// Senha admin
// ═══════════════════════════════════════════════════
function abrirModalSenhaAdmin(id, nome){
  $('senha-admin-usr-id').value = id;
  $('modal-senha-admin-title').textContent = `Redefinir senha — ${nome}`;
  $('senha-admin-nova').value='';
  $('senha-admin-confirma').value='';
  $('modal-senha-admin').style.display='flex';
}

async function salvarSenhaAdmin(){
  const id      = $('senha-admin-usr-id').value;
  const nova    = $('senha-admin-nova').value;
  const confirma= $('senha-admin-confirma').value;
  if(!nova||!confirma){toast('Preencha todos os campos','error');return;}
  if(nova !== confirma){toast('As senhas não coincidem','error');return;}
  if(nova.length < 6){toast('Senha deve ter ao menos 6 caracteres','error');return;}
  const r = await api('PUT',`/usuarios/${id}/senha`,{nova_senha:nova});
  if(r !== null){
    fecharModal('modal-senha-admin');
    toast('Senha redefinida com sucesso!');
  }
}

// ═══════════════════════════════════════════════════
// Expand linha de material
// ═══════════════════════════════════════════════════
async function toggleMatDetail(id, tr, forceReload){
  const detail = $('mat-detail-'+id);
  if(!detail) return;
  let open;
  if(forceReload){
    open = detail.classList.contains('open');
    if(!open) return;
  } else {
    open = detail.classList.toggle('open');
    const btn = tr && tr.querySelector('.mat-expand-btn');
    if(btn) btn.textContent = open ? '▼' : '▶';
    if(!open) return;
  }

  const mat = S.materiais.find(m=>m.id===id);
  if(!mat) return;

  const canEdit = S.grupo === 'admin' || S.grupo === 'editor';

  const cell = detail.querySelector('td');
  const tagBadge = t => t==='novo'
    ? '<span class="badge badge-novo">Novo</span>'
    : t==='usado'
      ? '<span class="badge badge-usado">Usado</span>'
      : t==='atribuido'
        ? '<span class="badge" style="background:#e0e0e0;color:#888">Atribuído</span>'
        : t==='saida'
          ? '<span class="badge badge-saida">Saída</span>'
          : '<span style="color:var(--muted);font-size:11px">—</span>';

  const tblStyle = 'width:100%;border-collapse:collapse;font-size:12px';
  const thStyle  = 'text-align:left;padding:5px 10px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.4px;color:var(--muted);border-bottom:1px solid var(--border)';
  const tdStyle  = 'padding:5px 10px;border-bottom:1px solid var(--border)';

  if(!!mat.usa_patrimonio){
    cell.innerHTML='<div style="font-size:12px;color:var(--muted)">Carregando…</div>';
    const unidades = await api('GET', `/patrimonio/${id}/unidades`);
    if(!unidades){ cell.innerHTML='<div style="color:var(--danger);font-size:12px">Erro ao carregar</div>'; return; }
    if(!unidades.length){
      cell.innerHTML='<div style="font-size:12px;color:var(--muted);padding:6px 0">Nenhuma unidade cadastrada. Use <strong>Adicionar Material</strong> para registrar unidades.</div>';
      return;
    }
    const ativas     = unidades.filter(u=>u.status==='ativo'&&u.tag!=='atribuido').length;
    const atribuidas = unidades.filter(u=>u.tag==='atribuido').length;
    const retiradas  = unidades.filter(u=>u.status==='retirado').length;
    cell.innerHTML = `
      <div style="font-size:12px;font-weight:600;color:var(--green);margin-bottom:8px">
        ${ativas} em estoque · ${atribuidas} atribuída(s) · ${retiradas} retirada(s)
      </div>
      <div style="overflow-x:auto">
      <table style="${tblStyle}">
        <thead><tr>
          <th style="${thStyle}">#</th>
          <th style="${thStyle}">Código</th>
          <th style="${thStyle}">Valor unit.</th>
          <th style="${thStyle}">Tag</th>
          <th style="${thStyle}">Cadastrado em</th>
          <th style="${thStyle}">Status</th>
          <th style="${thStyle}">Atribuído a</th>
          ${canEdit?`<th style="${thStyle}">Ações</th>`:''}
        </tr></thead>
        <tbody>
          ${unidades.map((u,i)=>{
            const val = (u.valor_unitario != null && u.valor_unitario > 0) ? 'R$ '+u.valor_unitario.toFixed(2)
                      : u.valor_unitario === 0 ? '<span style="color:var(--muted);font-size:11px">Sem valor</span>'
                      : mat.valor_unitario != null ? 'R$ '+mat.valor_unitario.toFixed(2) : '—';
            const isAtrib = u.tag==='atribuido';
            const tagAtual = u.status==='retirado' ? 'saida' : (u.tag || mat.tag);
            const cor = u.status==='retirado' ? 'color:var(--muted)' : isAtrib ? 'opacity:.6' : '';
            const statusLabel = isAtrib ? '<span class="badge" style="background:#e0e0e0;color:#888;font-size:10px">Atribuído</span>'
                              : u.status==='ativo' ? '<span class="badge badge-ok" style="font-size:10px">Em estoque</span>'
                              : '<span class="badge badge-alert" style="font-size:10px">Retirado</span>';
            const ativoCell = isAtrib && u.ativo_nome
              ? `<div style="font-size:11px;font-weight:600;color:var(--green)">${esc(u.ativo_nome)}</div>
                 ${u.ativo_categoria?`<div style="font-size:10px;color:var(--muted)">${esc(u.ativo_categoria)}</div>`:''}`
              : '<span style="color:var(--muted);font-size:11px">—</span>';
            const acoesBtn = canEdit && u.status==='ativo' && !isAtrib
              ? `<button class="btn btn-secondary btn-sm" onclick="abrirAtribuirCodigo(${id},${u.id},'${(u.codigo||'').replace(/'/g,'')}')">Código</button>`
              : '';
            return `<tr style="${cor}">
              <td style="${tdStyle}">${i+1}</td>
              <td style="${tdStyle};font-family:monospace;font-weight:600">${u.codigo||'<span style="color:var(--muted);font-style:italic">Sem código</span>'}</td>
              <td style="${tdStyle}">${val}</td>
              <td style="${tdStyle}">${tagBadge(tagAtual)}</td>
              <td style="${tdStyle}">${new Date(u.criado_em).toLocaleDateString('pt-BR')}</td>
              <td style="${tdStyle}">${statusLabel}</td>
              <td style="${tdStyle}">${ativoCell}</td>
              ${canEdit?`<td style="${tdStyle}">${acoesBtn}</td>`:''}
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
  } else {
    cell.innerHTML='<div style="font-size:12px;color:var(--muted)">Carregando…</div>';
    const dados = await api('GET', `/patrimonio/${id}/timeline`);
    if(!dados){ cell.innerHTML='<div style="color:var(--danger);font-size:12px">Erro ao carregar</div>'; return; }

    const entradas = dados.eventos.filter(e=>e.tipo==='entrada');
    if(!entradas.length){
      cell.innerHTML='<div style="font-size:12px;color:var(--muted)">Nenhuma entrada registrada.</div>';
      return;
    }
    cell.innerHTML = `
      <div style="font-size:12px;font-weight:600;color:var(--green);margin-bottom:8px">
        ${entradas.length} lote(s) de entrada
      </div>
      <div style="overflow-x:auto">
      <table style="${tblStyle}">
        <thead><tr>
          <th style="${thStyle}">Lote</th>
          <th style="${thStyle}">Qtd.</th>
          <th style="${thStyle}">Valor unit.</th>
          <th style="${thStyle}">Total lote</th>
          <th style="${thStyle}">Tag</th>
          <th style="${thStyle}">Data</th>
          <th style="${thStyle}">Obs.</th>
        </tr></thead>
        <tbody>
          ${entradas.map((e,i)=>{
            const val = e.valor_unitario!=null ? 'R$ '+e.valor_unitario.toFixed(2)
                      : mat.valor_unitario!=null ? 'R$ '+mat.valor_unitario.toFixed(2) : '—';
            const total = e.valor_unitario!=null ? 'R$ '+(e.valor_unitario*e.quantidade).toFixed(2)
                        : mat.valor_unitario!=null ? 'R$ '+(mat.valor_unitario*e.quantidade).toFixed(2) : '—';
            const loteTag = e.tag || 'novo';
            const isDev = e.observacao && e.observacao.toLowerCase().includes('devolução');
            return `<tr>
              <td style="${tdStyle};font-weight:600">${isDev?'Dev.':'Lote'} ${i+1}</td>
              <td style="${tdStyle}">${e.quantidade} ${mat.unidade}</td>
              <td style="${tdStyle}">${val}</td>
              <td style="${tdStyle}">${total}</td>
              <td style="${tdStyle}">${tagBadge(loteTag)}</td>
              <td style="${tdStyle};white-space:nowrap">${fmtDT(e.data)}</td>
              <td style="${tdStyle};color:var(--muted)">${e.observacao||'—'}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
  }
}

// ═══════════════════════════════════════════════════
// Categ. / Grupos Ativos
// ═══════════════════════════════════════════════════
const SA = { cats:[], grupos:[] };

async function carregarCategoriasAtivo(){
  const [cats,grps]=await Promise.all([
    api('GET','/ativos-categorias/'),
    api('GET','/ativos-categorias/grupos/'),
  ]);
  if(!cats) return;
  SA.cats=cats; SA.grupos=grps||[];
  renderizarCategoriasAtivo();
}

function renderizarCategoriasAtivo(){
  const canEdit=S.grupo==='admin'||S.grupo==='editor';
  const container=$('cat-ativo-lista');
  if(!SA.cats.length){
    container.innerHTML='<div class="empty"><span>📂</span>Nenhuma categoria cadastrada</div>';
    return;
  }
  let html='';
  SA.cats.forEach(c=>{
    const grpsDaCat=SA.grupos.filter(g=>g.categoria_id===c.id);
    html+=`
    <div class="cat-row" onclick="toggleCatAtivo(${c.id})">
      <span>
        <span class="cat-chevron" id="achev-${c.id}">▶</span>
        <span class="cat-nome" style="margin-left:8px">${esc(c.nome)}</span>
        ${c.descricao?`<span style="color:var(--muted);font-size:12px;margin-left:8px">— ${esc(c.descricao)}</span>`:''}
        <span style="color:var(--muted);font-size:11px;margin-left:8px">(${grpsDaCat.length} grupo(s))</span>
      </span>
      ${canEdit?`<span onclick="event.stopPropagation()" style="display:flex;gap:6px">
        <button class="btn btn-secondary btn-sm" onclick="editarCatAtivo(${c.id})">Editar</button>
        <button class="btn btn-danger btn-sm" onclick="removerCatAtivo(${c.id},'${c.nome.replace(/'/g,"\\'")}')">Remover</button>
      </span>`:''}
    </div>
    <div class="cat-grupos" id="agrupos-${c.id}">`;

    html+=`<!--AFORM_${c.id}-->`;
    grpsDaCat.forEach(g=>{
      html+=`
      <div class="grupo-row">
        <span>
          <strong>${esc(g.nome)}</strong>
          ${g.descricao?`<span style="color:var(--muted);font-size:12px"> — ${esc(g.descricao)}</span>`:''}
        </span>
        ${canEdit?`<span style="display:flex;gap:6px">
          <button class="btn btn-secondary btn-sm" onclick="editarGrupoAtivo(${g.id})">Editar</button>
          <button class="btn btn-danger btn-sm" onclick="removerGrupoAtivo(${g.id},'${g.nome.replace(/'/g,"\\'")}')">Remover</button>
        </span>`:''}
      </div>`;
    });

    if(canEdit){
      html=html.replace(`<!--AFORM_${c.id}-->`,`
        <div style="padding:8px 14px;border-bottom:1px solid var(--border);background:#F8FAF9">
          <button class="btn btn-secondary btn-sm" onclick="toggleFormGrupoAtivo(${c.id})">+ Adicionar grupo</button>
        </div>
        <div class="novo-grupo-form" id="aform-grp-${c.id}">
          <input type="text" id="anovogrp-nome-${c.id}" placeholder="Nome do grupo"/>
          <button class="btn btn-primary btn-sm" onclick="criarGrupoAtivoInline(${c.id})">Criar</button>
        </div>`);
    }
    html+=`</div>`;
  });
  container.innerHTML=html;
}

function toggleCatAtivo(catId){
  const grupos=$(`agrupos-${catId}`);
  const chev=$(`achev-${catId}`);
  const catRow=grupos.previousElementSibling;
  const isOpen=grupos.classList.contains('open');
  grupos.classList.toggle('open',!isOpen);
  catRow.classList.toggle('open',!isOpen);
  chev.textContent=isOpen?'▶':'▼';
}
function toggleFormGrupoAtivo(catId){ $(`aform-grp-${catId}`).classList.toggle('open'); }

async function criarGrupoAtivoInline(catId){
  const nome=$(`anovogrp-nome-${catId}`).value.trim();
  if(!nome){toast('Nome do grupo obrigatório','error');return;}
  const r=await api('POST','/ativos-categorias/grupos/',{nome, categoria_id:catId});
  if(r){toast('Grupo criado!'); await carregarCategoriasAtivo(); toggleCatAtivo(catId);}
}

function abrirModalCatAtivo(){
  $('cat-ativo-id').value=''; $('cat-ativo-nome').value=''; $('cat-ativo-desc').value='';
  $('modal-cat-ativo-title').textContent='Nova categoria';
  $('modal-cat-ativo').style.display='flex';
}

function editarCatAtivo(id){
  const c=SA.cats.find(x=>x.id===id); if(!c) return;
  $('cat-ativo-id').value=id; $('cat-ativo-nome').value=c.nome; $('cat-ativo-desc').value=c.descricao||'';
  $('modal-cat-ativo-title').textContent='Editar categoria';
  $('modal-cat-ativo').style.display='flex';
}

async function salvarCatAtivo(){
  const id=$('cat-ativo-id').value;
  const body={nome:$('cat-ativo-nome').value.trim(), descricao:$('cat-ativo-desc').value.trim()||null};
  if(!body.nome){toast('Nome obrigatório','error');return;}
  const r=id?await api('PUT',`/ativos-categorias/${id}`,body):await api('POST','/ativos-categorias/',body);
  if(r){fecharModal('modal-cat-ativo');toast('Categoria salva!');carregarCategoriasAtivo();}
}

async function removerCatAtivo(id,nome){
  if(!confirm(`Remover "${nome}"? Os grupos dentro dela também serão removidos.`)) return;
  const r=await api('DELETE',`/ativos-categorias/${id}`);
  if(r!==null){toast('Categoria removida');carregarCategoriasAtivo();}
}

function editarGrupoAtivo(id){
  const g=SA.grupos.find(x=>x.id===id); if(!g) return;
  $('grp-ativo-edit-id').value=id; $('grp-ativo-edit-nome').value=g.nome;
  $('grp-ativo-edit-desc').value=g.descricao||'';
  $('modal-grp-ativo').style.display='flex';
}

async function salvarGrupoAtivoEdit(){
  const id=$('grp-ativo-edit-id').value;
  const body={nome:$('grp-ativo-edit-nome').value.trim(),
    descricao:$('grp-ativo-edit-desc').value.trim()||null};
  if(!body.nome){toast('Nome obrigatório','error');return;}
  const r=await api('PUT',`/ativos-categorias/grupos/${id}`,body);
  if(r){fecharModal('modal-grp-ativo');toast('Grupo atualizado!');carregarCategoriasAtivo();}
}

async function removerGrupoAtivo(id,nome){
  if(!confirm(`Remover grupo "${nome}"?`)) return;
  const r=await api('DELETE',`/ativos-categorias/grupos/${id}`);
  if(r!==null){toast('Grupo removido');carregarCategoriasAtivo();}
}

// ═══════════════════════════════════════════════════
// Ativos
// ═══════════════════════════════════════════════════
const SAT = { lista:[], cats:[], grupos:[], selecionado:null, tabAtual:'ativos', inativos:[] };

async function carregarAtivos(){
  const [ativos,cats,grps]=await Promise.all([
    api('GET','/ativos/'),
    api('GET','/ativos-categorias/'),
    api('GET','/ativos-categorias/grupos/'),
  ]);
  if(!ativos) return;
  SAT.lista=ativos; SAT.cats=cats||[]; SAT.grupos=grps||[]; SAT.inativos=[];

  $('atv-cat-filtro').innerHTML='<option value="">Todas as categorias</option>'+
    SAT.cats.map(c=>`<option value="${c.id}">${esc(c.nome)}</option>`).join('');
  $('atv-grp-filtro').innerHTML='<option value="">Todos os grupos</option>'+
    SAT.grupos.map(g=>`<option value="${g.id}">${esc(g.nome)}</option>`).join('');
  renderizarAtivos(ativos);
  trocarTabAtivos('ativos');
  if(SAT.selecionado) selecionarAtivo(SAT.selecionado);
}

function mudarCatFiltroAtivo(){
  const catId=$('atv-cat-filtro').value;
  const grpsFilt=catId?SAT.grupos.filter(g=>g.categoria_id==catId):SAT.grupos;
  $('atv-grp-filtro').innerHTML='<option value="">Todos os grupos</option>'+
    grpsFilt.map(g=>`<option value="${g.id}">${esc(g.nome)}</option>`).join('');
  filtrarAtivos();
}

function filtrarAtivos(){
  const catId=$('atv-cat-filtro').value, grpId=$('atv-grp-filtro').value;
  renderizarAtivos(SAT.lista.filter(a=>{
    if(catId&&a.grupo.categoria_id!=catId) return false;
    if(grpId&&a.grupo_id!=grpId) return false;
    return true;
  }));
}

function renderizarAtivos(lista){
  const container=$('atv-lista');
  if(!lista.length){
    container.innerHTML='<div class="empty" style="background:var(--surface);border-radius:var(--radius);padding:40px"><span>◉</span>Nenhum ativo cadastrado</div>';
    return;
  }
  const canEdit=S.grupo==='admin'||S.grupo==='editor';
  container.innerHTML=lista.map(a=>`
    <div class="ativo-card ${SAT.selecionado===a.id?'selected':''}" id="atv-card-${a.id}" onclick="selecionarAtivo(${a.id})">
      <div style="display:flex;justify-content:space-between;align-items:start">
        <div>
          <div class="ativo-nome">${esc(a.nome)}</div>
          <div class="ativo-sub">${a.grupo.categoria.nome} / ${a.grupo.nome}</div>
          ${a.descricao?`<div class="ativo-sub">${esc(a.descricao)}</div>`:''}
        </div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">
          ${a.itens_ativos>0?`<span class="badge badge-em-uso">${a.itens_ativos} em uso</span>`:'<span class="badge badge-ok">Livre</span>'}
          ${canEdit?`<div style="display:flex;gap:4px;margin-top:4px" onclick="event.stopPropagation()">
            <button class="btn btn-secondary btn-sm" onclick="editarAtivo(${a.id})">Editar</button>
            <button class="btn btn-danger btn-sm" onclick="removerAtivo(${a.id},'${a.nome.replace(/'/g,"\\'")}')">✕</button>
          </div>`:''}
        </div>
      </div>
    </div>`).join('');
}

async function selecionarAtivo(id){
  SAT.selecionado=id;
  document.querySelectorAll('.ativo-card').forEach(el=>el.classList.remove('selected'));
  const card=$('atv-card-'+id); if(card) card.classList.add('selected');

  const ativo=SAT.lista.find(a=>a.id===id); if(!ativo) return;
  const canEdit=S.grupo==='admin'||S.grupo==='editor';

  $('atv-painel').innerHTML=`
    <div class="table-wrap">
      <div class="table-toolbar" style="justify-content:space-between">
        <div>
          <strong style="font-size:14px">${esc(ativo.nome)}</strong>
          <div style="font-size:12px;color:var(--muted);margin-top:2px">${ativo.grupo.categoria.nome} / ${ativo.grupo.nome}</div>
        </div>
        ${canEdit?`<button class="btn btn-primary btn-sm" onclick="abrirModalAtribuir(${id},'${ativo.nome.replace(/'/g,"\\'")}')">↗ Atribuir material</button>`:''}
      </div>
      <div id="atv-itens-wrap">
        <div style="padding:32px;text-align:center;color:var(--muted)">Carregando…</div>
      </div>
    </div>`;

  const itens=await api('GET',`/ativos/${id}/itens`);
  if(!itens){ $('atv-itens-wrap').innerHTML='<div class="empty"><span>⚠</span>Erro ao carregar</div>'; return; }

  if(!itens.length){
    $('atv-itens-wrap').innerHTML='<div class="empty" style="padding:32px"><span>📦</span>Nenhum material atribuído a este ativo</div>';
    return;
  }

  $('atv-itens-wrap').innerHTML=`
    <table>
      <thead><tr>
        <th>Material</th><th>Grupo</th><th>Unidade</th><th>Atribuído em</th><th>Obs.</th>
        ${canEdit?'<th>Ações</th>':''}
      </tr></thead>
      <tbody>
        ${itens.map(i=>`<tr>
          <td><strong>${esc(i.nome_material)}</strong></td>
          <td><span style="color:var(--muted);font-size:12px">${esc(i.categoria_nome)} / </span>${esc(i.grupo_nome)}</td>
          <td style="font-family:monospace;font-weight:600">${i.unidade_codigo||'<span style="color:var(--muted);font-style:italic;font-family:inherit;font-weight:400">sem código</span>'}</td>
          <td>${fmt(i.atribuido_em)}</td>
          <td style="font-size:12px;color:var(--muted)">${i.observacao||'—'}</td>
          ${canEdit?`<td><button class="btn btn-secondary btn-sm" onclick="devolverItem(${id},${i.id})">↩ Devolver</button></td>`:''}
        </tr>`).join('')}
      </tbody>
    </table>`;
}

async function devolverItem(ativoId, itemId){
  if(!confirm('Devolver este material ao estoque? Ele ficará marcado como "Usado".')) return;
  const r=await api('POST',`/ativos/${ativoId}/devolver/${itemId}`);
  if(r){
    toast(`${r.quantidade} ${r.material} devolvido ao estoque (tag: Usado)`);
    await carregarAtivos();
    selecionarAtivo(ativoId);
  }
}

async function abrirModalAtivo(){
  if(!SAT.cats.length) SAT.cats=await api('GET','/ativos-categorias/')||[];
  $('ativo-id').value=''; $('ativo-nome').value=''; $('ativo-desc').value='';
  $('modal-ativo-title').textContent='Novo ativo';
  $('ativo-cat-sel').innerHTML=SAT.cats.map(c=>`<option value="${c.id}">${esc(c.nome)}</option>`).join('');
  await carregarGruposModalAtivo();
  $('modal-ativo').style.display='flex';
}

async function carregarGruposModalAtivo(){
  const catId=$('ativo-cat-sel').value;
  const grps=await api('GET',catId?`/ativos-categorias/grupos/?categoria_id=${catId}`:'/ativos-categorias/grupos/');
  $('ativo-grp-sel').innerHTML=!grps||!grps.length
    ?'<option value="">— Nenhum grupo —</option>'
    :grps.map(g=>`<option value="${g.id}">${esc(g.nome)}</option>`).join('');
}

async function editarAtivo(id){
  const a=SAT.lista.find(x=>x.id===id); if(!a) return;
  if(!SAT.cats.length) SAT.cats=await api('GET','/ativos-categorias/')||[];
  $('ativo-id').value=id; $('ativo-nome').value=a.nome; $('ativo-desc').value=a.descricao||'';
  $('modal-ativo-title').textContent='Editar ativo';
  $('ativo-cat-sel').innerHTML=SAT.cats.map(c=>
    `<option value="${c.id}" ${c.id===a.grupo.categoria_id?'selected':''}>${esc(c.nome)}</option>`).join('');
  const grps=await api('GET',`/ativos-categorias/grupos/?categoria_id=${a.grupo.categoria_id}`);
  $('ativo-grp-sel').innerHTML=(grps||[]).map(g=>
    `<option value="${g.id}" ${g.id===a.grupo_id?'selected':''}>${esc(g.nome)}</option>`).join('');
  $('modal-ativo').style.display='flex';
}

async function salvarAtivo(){
  const id=$('ativo-id').value;
  const body={nome:$('ativo-nome').value.trim(), descricao:$('ativo-desc').value.trim()||null,
    grupo_id:parseInt($('ativo-grp-sel').value)};
  if(!body.nome){toast('Nome obrigatório','error');return;}
  if(!body.grupo_id){toast('Selecione um grupo','error');return;}
  const r=id?await api('PUT',`/ativos/${id}`,body):await api('POST','/ativos/',body);
  if(r){fecharModal('modal-ativo');toast('Ativo salvo!');await carregarAtivos();if(id) selecionarAtivo(parseInt(id));}
}

async function removerAtivo(id,nome){
  if(!confirm(`Desativar "${nome}"?`)) return;
  const r=await api('DELETE',`/ativos/${id}`);
  if(r!==null){
    toast('Ativo desativado');
    if(SAT.selecionado===id){
      SAT.selecionado=null;
      $('atv-painel').innerHTML='<div class="table-wrap" style="padding:40px;text-align:center;color:var(--muted)"><div style="font-size:32px;margin-bottom:8px">◉</div><div style="font-size:14px">Selecione um ativo para ver os itens em uso</div></div>';
    }
    await carregarAtivos();
  }
}

async function reativarAtivo(id, nome){
  if(!confirm(`Reativar "${nome}"?\n\nO ativo voltará ativo e zerado — os itens que estavam atribuídos permanecem no estoque.`)) return;
  const r=await api('POST',`/ativos/${id}/reativar`);
  if(r!==null){
    toast('Ativo reativado');
    SAT.inativos=[];
    await carregarAtivos();
    carregarAtivosInativos();
  }
}

// ── Aba Inativos ──────────────────────────────────
function trocarTabAtivos(tab){
  SAT.tabAtual=tab;
  $('atv-tab-ativos')?.classList.toggle('active',tab==='ativos');
  $('atv-tab-inativos')?.classList.toggle('active',tab==='inativos');
  const pA=$('atv-pane-ativos'), pI=$('atv-pane-inativos');
  if(pA) pA.style.display=tab==='ativos'?'':'none';
  if(pI) pI.style.display=tab==='inativos'?'':'none';
  if(tab==='inativos'&&!SAT.inativos.length) carregarAtivosInativos();
}

async function carregarAtivosInativos(){
  const lista=await api('GET','/ativos/inativos');
  if(!lista) return;
  SAT.inativos=lista;
  renderizarAtivosInativos(lista);
}

function renderizarAtivosInativos(lista){
  const container=$('atv-lista-inativos');
  if(!lista.length){
    container.innerHTML='<div class="empty" style="background:var(--surface);border-radius:var(--radius);padding:40px"><span>◉</span>Nenhum ativo inativo</div>';
    return;
  }
  container.innerHTML=lista.map(a=>`
    <div class="ativo-card" style="opacity:.75">
      <div style="display:flex;justify-content:space-between;align-items:start">
        <div>
          <div class="ativo-nome">${esc(a.nome)}</div>
          <div class="ativo-sub">${a.grupo.categoria.nome} / ${a.grupo.nome}</div>
          ${a.descricao?`<div class="ativo-sub">${esc(a.descricao)}</div>`:''}
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <span class="badge" style="background:#9E9E9E;color:#fff">Inativo</span>
          <button class="btn btn-sm editor-only" style="background:var(--green);color:#fff;border:none" onclick="reativarAtivo(${a.id},'${a.nome.replace(/'/g,"\\'")}')">Reativar</button>
        </div>
      </div>
    </div>`).join('');
}

// ── Modal Atribuir Material ────────────────────────
async function abrirModalAtribuir(ativoId, ativoNome){
  $('atribuir-ativo-id').value=ativoId;
  $('modal-atribuir-title').textContent=`Atribuir material → ${ativoNome}`;
  $('atribuir-estoque-info').style.display='none';
  $('atribuir-obs').value='';
  $('atribuir-unidade').innerHTML='<option value="">Selecione o material primeiro…</option>';

  if(!S.categorias.length) S.categorias=await api('GET','/categorias/')||[];
  $('atribuir-cat').innerHTML='<option value="">Selecione…</option>'+
    S.categorias.map(c=>`<option value="${c.id}">${esc(c.nome)}</option>`).join('');
  $('atribuir-grp').innerHTML='<option value="">Selecione…</option>';
  $('atribuir-mat').innerHTML='<option value="">Selecione…</option>';
  $('modal-atribuir').style.display='flex';

  // Searchable selects
  ['atribuir-cat','atribuir-grp','atribuir-mat','atribuir-unidade'].forEach(tornarPesquisavel);
}

async function carregarGruposAtribuir(){
  const catId=$('atribuir-cat').value;
  $('atribuir-grp').innerHTML='<option value="">Selecione…</option>';
  $('atribuir-mat').innerHTML='<option value="">Selecione…</option>';
  $('atribuir-estoque-info').style.display='none';
  if(!catId) return;
  const grps=await api('GET',`/grupos/?categoria_id=${catId}`);
  $('atribuir-grp').innerHTML='<option value="">Selecione…</option>'+
    (grps||[]).map(g=>`<option value="${g.id}">${esc(g.nome)}</option>`).join('');
}

async function carregarMateriaisAtribuir(){
  const grpId=$('atribuir-grp').value;
  $('atribuir-mat').innerHTML='<option value="">Selecione…</option>';
  $('atribuir-estoque-info').style.display='none';
  if(!grpId) return;
  const mats=await api('GET',`/materiais/?grupo_id=${grpId}`);
  $('atribuir-mat').innerHTML='<option value="">Selecione…</option>'+
    (mats||[]).map(m=>`<option value="${m.id}" data-qtd="${m.quantidade}" data-un="${m.unidade}">${esc(m.nome)}</option>`).join('');
}

async function carregarUnidadesAtribuir(){
  const sel=$('atribuir-mat');
  const opt=sel.options[sel.selectedIndex];
  $('atribuir-unidade').innerHTML='<option value="">Carregando…</option>';
  $('atribuir-estoque-info').style.display='none';
  if(!opt||!opt.value){
    $('atribuir-unidade').innerHTML='<option value="">Selecione o material primeiro…</option>';
    return;
  }
  const matId=opt.value;
  $('atribuir-estoque-info').textContent=`Estoque disponível: ${opt.dataset.qtd} ${opt.dataset.un}`;
  $('atribuir-estoque-info').style.display='block';
  const unidades=await api('GET',`/patrimonio/${matId}/unidades`);
  const disponiveis=(unidades||[]).filter(u=>u.tag!=='atribuido'&&u.status==='ativo');
  if(!disponiveis.length){
    $('atribuir-unidade').innerHTML='<option value="">Nenhuma unidade disponível</option>';
    return;
  }
  $('atribuir-unidade').innerHTML='<option value="">Selecione a unidade…</option>'+
    disponiveis.map(u=>`<option value="${u.id}">${u.codigo||'Sem código #'+u.id} — ${u.tag||'novo'}</option>`).join('');
}

async function confirmarAtribuir(){
  const ativoId=parseInt($('atribuir-ativo-id').value);
  const matId=parseInt($('atribuir-mat').value);
  const unidadeId=parseInt($('atribuir-unidade').value);
  const obs=$('atribuir-obs').value.trim();
  if(!matId){toast('Selecione um material','error');return;}
  if(!unidadeId){toast('Selecione uma unidade','error');return;}
  const r=await api('POST',`/ativos/${ativoId}/atribuir`,{material_id:matId,unidade_id:unidadeId,observacao:obs||null});
  if(r){
    fecharModal('modal-atribuir');
    toast('Material atribuído com sucesso!');
    await carregarAtivos();
    selecionarAtivo(ativoId);
  }
}

// ═══════════════════════════════════════════════════
// Adicionar Material (entrada para material existente)
// ═══════════════════════════════════════════════════
async function abrirModalAdicionarMaterial(){
  if(!S.categorias.length) S.categorias=await api('GET','/categorias/')||[];
  $('add-mat-id').value='';
  $('add-mat-info').style.display='none';
  $('add-mat-qtd').value=1; $('add-mat-obs').value='';
  $('add-mat-valor').value='';
  $('add-mat-cat').innerHTML=S.categorias.map(c=>`<option value="${c.id}">${esc(c.nome)}</option>`).join('');
  await carregarGruposAddMat();
  $('modal-add-mat').style.display='flex';

  // Searchable selects
  ['add-mat-cat','add-mat-grp','add-mat-sel'].forEach(tornarPesquisavel);
}

async function carregarGruposAddMat(){
  const catId=$('add-mat-cat').value;
  $('add-mat-grp').innerHTML='<option value="">Selecione o grupo…</option>';
  $('add-mat-sel').innerHTML='<option value="">Selecione o material…</option>';
  $('add-mat-info').style.display='none';
  if(!catId) return;
  const grps=await api('GET',`/grupos/?categoria_id=${catId}`);
  $('add-mat-grp').innerHTML='<option value="">Selecione o grupo…</option>'+
    (grps||[]).map(g=>`<option value="${g.id}">${esc(g.nome)}</option>`).join('');
}

async function carregarMateriaisAddMat(){
  const grpId=$('add-mat-grp').value;
  $('add-mat-sel').innerHTML='<option value="">Selecione o material…</option>';
  $('add-mat-info').style.display='none';
  if(!grpId) return;
  const mats=await api('GET',`/materiais/?grupo_id=${grpId}`);
  $('add-mat-sel').innerHTML='<option value="">Selecione o material…</option>'+
    (mats||[]).map(m=>`<option value="${m.id}" data-qtd="${m.quantidade}" data-un="${m.unidade}" data-pat="${m.usa_patrimonio}" data-val="${m.valor_unitario??''}">${esc(m.nome)}</option>`).join('');
}

function preencherCamposAddMat(){
  const sel=$('add-mat-sel');
  const opt=sel.options[sel.selectedIndex];
  if(!opt||!opt.value){$('add-mat-info').style.display='none';return;}
  $('add-mat-id').value=opt.value;
  $('add-mat-un').value=opt.dataset.un||'un';
  $('add-mat-valor').value=opt.dataset.val||'';
  $('add-mat-info').textContent=`Estoque atual: ${opt.dataset.qtd} ${opt.dataset.un}`;
  $('add-mat-info').style.display='block';
}

async function confirmarAdicionarMaterial(){
  const id=$('add-mat-id').value;
  if(!id){toast('Selecione um material','error');return;}
  const qtd=parseFloat($('add-mat-qtd').value);
  if(!qtd||qtd<=0){toast('Quantidade inválida','error');return;}
  const valorRaw=$('add-mat-valor').value;
  const body={
    quantidade:qtd,
    valor_unitario:valorRaw!==''?parseFloat(valorRaw):null,
    observacao:$('add-mat-obs').value.trim()||null,
  };
  const r=await api('POST',`/materiais/${id}/entrada`,body);
  if(r){fecharModal('modal-add-mat');toast('Material adicionado ao estoque!');carregarMateriais();}
}

// ═══════════════════════════════════════════════════
// Notificações
// ═══════════════════════════════════════════════════
let _notifAbaAtiva='retiradas';

async function carregarNotificacoes(){
  _notifAbaAtiva='retiradas';
  trocarAbaNotif('retiradas');
  // Carregar todos os emails e templates
  const [emails, tpls]=await Promise.all([
    api('GET','/notificacoes/emails'),
    api('GET','/notificacoes/templates'),
  ]);
  if(!emails||!tpls) return;

  // Preencher listas de emails
  ['retirada','entrada','alerta','requerimento','requerimento_decisao','solicitacao','solicitacao_decisao'].forEach(tipo=>{
    const lista=emails.filter(e=>e.tipo===tipo);
    _renderizarEmailsNotif(tipo, lista);
  });

  // Preencher templates
  tpls.forEach(t=>{
    const tipoMap={retirada:'retirada',entrada:'entrada',alerta:'alerta',requerimento:'requerimento',requerimento_decisao:'requerimento_decisao'};
    const k=tipoMap[t.tipo]; if(!k) return;
    const assuntoEl=$(`notif-tpl-${k}-assunto`);
    const corpoEl=$(`notif-tpl-${k}-corpo`);
    if(assuntoEl) assuntoEl.value=t.assunto;
    if(corpoEl)   corpoEl.value=t.corpo;
  });
}

function _renderizarEmailsNotif(tipo, lista){
  const container=$(`notif-list-${tipo}`);
  if(!container) return;
  if(!lista.length){
    container.innerHTML='<div style="font-size:13px;color:var(--muted);padding:8px 0">Nenhum e-mail cadastrado.</div>';
    return;
  }
  container.innerHTML=lista.map(e=>`
    <div style="display:flex;align-items:center;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--border)">
      <div>
        <span style="font-size:13px">${e.email}</span>
        ${tipo==='alerta'&&e.intervalo_dias?`<span style="font-size:11px;color:var(--muted);margin-left:6px">a cada ${e.intervalo_dias}d</span>`:''}
      </div>
      <button class="btn btn-danger btn-sm" onclick="removerEmailNotif(${e.id},'${tipo}')">✕</button>
    </div>`).join('');
}

async function adicionarEmailNotif(tipo){
  const email=$(`notif-email-${tipo}`).value.trim();
  if(!email){toast('Informe um e-mail','error');return;}
  const intEl=$(`notif-int-${tipo}`);
  const intervalo_dias=intEl&&intEl.value?parseInt(intEl.value)||null:null;
  const r=await api('POST','/notificacoes/emails',{email,tipo,intervalo_dias});
  if(r){
    toast('E-mail adicionado!');
    $(`notif-email-${tipo}`).value='';
    if(intEl) intEl.value='';
    const emails=await api('GET',`/notificacoes/emails?tipo=${tipo}`);
    _renderizarEmailsNotif(tipo, emails||[]);
  }
}

async function removerEmailNotif(id, tipo){
  const r=await api('DELETE',`/notificacoes/emails/${id}`);
  if(r!==null){
    toast('E-mail removido');
    const emails=await api('GET',`/notificacoes/emails?tipo=${tipo}`);
    _renderizarEmailsNotif(tipo, emails||[]);
  }
}

async function enviarAlertasAgora(){
  const r=await api('POST','/notificacoes/alertas/enviar');
  if(r) toast(r.mensagem||(r.alertas_enviados+' alerta(s) enviado(s)'), r.ok===false?'error':'success');
}

async function salvarTemplateNotif(tipo){
  const assunto=$(`notif-tpl-${tipo}-assunto`).value.trim();
  const corpo=$(`notif-tpl-${tipo}-corpo`).value.trim();
  if(!assunto||!corpo){toast('Preencha assunto e corpo','error');return;}
  const r=await api('PUT',`/notificacoes/templates/${tipo}`,{tipo,assunto,corpo});
  if(r) toast('Template salvo!');
}

function trocarAbaNotif(aba){
  _notifAbaAtiva=aba;
  const section=$('page-notificacoes');
  section?.querySelectorAll('.inner-tab').forEach((el,i)=>{
    const abas=['retiradas','entradas','alertas','requerimento','solicitacao','smtp'];
    el.classList.toggle('active', abas[i]===aba);
  });
  section?.querySelectorAll('.inner-tab-pane').forEach(el=>el.classList.remove('active'));
  $(`notif-pane-${aba}`)?.classList.add('active');
  if(aba==='smtp') carregarSmtp();
  if(aba==='requerimento') _carregarEmailsRequerimento();
  if(aba==='solicitacao')  _carregarEmailsSolicitacao();
}

async function _carregarEmailsRequerimento(){
  const [emails, tpls] = await Promise.all([
    api('GET', '/notificacoes/emails'),
    api('GET', '/notificacoes/templates'),
  ]);
  _renderizarEmailsNotif('requerimento',          (emails||[]).filter(e=>e.tipo==='requerimento'));
  _renderizarEmailsNotif('requerimento_decisao',  (emails||[]).filter(e=>e.tipo==='requerimento_decisao'));
  if(!tpls) return;
  ['requerimento','requerimento_decisao'].forEach(tipo=>{
    const tpl = tpls.find(t=>t.tipo===tipo);
    if(!tpl) return;
    const k = tipo.replace('_decisao','-decisao');
    const assuntoEl = $(`notif-tpl-${tipo}-assunto`);
    const corpoEl   = $(`notif-tpl-${tipo}-corpo`);
    if(assuntoEl) assuntoEl.value = tpl.assunto;
    if(corpoEl)   corpoEl.value   = tpl.corpo;
  });
}

async function _carregarEmailsSolicitacao(){
  const emails = await api('GET', '/notificacoes/emails');
  _renderizarEmailsNotif('solicitacao',         (emails||[]).filter(e=>e.tipo==='solicitacao'));
  _renderizarEmailsNotif('solicitacao_decisao', (emails||[]).filter(e=>e.tipo==='solicitacao_decisao'));
}

async function carregarSmtp(){
  const cfg=await api('GET','/notificacoes/smtp');
  if(!cfg) return;
  $('smtp-host').value=cfg.host||'';
  $('smtp-porta').value=cfg.porta||587;
  $('smtp-usuario').value=cfg.usuario||'';
  $('smtp-senha').value=cfg.senha||'';
  $('smtp-remetente').value=cfg.remetente||'';
  $('smtp-tls').checked=cfg.tls!==false;
  $('smtp-ssl').checked=!!cfg.ssl;
}

async function salvarSmtp(){
  const body={
    host:     $('smtp-host').value.trim(),
    porta:    parseInt($('smtp-porta').value)||587,
    usuario:  $('smtp-usuario').value.trim(),
    senha:    $('smtp-senha').value,
    remetente:$('smtp-remetente').value.trim(),
    tls:      $('smtp-tls').checked,
    ssl:      $('smtp-ssl').checked,
  };
  if(!body.host){toast('Informe o host SMTP','error');return;}
  const r=await api('PUT','/notificacoes/smtp',body);
  if(r) toast('Configuração SMTP salva!');
}

async function testarSmtp(){
  const btn=event.target;
  btn.disabled=true; btn.textContent='Enviando…';
  try{
    const r=await api('POST','/notificacoes/smtp/testar');
    if(r) toast(`E-mail de teste enviado para ${r.enviado_para}`);
  } finally{
    btn.disabled=false; btn.textContent='Testar envio';
  }
}

// ── Motivos personalizados ─────────────────────────
async function abrirModalMotivo(){
  $('motivo-novo-nome').value='';
  $('modal-motivo').style.display='flex';
  await _carregarListaMotivos();
}

async function _carregarListaMotivos(){
  const dados=await api('GET','/motivos/');
  if(!dados) return;
  const container=$('motivo-lista');
  const padrao=(dados.padrao||[]).map(m=>`
    <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border)">
      <span style="font-size:13px">${esc(m.label)}</span>
      <span style="font-size:11px;color:var(--muted);background:#ECEFF1;padding:2px 6px;border-radius:4px">Padrão</span>
    </div>`).join('');
  const custom=(dados.customizados||[]).map(m=>`
    <div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
      <span style="font-size:13px">${esc(m.nome)}</span>
      <button class="btn btn-danger btn-sm" onclick="removerMotivoCustom(${m.id})">✕</button>
    </div>`).join('');
  container.innerHTML=(padrao+custom)||'<p style="color:var(--muted);font-size:13px;padding:8px 0">Nenhum motivo cadastrado.</p>';
  _carregarOpcoesMotivo(dados);
}

async function salvarMotivoCustom(){
  const nome=$('motivo-novo-nome').value.trim();
  if(!nome){toast('Informe o nome do motivo','error');return;}
  const r=await api('POST','/motivos/',{nome});
  if(r){$('motivo-novo-nome').value='';toast('Motivo criado!');await _carregarListaMotivos();}
}

async function removerMotivoCustom(id){
  if(!confirm('Remover este motivo?')) return;
  const r=await api('DELETE',`/motivos/${id}`);
  if(r!==null){toast('Motivo removido');await _carregarListaMotivos();}
}

// ═══════════════════════════════════════════════════
// Requerimentos de Compra
// ═══════════════════════════════════════════════════
let _reqDetalheId  = null;
let _podeCriarReq  = false;
let _podeAprovarReq = false;

function _atualizarBadgeReq(listaReq, listaSol){
  const nReq = (listaReq||[]).filter(r=>r.status==='aguardando').length;
  const nSol = (listaSol||[]).filter(s=>s.status==='aguardando').length;
  const total = nReq + nSol;
  const el = $('nav-badge-req');
  if(!el) return;
  if(total > 0){ el.textContent = total > 99 ? '99+' : total; el.style.display=''; }
  else { el.style.display='none'; }
}

async function carregarRequerimentos(){
  const isAdmin = S.grupo === 'admin' || S.grupo === 'mestre';
  if(isAdmin){
    _podeCriarReq = _podeAprovarReq = true;
  } else {
    const emails = await api('GET', '/notificacoes/emails');
    const emailsAtivos = (emails||[]).filter(e=>e.ativo);
    _podeCriarReq   = emailsAtivos.some(e=>e.tipo==='requerimento'         && e.email===S.email);
    _podeAprovarReq = emailsAtivos.some(e=>e.tipo==='requerimento_decisao' && e.email===S.email);
  }
  // Badge sempre atualizado (requerimentos + solicitações)
  const [listaReq, listaSol] = await Promise.all([
    api('GET', '/requerimentos/'),
    api('GET', '/solicitacoes/'),
  ]);
  if(!listaReq) return;
  _atualizarBadgeReq(listaReq, listaSol);

  // Exibir botões corretos conforme sub-aba ativa
  const btnReq = $('btn-novo-req');
  const btnSol = $('btn-nova-sol');
  if(_reqTabAtual === 'req'){
    if(btnReq) btnReq.style.display = _podeCriarReq ? '' : 'none';
    if(btnSol) btnSol.style.display = 'none';
    _renderRequerimentos(listaReq);
  } else {
    if(btnReq) btnReq.style.display = 'none';
    if(btnSol) btnSol.style.display = S.grupo !== 'viewer' ? '' : 'none';
    carregarSolicitacoes();
  }
}

function _badgeReq(status){
  if(status === 'aprovado')   return '<span class="badge badge-ok">Aprovado</span>';
  if(status === 'rejeitado')  return '<span class="badge badge-alert" style="background:#FDECEA;color:var(--danger)">Rejeitado</span>';
  return '<span class="badge" style="background:#FFF3CD;color:#856404;font-weight:600">Aguardando</span>';
}

function _renderRequerimentos(lista){
  // Badge já foi atualizado por carregarRequerimentos com ambas as listas
  _atualizarBadgeReq(lista, null);
  const tbody = $('req-body');
  if(!lista.length){
    tbody.innerHTML = '<tr><td colspan="6"><div class="empty"><span>📋</span>Nenhum requerimento cadastrado</div></td></tr>';
    return;
  }
  tbody.innerHTML = lista.map(r => {
    const acoes = `
      <button class="btn btn-secondary btn-sm" onclick="verRequerimento(${r.id})">Ver</button>
      ${_podeAprovarReq && r.status === 'aguardando'
        ? `<button class="btn btn-primary btn-sm" onclick="withBtn(this,()=>_abrirDetalheEAprovar(${r.id}))">Aprovar</button>
           <button class="btn btn-danger btn-sm" onclick="withBtn(this,()=>_abrirDetalheERejeitar(${r.id}))">Rejeitar</button>`
        : ''}
      <button class="btn btn-secondary btn-sm" onclick="downloadExcelReq(${r.id})" title="Download Excel">⬇</button>`;
    return `<tr>
      <td><strong>${esc(r.titulo)}</strong></td>
      <td style="white-space:nowrap">R$ ${Number(r.total).toFixed(2)}</td>
      <td class="hide-mobile" style="font-size:12px;color:var(--muted)">${esc(r.criador_nome||'—')}</td>
      <td class="hide-mobile" style="font-size:12px;color:var(--muted)">${fmtDT(r.criado_em)}</td>
      <td>${_badgeReq(r.status)}</td>
      <td style="white-space:nowrap" onclick="event.stopPropagation()">${acoes}</td>
    </tr>`;
  }).join('');
}

function abrirNovoRequerimento(){
  $('req-titulo').value = '';
  $('req-itens-body').innerHTML = '';
  $('req-total-preview').textContent = _fmtBRL(0);
  $('req-itens-vazio').style.display = 'none';
  const fi = $('req-import-file'); if(fi) fi.value='';
  addItemReq();
  abrirModal('modal-novo-req');
}

function abrirModal(id){ $(id).style.display = 'flex'; }

function _fmtBRL(v){ return 'R$ ' + Number(v).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2}); }

function _addItemReqRow(nome='', qtd='', valor=''){
  const tbody = $('req-itens-body');
  $('req-itens-vazio').style.display = 'none';
  const inp = 'padding:6px 8px;border:1.5px solid var(--border);border-radius:8px;font-size:13px;width:100%';
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td style="padding:3px 4px 3px 0">
      <input type="text" placeholder="Nome do item" value="${esc(nome)}" style="${inp}"/>
    </td>
    <td style="padding:3px 4px;width:90px">
      <input type="number" min="0.01" step="0.01" placeholder="1" value="${qtd}"
        style="${inp};text-align:right" oninput="_atualizarTotalReq(this)"/>
    </td>
    <td style="padding:3px 4px;width:120px">
      <input type="number" min="0.01" step="0.01" placeholder="0,00" value="${valor}"
        style="${inp};text-align:right" oninput="_atualizarTotalReq(this)"/>
    </td>
    <td style="padding:3px 4px;width:110px;text-align:right;font-size:13px;font-weight:600;color:var(--green)" class="req-subtotal">—</td>
    <td style="padding:3px 0 3px 4px;text-align:center">
      <button class="btn btn-danger btn-sm" style="padding:4px 8px"
        onclick="this.closest('tr').remove();_atualizarTotalReq()">✕</button>
    </td>`;
  tbody.appendChild(tr);
  _atualizarTotalReq();
}

function addItemReq(){ _addItemReqRow(); }

function _atualizarTotalReq(){
  let total = 0;
  document.querySelectorAll('#req-itens-body tr').forEach(tr => {
    const inputs = tr.querySelectorAll('input[type="number"]');
    const qtd  = parseFloat(inputs[0]?.value) || 0;
    const val  = parseFloat(inputs[1]?.value) || 0;
    const sub  = qtd * val;
    const celSub = tr.querySelector('.req-subtotal');
    if(celSub) celSub.textContent = sub > 0 ? _fmtBRL(sub) : '—';
    total += sub;
  });
  $('req-total-preview').textContent = _fmtBRL(total);
}

async function criarRequerimento(){
  const titulo = $('req-titulo').value.trim();
  if(!titulo){ toast('Título obrigatório', 'error'); return; }

  const rows = document.querySelectorAll('#req-itens-body tr');
  if(!rows.length){ toast('Adicione ao menos um item', 'error'); return; }

  const itens = [];
  let valido = true;
  rows.forEach(tr => {
    const inputs = tr.querySelectorAll('input[type="text"],input[type="number"]');
    const nome       = inputs[0]?.value.trim();
    const quantidade = parseFloat(inputs[1]?.value) || 0;
    const valor      = parseFloat(inputs[2]?.value) || 0;
    if(!nome){ valido = false; return; }
    if(quantidade <= 0){ valido = false; toast('Quantidade deve ser maior que zero em todos os itens','error'); return; }
    if(valor <= 0){ valido = false; toast('Valor deve ser maior que zero em todos os itens','error'); return; }
    itens.push({ nome, quantidade, valor });
  });

  if(!valido){ toast('Preencha todos os campos dos itens corretamente', 'error'); return; }
  if(!itens.length){ toast('Adicione ao menos um item', 'error'); return; }

  const r = await api('POST', '/requerimentos/', { titulo, itens });
  if(r){
    fecharModal('modal-novo-req');
    toast('Requerimento criado!');
    carregarRequerimentos();
  }
}

async function verRequerimento(id){
  _reqDetalheId = id;
  const r = await api('GET', `/requerimentos/${id}`);
  if(!r) return;

  $('det-req-titulo').textContent     = r.titulo;
  $('det-req-badge').innerHTML        = _badgeReq(r.status);
  $('det-req-criador').textContent    = 'Por: ' + (r.criador_nome || '—');
  $('det-req-data').textContent       = fmtDT(r.criado_em);
  $('det-req-total').textContent      = _fmtBRL(r.total);

  // Itens
  $('det-req-itens').innerHTML = (r.itens||[]).map(it => {
    const qtd = it.quantidade || 1;
    const sub = qtd * it.valor;
    return `<tr>
      <td style="padding:8px 10px;border-bottom:1px solid var(--border)">${esc(it.nome)}</td>
      <td style="padding:8px 10px;border-bottom:1px solid var(--border);text-align:right;white-space:nowrap">${Number(qtd).toLocaleString('pt-BR',{maximumFractionDigits:2})}</td>
      <td style="padding:8px 10px;border-bottom:1px solid var(--border);text-align:right;white-space:nowrap">${_fmtBRL(it.valor)}</td>
      <td style="padding:8px 10px;border-bottom:1px solid var(--border);text-align:right;white-space:nowrap;font-weight:600">${_fmtBRL(sub)}</td>
    </tr>`;
  }).join('');

  // Observação de rejeição
  const obsWrap = $('det-req-obs-wrap');
  if(r.status === 'rejeitado' && r.observacao){
    $('det-req-obs').textContent = r.observacao;
    obsWrap.style.display = 'block';
  } else {
    obsWrap.style.display = 'none';
  }

  // Área de aprovação/rejeição
  const acaoWrap = $('det-req-acao-wrap');
  if(_podeAprovarReq && r.status === 'aguardando'){
    $('det-req-obs-input').value = '';
    acaoWrap.style.display = 'block';
  } else {
    acaoWrap.style.display = 'none';
  }

  abrirModal('modal-detalhe-req');
}

// Atalhos internos para abrir detalhe já na ação
async function _abrirDetalheEAprovar(id){ await verRequerimento(id); }
async function _abrirDetalheERejeitar(id){ await verRequerimento(id); }

async function aprovarRequerimento(id){
  const obs = $('det-req-obs-input')?.value.trim() || '';
  const body = obs ? { observacao: obs } : {};
  const r = await api('POST', `/requerimentos/${id}/aprovar`, body);
  if(r){
    fecharModal('modal-detalhe-req');
    toast('Requerimento aprovado!');
    carregarRequerimentos();
  }
}

async function rejeitarRequerimento(id){
  const obs = $('det-req-obs-input')?.value.trim();
  if(!obs){ toast('Informe o motivo da rejeição', 'error'); return; }
  const r = await api('POST', `/requerimentos/${id}/rejeitar`, { observacao: obs });
  if(r){
    fecharModal('modal-detalhe-req');
    toast('Requerimento rejeitado');
    carregarRequerimentos();
  }
}

function _baixarBlob(url, nomeArquivo){
  fetch(url, { headers: { Authorization: `Bearer ${S.token}` } })
    .then(r => { if(!r.ok) throw new Error(); return r.blob(); })
    .then(blob => {
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = nomeArquivo;
      link.click();
      URL.revokeObjectURL(link.href);
    }).catch(() => toast('Erro ao baixar arquivo', 'error'));
}

function downloadExcelReq(id){ _baixarBlob(`/api/requerimentos/${id}/excel`, `requerimento_${id}.xlsx`); }

function baixarModeloReq(){ _baixarBlob('/api/requerimentos/modelo-excel', 'modelo_requerimento.xlsx'); }

async function importarExcelReq(input){
  const file = input.files[0];
  if(!file) return;
  input.value = '';   // permite reimportar o mesmo arquivo

  const titulo = $('req-titulo').value.trim();
  if(!titulo){ toast('Preencha o título antes de importar', 'error'); return; }

  const fd = new FormData();
  fd.append('arquivo', file);

  toast('Importando planilha…');
  try {
    const resp = await fetch(`/api/requerimentos/importar-excel?titulo=${encodeURIComponent(titulo)}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${S.token}` },
      body: fd,
    });
    if(!resp.ok){
      const err = await resp.json().catch(()=>({}));
      toast(err.detail || 'Erro ao importar planilha', 'error');
      return;
    }
    const req = await resp.json();
    fecharModal('modal-novo-req');
    toast('Requerimento importado com sucesso!');
    carregarRequerimentos();
  } catch {
    toast('Erro ao importar planilha', 'error');
  }
}

// ═══════════════════════════════════════════════════
// Relatórios
// ═══════════════════════════════════════════════════
function carregarRelatorios(){
  const agora = new Date();
  const sel = $('rel-nfe-mes');
  const selAno = $('rel-nfe-ano');
  if(sel) sel.value = String(agora.getMonth()+1);
  if(selAno) selAno.value = String(agora.getFullYear());
  $('rel-nfe-resultado').innerHTML = '';
}

async function carregarRelatorioNfe(){
  const mes = parseInt($('rel-nfe-mes').value);
  const ano = parseInt($('rel-nfe-ano').value);
  if(!mes || !ano){ toast('Selecione mês e ano','error'); return; }
  const resultado = $('rel-nfe-resultado');
  resultado.innerHTML = '<div style="padding:16px;color:var(--muted)">Carregando…</div>';
  const data = await api('GET', `/relatorios/entradas-nfe?mes=${mes}&ano=${ano}`);
  if(!data){ resultado.innerHTML=''; return; }
  if(!data.length){
    resultado.innerHTML = '<div style="padding:16px;color:var(--muted)">Nenhuma entrada via NF-e no período.</div>';
    return;
  }
  const totalGeral = data.reduce((acc,r)=>acc+r.subtotal,0);
  resultado.innerHTML = `
    <div class="table-scroll" style="margin-top:16px">
      <table>
        <thead><tr>
          <th>NF-e</th><th>Material</th><th>Categoria</th>
          <th style="text-align:right">Qtd</th>
          <th style="text-align:right">Valor Unit.</th>
          <th style="text-align:right">Subtotal</th>
          <th>Data</th>
        </tr></thead>
        <tbody>
          ${data.map(r=>`<tr>
            <td style="font-size:12px">${esc(r.nf_numero||'—')}</td>
            <td>${esc(r.material_nome)}</td>
            <td style="font-size:12px;color:var(--muted)">${esc(r.categoria_nome)}</td>
            <td style="text-align:right">${Number(r.quantidade).toLocaleString('pt-BR',{maximumFractionDigits:2})} ${esc(r.unidade)}</td>
            <td style="text-align:right">${r.valor_unitario>0?'R$ '+r.valor_unitario.toFixed(2):'—'}</td>
            <td style="text-align:right;font-weight:600">${r.subtotal>0?'R$ '+r.subtotal.toFixed(2):'—'}</td>
            <td style="font-size:12px;color:var(--muted)">${fmtDT(r.criado_em)}</td>
          </tr>`).join('')}
        </tbody>
        <tfoot><tr style="background:var(--bg)">
          <td colspan="5" style="padding:10px 14px;font-weight:700;font-size:13px">Total do período</td>
          <td style="padding:10px 14px;text-align:right;font-weight:700;font-size:13px">R$ ${totalGeral.toFixed(2)}</td>
          <td></td>
        </tr></tfoot>
      </table>
    </div>`;
}

// ═══════════════════════════════════════════════════
// Solicitações de Estoque
// ═══════════════════════════════════════════════════
let _reqTabAtual = 'req';   // 'req' | 'sol'

function switchReqTab(tab){
  _reqTabAtual = tab;
  ['req','sol'].forEach(t=>{
    const btn   = $('tab-btn-'+t);
    const panel = $('tab-panel-'+t);
    const isActive = t === tab;
    if(btn)   btn.classList.toggle('active', isActive);
    if(panel) panel.style.display = isActive ? '' : 'none';
  });
  // Mostra o botão de ação correto
  const btnReq = $('btn-novo-req');
  const btnSol = $('btn-nova-sol');
  if(tab === 'req'){
    if(btnReq) btnReq.style.display = _podeCriarReq ? '' : 'none';
    if(btnSol) btnSol.style.display = 'none';
    carregarRequerimentos();
  } else {
    if(btnReq) btnReq.style.display = 'none';
    if(btnSol) btnSol.style.display = '';
    carregarSolicitacoes();
  }
}

async function carregarSolicitacoes(){
  const isAdmin = S.grupo === 'admin' || S.grupo === 'mestre';
  if(S.grupo === 'viewer'){ return; }
  const lista = await api('GET', '/solicitacoes/');
  if(!lista) return;
  const tbody = $('sol-body');
  if(!tbody) return;
  if(!lista.length){
    tbody.innerHTML = '<tr><td colspan="7"><div class="empty"><span>📦</span>Nenhuma solicitação cadastrada</div></td></tr>';
    return;
  }
  tbody.innerHTML = lista.map(s=>{
    const badgeCls = s.status === 'aprovado' ? 'badge-ok' : s.status === 'rejeitado' ? 'badge-alert' : '';
    const badgeSty = s.status === 'rejeitado' ? 'style="background:#FDECEA;color:var(--danger)"' : '';
    const badgeTxt = s.status === 'aguardando' ? '<span class="badge" style="background:#FFF3CD;color:#856404;font-weight:600">Aguardando</span>'
                   : s.status === 'aprovado'   ? '<span class="badge badge-ok">Aprovado</span>'
                   :                             '<span class="badge badge-alert" style="background:#FDECEA;color:var(--danger)">Rejeitado</span>';
    const acoes = isAdmin && s.status === 'aguardando'
      ? `<button class="btn btn-primary btn-sm" onclick="aprovarSolicitacao(${s.id})">Aprovar</button>
         <button class="btn btn-danger btn-sm" onclick="rejeitarSolicitacao(${s.id})">Rejeitar</button>`
      : s.observacao ? `<span style="font-size:12px;color:var(--muted)" title="${esc(s.observacao)}">obs.</span>` : '—';
    return `<tr>
      <td><strong>${esc(s.material_nome)}</strong></td>
      <td style="font-size:12px;color:var(--muted)">${esc(s.ativo_nome||'—')}</td>
      <td style="text-align:right">${Number(s.quantidade).toLocaleString('pt-BR',{maximumFractionDigits:2})}</td>
      <td style="font-size:12px;max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(s.motivo)}</td>
      <td class="hide-mobile" style="font-size:12px;color:var(--muted)">${esc(s.criador_nome||'—')}</td>
      <td>${badgeTxt}</td>
      <td style="white-space:nowrap" onclick="event.stopPropagation()">${acoes}</td>
    </tr>`;
  }).join('');
}

async function abrirNovaSolicitacao(){
  if(!S.categorias.length) S.categorias = await api('GET', '/categorias/') || [];
  const ativos = await api('GET', '/ativos/') || [];

  $('sol-cat').innerHTML = '<option value="">Selecione…</option>'
    + S.categorias.map(c=>`<option value="${c.id}">${esc(c.nome)}</option>`).join('');
  $('sol-grp').innerHTML       = '<option value="">Selecione…</option>';
  $('sol-material-id').innerHTML = '<option value="">Selecione…</option>';
  $('sol-unidade-id').innerHTML  = '<option value="">Selecione o material primeiro…</option>';
  $('sol-ativo-id').innerHTML = '<option value="">-- Nenhum / Sem ativo --</option>'
    + ativos.filter(a=>a.ativo).map(a=>`<option value="${a.id}">${esc(a.nome)}</option>`).join('');

  $('sol-quantidade').value      = '1';
  $('sol-motivo').value          = '';
  $('sol-quantidade-wrap').style.display = 'none';
  $('sol-unidade-wrap').style.display    = 'none';
  abrirModal('modal-nova-sol');

  // Searchable selects — aplicar após o modal abrir e os selects serem populados
  ['sol-cat','sol-grp','sol-material-id','sol-unidade-id','sol-ativo-id'].forEach(tornarPesquisavel);
}

async function solCarregarGrupos(){
  const catId = $('sol-cat').value;
  $('sol-grp').innerHTML         = '<option value="">Selecione…</option>';
  $('sol-material-id').innerHTML = '<option value="">Selecione…</option>';
  $('sol-quantidade-wrap').style.display = 'none';
  $('sol-unidade-wrap').style.display    = 'none';
  if(!catId) return;
  const grps = await api('GET', `/grupos/?categoria_id=${catId}`) || [];
  $('sol-grp').innerHTML = '<option value="">Selecione…</option>'
    + grps.map(g=>`<option value="${g.id}">${esc(g.nome)}</option>`).join('');
}

async function solCarregarMateriais(){
  const grpId = $('sol-grp').value;
  $('sol-material-id').innerHTML = '<option value="">Selecione…</option>';
  $('sol-quantidade-wrap').style.display = 'none';
  $('sol-unidade-wrap').style.display    = 'none';
  if(!grpId) return;
  const mats = await api('GET', `/materiais/?grupo_id=${grpId}`) || [];
  const disponiveis = mats.filter(m=>m.ativo && m.quantidade > 0);
  $('sol-material-id').innerHTML = '<option value="">Selecione…</option>'
    + disponiveis.map(m=>
        `<option value="${m.id}" data-pat="${m.usa_patrimonio?'1':'0'}" data-un="${esc(m.unidade)}">`
        +`${esc(m.nome)} (${Number(m.quantidade).toLocaleString('pt-BR',{maximumFractionDigits:0})} ${esc(m.unidade)})</option>`
      ).join('');
}

async function solCarregarUnidades(){
  const sel = $('sol-material-id');
  const opt = sel.options[sel.selectedIndex];
  $('sol-quantidade-wrap').style.display = 'none';
  $('sol-unidade-wrap').style.display    = 'none';
  if(!opt || !opt.value) return;

  const matId = opt.value;
  const isPat = opt.dataset.pat === '1';

  if(isPat){
    $('sol-unidade-wrap').style.display = '';
    $('sol-unidade-id').innerHTML = '<option value="">Carregando…</option>';
    const unidades    = await api('GET', `/patrimonio/${matId}/unidades`) || [];
    const disponiveis = unidades.filter(u=>u.status==='ativo' && u.tag!=='atribuido');
    if(!disponiveis.length){
      $('sol-unidade-id').innerHTML = '<option value="">Nenhuma unidade disponível</option>';
    } else {
      $('sol-unidade-id').innerHTML = '<option value="">Selecione a unidade…</option>'
        + disponiveis.map(u=>{
            const cod = u.codigo || 'Sem código #' + u.id;
            const tag = u.tag || 'novo';
            return `<option value="${u.id}">${esc(cod)} — ${tag}</option>`;
          }).join('');
    }
  } else {
    $('sol-quantidade-wrap').style.display = '';
    $('sol-quantidade').value = '1';
  }
}

async function criarSolicitacao(){
  const material_id = parseInt($('sol-material-id').value);
  if(!material_id){ toast('Selecione um material','error'); return; }

  const opt    = $('sol-material-id').options[$('sol-material-id').selectedIndex];
  const isPat  = opt && opt.dataset.pat === '1';
  const ativo_id_v = $('sol-ativo-id').value;
  const ativo_id   = ativo_id_v ? parseInt(ativo_id_v) : null;
  const motivo     = $('sol-motivo').value.trim();
  if(!motivo){ toast('Informe o motivo','error'); return; }

  const body = { material_id, motivo };
  if(ativo_id) body.ativo_id = ativo_id;

  if(isPat){
    const unidade_id = parseInt($('sol-unidade-id').value);
    if(!unidade_id){ toast('Selecione uma unidade','error'); return; }
    body.unidade_id = unidade_id;
    body.quantidade = 1;
  } else {
    const quantidade = parseInt($('sol-quantidade').value, 10);
    if(!quantidade || quantidade <= 0){ toast('Quantidade inválida','error'); return; }
    body.quantidade = quantidade;
  }

  const r = await api('POST', '/solicitacoes/', body);
  if(r){
    fecharModal('modal-nova-sol');
    toast('Solicitação criada!');
    carregarSolicitacoes();
  }
}

async function aprovarSolicitacao(id){
  if(!confirm('Aprovar esta solicitação? O material será debitado do estoque.')) return;
  const r = await api('POST', `/solicitacoes/${id}/aprovar`, {});
  if(r){
    const msg = r.ativo_nome
      ? `Aprovado! ${r.material_nome} atribuído a ${r.ativo_nome}`
      : `Aprovado! ${r.material_nome} retirado do estoque`;
    toast(msg);
    carregarSolicitacoes();
  }
}

async function rejeitarSolicitacao(id){
  const obs = prompt('Motivo da rejeição (obrigatório):');
  if(obs === null) return;
  if(!obs.trim()){ toast('Informe o motivo da rejeição','error'); return; }
  const r = await api('POST', `/solicitacoes/${id}/rejeitar`, { observacao: obs.trim() });
  if(r){ toast('Solicitação rejeitada'); carregarSolicitacoes(); }
}

// ═══════════════════════════════════════════════════
// Polling — sincronização entre abas/usuários
// ═══════════════════════════════════════════════════
let _paginaAtual  = 'dashboard';
let _pollState    = null;
let _pollTimer    = null;
const _POLL_MS    = 20_000;

// Quais entidades cada página monitora, e qual função recarrega
const _pollCfg = {
  dashboard:    { watch: ['materiais','movimentacoes'],              fn: ()=> carregarDashboard() },
  materiais:    { watch: ['materiais'],                              fn: ()=> carregarMateriais() },
  retiradas:    { watch: ['movimentacoes'],                          fn: ()=> carregarRetiradas() },
  requerimentos:{ watch: ['requerimentos','solicitacoes'],           fn: ()=> carregarRequerimentos() },
  ativos:       { watch: ['ativos'],                                 fn: ()=> carregarAtivos() },
};

async function _doPoll(){
  if(!S.token) return;
  const data = await api('GET', '/poll');
  if(!data) return;

  // ── Controle de versão ──────────────────────────────────────
  if(_pollState && data.versao && data.versao !== _pollState.versao){
    _mostrarBannerAtualizacao(data.versao);
  }
  if(!_pollState){
    // Primeira chamada: apenas registra o estado inicial
    _pollState = data;
    const el = $('sidebar-versao');
    if(el) el.textContent = 'v' + data.versao;
    return;
  }

  // ── Recarrega a página atual se alguma entidade mudou ───────
  const cfg = _pollCfg[_paginaAtual];
  if(cfg){
    const mudou = cfg.watch.some(ent => data[ent] && data[ent] !== _pollState[ent]);
    if(mudou) cfg.fn();
  }

  // ── Badge de requerimentos + solicitações: atualiza sempre ──
  const reqMudou = data.requerimentos !== _pollState.requerimentos;
  const solMudou = data.solicitacoes  !== _pollState.solicitacoes;
  if((reqMudou || solMudou) && _paginaAtual !== 'requerimentos'){
    Promise.all([
      api('GET', '/requerimentos/'),
      api('GET', '/solicitacoes/'),
    ]).then(([req, sol]) => { _atualizarBadgeReq(req, sol); });
  }

  _pollState = data;
}

function _mostrarBannerAtualizacao(novaVersao){
  if($('banner-atualizacao')) return;
  const b = document.createElement('div');
  b.id = 'banner-atualizacao';
  b.innerHTML = `
    <span>Nova versão disponível (v${novaVersao}) — recarregue para atualizar.</span>
    <button onclick="location.reload()">Atualizar agora</button>`;
  document.body.prepend(b);
}

function _startPolling(){
  _doPoll();   // chamada inicial: registra estado base e exibe versão
  _pollTimer = setInterval(()=>{
    if(document.visibilityState !== 'hidden') _doPoll();
  }, _POLL_MS);
  // Poll imediato ao voltar para a aba
  document.addEventListener('visibilitychange', ()=>{
    if(document.visibilityState === 'visible') _doPoll();
  });
}


// ═══════════════════════════════════════════════════
// Auto-login
// ═══════════════════════════════════════════════════
if(S.token) iniciarApp();
