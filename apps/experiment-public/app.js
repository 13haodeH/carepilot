(() => {
  const app = document.querySelector('#app');
  const participantStorageKey = 'carepilot.customer-efficiency.public-participant.v1';
  const apiBase = String(window.CAREPILOT_API_BASE_URL || '').replace(/\/$/, '');
  const outcomeOptions = [
    ['RESOLVED', '现在可以处理并回复用户', '目前的信息已经足够。'],
    ['NEED_INFO', '先请用户补充信息', '还缺关键材料或情况。'],
    ['WAITING_REVIEW', '交给人工进一步确认', '这一步不能直接替用户决定。'],
  ];
  const suggestionChoices = [['ADOPTED', '按系统建议处理'], ['MODIFIED', '改一改再处理'], ['REJECTED', '不按这个建议处理'], ['TAKEN_OVER', '我自己接手处理']];
  const state = { session: null, active: null, notice: '', error: '', saving: false };

  const escape = (value) => String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
  const participantId = () => {
    const existing = localStorage.getItem(participantStorageKey);
    if (existing) return existing;
    const id = crypto.randomUUID(); localStorage.setItem(participantStorageKey, id); return id;
  };
  const request = async (path, body) => {
    const response = await fetch(`${apiBase}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || '页面暂时无法保存，请稍后重试。');
    return payload;
  };
  const currentTask = () => state.session.tasks.find((task) => !state.session.completed_task_ids.includes(task.task_id));
  const activeElapsedMs = () => {
    if (!state.active) return 0;
    return state.active.activeElapsedMs + (state.active.activeSinceMs ? Math.max(0, Date.now() - state.active.activeSinceMs) : 0);
  };
  const elapsed = () => Math.floor(activeElapsedMs() / 1000);
  const timerText = () => { const seconds = elapsed(); return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`; };
  const notice = () => state.error ? `<p class="notice error">${escape(state.error)}</p>` : state.notice ? `<p class="notice">${escape(state.notice)}</p>` : '';

  function renderIntro() {
    const task = currentTask(); const done = state.session.completed_task_ids.length;
    app.innerHTML = `<header class="top"><div><p class="title">模拟客服小实验</p><p class="progress">第 ${done + 1} / 6 题</p></div></header><section class="shell"><div class="card intro"><p class="eyebrow">开始前看一眼</p><h1>这是一个模拟客服处理售后问题的小实验</h1><p class="muted">你会看到 6 个模拟订单问题。请根据页面上的信息判断下一步该怎么处理；每题做完点“提交这一题”即可。不需要客服经验，也没有需要背的标准答案。</p><div class="hint"><strong>这一题你要做什么</strong><br>${task.condition === 'MANUAL' ? '自己阅读订单、物流、处理规则和图片材料，再判断怎么处理。' : '先看系统已经整理好的信息和建议，再决定是否需要查看原始信息，以及怎么处理。'}</div><button class="primary" id="start">${done > 0 && state.notice ? '下一题' : '开始做题'}</button>${notice()}</div></section>`;
    document.querySelector('#start').addEventListener('click', startTask);
  }

  function selectedClass(value, selected) { return value === selected ? ' selected' : ''; }
  function renderTask() {
    const { task, sourceActions, selectedOutcome, humanConfirmationOpened, suggestionChoice, easeRating, notes } = state.active;
    const sourceButtons = task.sources.map((source) => `<button class="choice${selectedClass(source.id, sourceActions.includes(source.id) ? source.id : '')}" data-source="${escape(source.id)}">${sourceActions.includes(source.id) ? '已查看：' : ''}${escape(source.label)}</button>`).join('');
    const sourceDetails = task.sources.filter((source) => sourceActions.includes(source.id)).map((source) => `<div class="source-content"><strong>${escape(source.label.replace('查看', ''))}</strong>${escape(source.content)}</div>`).join('');
    const packageCard = task.decision_package ? `<article class="card package"><h2>系统已经整理好的信息</h2><p class="muted">先阅读下面的内容；如果你想再确认，可以打开后面的原始信息。</p><p>${escape(task.decision_package.summary)}</p><div class="grid two fields">${task.decision_package.fields.map((field) => `<div class="field">${escape(field.label)}<span class="${field.status === '信息已准备好' ? '' : 'missing'}">${escape(field.status)}</span></div>`).join('')}</div><p><strong>处理规则：</strong>${escape(task.decision_package.policy_citation)}</p><p><strong>系统建议：</strong>${escape(task.decision_package.recommendation)}</p>${task.decision_package.missing_information.length ? `<p><strong>还需要补充：</strong>${task.decision_package.missing_information.map(escape).join('；')}</p>` : ''}</article>` : '';
    const humanCard = task.requires_human_confirmation ? `<article class="card warning"><h2>这题需要人工进一步确认</h2><p>你不需要替用户直接做决定。请先点下面的按钮，再选择“交给人工进一步确认”。</p><button class="choice${humanConfirmationOpened ? ' selected' : ''}" id="human">${humanConfirmationOpened ? '已选择人工进一步确认' : '交给人工进一步确认'}</button>${task.condition === 'DECISION_PACKAGE' && humanConfirmationOpened ? `<p><strong>你会怎么处理系统给出的建议？</strong></p><div class="grid two">${suggestionChoices.map(([value, label]) => `<button class="choice${selectedClass(value, suggestionChoice)}" data-suggestion="${value}">${label}</button>`).join('')}</div>` : ''}</article>` : '';
    app.innerHTML = `<header class="top"><div><p class="title">模拟客服小实验</p><p class="progress">第 ${state.session.completed_task_ids.length + 1} / 6 题</p></div></header><section class="shell"><div class="task-head question"><div><p class="eyebrow">现在请完成这一题</p><h1>先看清楚情况，再选择下一步</h1></div><div class="timer" id="timer">${timerText()}</div></div><article class="card"><h2>用户遇到的问题</h2><p>${escape(task.prompt)}</p></article>${packageCard}<article class="card"><h2>${task.condition === 'MANUAL' ? '请自己查看这些信息' : '需要时可以再看原始信息'}</h2><p class="muted">只打开你觉得需要的信息。</p><div class="grid two">${sourceButtons}</div>${sourceDetails}</article>${humanCard}<article class="card"><h2>现在请选择你认为合适的处理方式</h2><div class="grid three" style="margin-top:14px">${outcomeOptions.map(([value, label, detail]) => `<button class="choice${selectedClass(value, selectedOutcome)}" data-outcome="${value}">${label}<small>${detail}</small></button>`).join('')}</div></article><article class="card"><h2>这一题做起来难不难？</h2><p class="muted">1 = 非常难，7 = 非常容易</p><div class="grid scale" id="scale">${[1,2,3,4,5,6,7].map((value) => `<label><input type="radio" name="ease" value="${value}" ${easeRating === value ? 'checked' : ''}>${value}</label>`).join('')}</div><label class="muted" style="display:block;margin-top:20px">还有想补充的吗？（可不填）<textarea id="notes" maxlength="500" placeholder="例如：我不太理解某条信息">${escape(notes)}</textarea></label><button class="primary" id="submit" ${state.saving ? 'disabled' : ''}>${state.saving ? '正在保存…' : '提交这一题'}</button>${notice()}</article></section>`;
    document.querySelectorAll('[data-source]').forEach((button) => button.addEventListener('click', () => { const id = button.dataset.source; if (!state.active.sourceActions.includes(id)) state.active.sourceActions.push(id); renderTask(); }));
    document.querySelectorAll('[data-outcome]').forEach((button) => button.addEventListener('click', () => { state.active.selectedOutcome = button.dataset.outcome; renderTask(); }));
    document.querySelector('#human')?.addEventListener('click', () => { state.active.humanConfirmationOpened = true; renderTask(); });
    document.querySelectorAll('[data-suggestion]').forEach((button) => button.addEventListener('click', () => { state.active.suggestionChoice = button.dataset.suggestion; renderTask(); }));
    document.querySelectorAll('input[name="ease"]').forEach((input) => input.addEventListener('change', () => { state.active.easeRating = Number(input.value); }));
    document.querySelector('#notes').addEventListener('input', (event) => { state.active.notes = event.target.value; });
    document.querySelector('#submit').addEventListener('click', submitTask);
  }

  async function startTask() {
    const task = currentTask(); state.error = ''; state.notice = '';
    try {
      const started = await request(`/api/public-efficiency/tasks/${task.task_id}/start`, { participant_id: state.session.participant_id });
      state.active = { task, activeElapsedMs: 0, activeSinceMs: document.visibilityState === 'visible' ? Date.now() : null, sourceActions: [], selectedOutcome: null, humanConfirmationOpened: false, suggestionChoice: null, easeRating: null, notes: '' }; renderTask();
    } catch (error) { state.error = error.message; renderIntro(); }
  }

  async function submitTask() {
    const active = state.active;
    if (!active.selectedOutcome || !active.easeRating) { state.error = '请先选择你认为合适的处理方式，并完成这一题的难易评分。'; renderTask(); return; }
    if (active.task.requires_human_confirmation && (!active.humanConfirmationOpened || active.selectedOutcome !== 'WAITING_REVIEW')) { state.error = '这题需要先选择“交给人工进一步确认”。'; renderTask(); return; }
    if (active.task.requires_human_confirmation && active.task.condition === 'DECISION_PACKAGE' && !active.suggestionChoice) { state.error = '请告诉我们：你会怎样处理系统给出的建议。'; renderTask(); return; }
    state.saving = true; state.error = ''; renderTask();
    try {
      const saved = await request(`/api/public-efficiency/tasks/${active.task.task_id}/records`, { participant_id: state.session.participant_id, selected_outcome: active.selectedOutcome, source_actions: active.sourceActions, high_risk_gate_observed: active.humanConfirmationOpened, proposal_outcome: active.suggestionChoice, active_duration_seconds: Math.round(activeElapsedMs() / 1000), ease_rating_1_to_7: active.easeRating, observer_notes: active.notes });
      state.session.completed_task_ids = saved.completed_task_ids; state.active = null; state.notice = saved.experiment_completed ? '' : '这一题已经保存。准备好后再开始下一题。'; state.saving = false;
      if (saved.experiment_completed) renderThanks(); else renderIntro();
    } catch (error) { state.error = error.message; state.saving = false; renderTask(); }
  }

  function renderThanks() { app.innerHTML = `<section class="shell"><div class="card thanks"><p class="success">✓</p><h1>感谢你的参与！</h1><p class="muted">你已完成全部题目。你的回答已保存，无需再操作。</p></div></section>`; }
  document.addEventListener('visibilitychange', () => {
    if (!state.active) return;
    if (document.visibilityState === 'hidden' && state.active.activeSinceMs) {
      state.active.activeElapsedMs = activeElapsedMs(); state.active.activeSinceMs = null;
    }
    if (document.visibilityState === 'visible' && !state.active.activeSinceMs) state.active.activeSinceMs = Date.now();
  });
  setInterval(() => { const timer = document.querySelector('#timer'); if (timer) timer.textContent = timerText(); }, 1000);

  async function initialize() {
    if (!apiBase || apiBase.includes('127.0.0.1') && location.hostname !== '127.0.0.1' && location.hostname !== 'localhost') { state.error = '实验页面尚未连接到服务，请联系研究者。'; app.innerHTML = `<section class="shell"><div class="card intro"><h1>暂时无法打开实验</h1>${notice()}</div></section>`; return; }
    const params = new URLSearchParams(location.search); const pilotCode = params.get('pilot');
    try {
      state.session = await request('/api/public-efficiency/sessions', { participant_id: participantId(), study_mode: pilotCode ? 'PILOT' : 'FORMAL', pilot_access_code: pilotCode || undefined });
      if (state.session.completed_task_ids.length === 6) renderThanks(); else renderIntro();
    } catch (error) { state.error = error.message; app.innerHTML = `<section class="shell"><div class="card intro"><h1>暂时无法打开实验</h1>${notice()}</div></section>`; }
  }
  initialize();
})();
