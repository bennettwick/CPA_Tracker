// ============================================================
// STATE
// ============================================================
let _results = null;
let _courses = null;
let _graduation_status = 'unknown';
let _degreeConferred = null;
let _openTopics = {};

// ============================================================
// HELPERS
// ============================================================
function fmt(key) {
  if (!key) return '';
  return String(key).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
const _KNOWN_CATEGORIES = new Set([
  'financial_accounting','management_accounting','governmental_nonprofit',
  'taxation','auditing','accounting_information_systems','accounting_elective',
  'upper_division_accounting','general_business','business_law','ethics',
  'other','unclear',
]);
function displayCategory(cat) {
  if (!cat || cat === 'general_business') return 'Business';
  if (!_KNOWN_CATEGORIES.has(cat)) return 'Business';
  return fmt(cat);
}
function semLabel(c) {
  const ok = { Fall: 1, Spring: 1, Summer: 1, Winter: 1 };
  const s = c.semester && ok[c.semester] ? c.semester : null;
  const y = c.year ? String(c.year) : null;
  if (s && y) return s + ' ' + y;
  return y || 'Unknown';
}
function semSort(l) {
  if (l === 'Unknown') return 999990;
  const o = { Spring: 1, Summer: 2, Fall: 3, Winter: 4 };
  const p = l.split(' ');
  return p.length === 1 ? (parseInt(p[0]) || 9999) * 10 : (parseInt(p[1]) || 9999) * 10 + (o[p[0]] || 0);
}

// ============================================================
// SECTION SWITCH
// ============================================================
function showSection(name) {
  const upload  = document.getElementById('upload-section');
  const loading = document.getElementById('loading-section');
  const results = document.getElementById('results-section');
  upload.style.display  = name === 'upload'  ? 'flex'  : 'none';
  loading.style.display = name === 'loading' ? 'flex'  : 'none';
  results.style.display = name === 'results' ? 'block' : 'none';
  document.body.classList.toggle('on-results', name === 'results');
}

// ============================================================
// ERROR DISPLAY
// ============================================================
function showError(msg) {
  const el = document.getElementById('error-msg');
  el.textContent = msg;
  el.style.display = '';
}
function hideError() {
  const el = document.getElementById('error-msg');
  if (el) el.style.display = 'none';
}

// ============================================================
// SUMMARY CALC
// ============================================================
function calcSummary() {
  if (!_results) return 'not_eligible';
  if (_results.degree_info && !_degreeConferred) return 'not_eligible';
  if ((_results.grade_flags || []).length > 0) return 'needs_review';
  if ((_results.unclear_courses || []).length > 0) return 'needs_review';
  const topicsMet = (_results.topic_results || []).every(t => t.met);
  let hoursMet = true;
  if (_results.hour_totals) {
    Object.values(_results.hour_totals).forEach(h => { if (!h.met) hoursMet = false; });
  }
  return (topicsMet && hoursMet) ? 'eligible' : 'not_eligible';
}

// ============================================================
// RENDER STATUS BADGE + NAV PILL
// ============================================================
function renderStatus() {
  const s = calcSummary();
  const badge = document.getElementById('status-badge-large');
  const text  = document.getElementById('status-badge-text');
  const msg   = document.getElementById('results-header-msg');

  const cls = s === 'eligible' ? 'eligible' : s === 'needs_review' ? 'needs-review' : 'not-eligible';
  badge.className = 'status-badge-large ' + cls;

  const asterisk = '<sup class="verdict-asterisk">*</sup>';
  if (s === 'eligible') {
    text.innerHTML = 'Eligible' + asterisk;
  } else if (s === 'needs_review') {
    text.innerHTML = 'Needs Review' + asterisk;
  } else {
    text.innerHTML = 'Not Yet Eligible' + asterisk;
  }
  msg.style.display = 'none';
}

// ============================================================
// RENDER TOPICS
// ============================================================
function renderTopics(topicResults) {
  const container = document.getElementById('topic-list');
  container.innerHTML = '';
  if (!topicResults || topicResults.length === 0) {
    const empty = document.createElement('div');
    empty.style.padding = '1rem 1.5rem';
    empty.style.fontSize = '0.85rem';
    empty.style.color = 'var(--ink-muted)';
    empty.textContent = 'No required topics found for this state.';
    container.appendChild(empty);
    return;
  }
  topicResults.forEach(t => {
    const pct = t.required_credits > 0
      ? Math.min(100, Math.round(t.earned_credits / t.required_credits * 100))
      : 0;

    const row = document.createElement('div');
    row.className = 'topic-row' + (_openTopics[t.topic] ? ' open' : '');

    const arrow = document.createElement('span');
    arrow.className = 'topic-row-arrow';
    arrow.innerHTML = '<svg viewBox="0 0 11 11" fill="none"><path d="M3 2l4 3.5L3 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    const name = document.createElement('span');
    name.className = 'topic-row-name';
    name.textContent = fmt(t.topic);

    const miniBar = document.createElement('div');
    miniBar.className = 'topic-mini-bar';
    miniBar.innerHTML = '<div class="topic-mini-fill ' + (t.met ? 'met' : 'unmet') + '" style="width:' + pct + '%"></div>';

    const cred = document.createElement('span');
    cred.className = 'topic-row-cred';
    cred.textContent = t.earned_credits + ' / ' + t.required_credits + ' cr';

    const badge = document.createElement('span');
    badge.className = 'tbadge ' + (t.met ? 'met' : 'unmet');
    badge.textContent = t.met ? 'Met' : 'Not Met';

    row.append(arrow, name, miniBar, cred, badge);

    const expand = document.createElement('div');
    expand.className = 'topic-expand' + (_openTopics[t.topic] ? ' open' : '');
    buildExpandBody(expand, t);

    row.addEventListener('click', () => {
      const opening = !expand.classList.contains('open');
      expand.classList.toggle('open', opening);
      row.classList.toggle('open', opening);
      _openTopics[t.topic] = opening;
    });

    container.appendChild(row);
    container.appendChild(expand);
  });
}

function buildExpandBody(expand, t) {
  expand.innerHTML = '';
  const pills = document.createElement('div');
  pills.className = 'te-pills';

  if (!t.courses || t.courses.length === 0) {
    const empty = document.createElement('span');
    empty.className = 'te-empty';
    empty.textContent = 'No courses assigned to this requirement.';
    pills.appendChild(empty);
  } else {
    // Track used indices so duplicate-named retakes each map to the right entry.
    const usedIdx = new Set();
    const eligibility = t.course_eligibility || [];
    t.courses.forEach((cn, ci) => {
      const isIneligible = eligibility[ci] === false;
      let courseIdx = -1;
      for (let i = 0; i < (_courses || []).length; i++) {
        if (_courses[i].name === cn && _courses[i].cpa_category === t.topic && !usedIdx.has(i)) {
          courseIdx = i;
          break;
        }
      }
      const c = courseIdx >= 0 ? _courses[courseIdx] : null;
      if (courseIdx >= 0) usedIdx.add(courseIdx);

      const pill = document.createElement('span');
      pill.className = 'course-pill' + (isIneligible ? ' ineligible' : '');
      if (isIneligible) {
        pill.title = 'Not counted — this requirement only accepts upper-level courses.';
      }
      const prefix = c && c.code ? c.code + ': ' : '';
      const cr     = c ? ' (' + c.credits + ' cr)' : '';
      const label = document.createElement('span');
      label.textContent = prefix + cn + cr + (isIneligible ? ' — lower-level, not counted' : '');
      const x = document.createElement('button');
      x.className = 'pill-x';
      x.title = 'Remove from this requirement';
      x.textContent = '×';
      x.addEventListener('click', e => {
        e.stopPropagation();
        if (courseIdx >= 0) {
          _courses[courseIdx].cpa_category = 'other';
          recalculate();
        }
      });
      pill.appendChild(label);
      pill.appendChild(x);
      pills.appendChild(pill);
    });
  }

  expand.appendChild(pills);
  expand.appendChild(buildAddCourseWidget(t));
}

function buildAddCourseWidget(t) {
  const wrap = document.createElement('div');
  wrap.className = 'add-course-wrap';

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'add-course-btn';
  btn.textContent = '+ Add a course';

  const popup = document.createElement('div');
  popup.className = 'add-course-popup';

  const search = document.createElement('input');
  search.type = 'text';
  search.className = 'add-course-search';
  search.placeholder = 'Search by name or code…';

  const list = document.createElement('div');
  list.className = 'add-course-list';

  // Sort all candidates alphabetically by code+name. Tag ineligible candidates so the
  // dropdown shows *why* they won't count toward this requirement.
  const upperOnly = !!t.upper_level_only;
  const candidates = (_courses || [])
    .map((c, idx) => ({ c, idx }))
    .filter(({ c }) => c.cpa_category !== t.topic)
    .map(({ c, idx }) => ({
      c, idx,
      ineligible: upperOnly && c.is_upper_level === false,
    }))
    .sort((a, b) => {
      const la = ((a.c.code || '') + ' ' + (a.c.name || '')).toLowerCase();
      const lb = ((b.c.code || '') + ' ' + (b.c.name || '')).toLowerCase();
      return la.localeCompare(lb);
    });

  function renderList(filterText) {
    list.innerHTML = '';
    const f = (filterText || '').toLowerCase().trim();
    let count = 0;
    candidates.forEach(({ c, idx, ineligible }) => {
      const labelText =
        (c.code ? c.code + ': ' : '') +
        c.name +
        ' (' + (c.credits != null ? c.credits : '?') + ' cr — ' +
        displayCategory(c.cpa_category) +
        (ineligible ? ' — lower-level, not counted' : '') +
        ')';
      if (f && !labelText.toLowerCase().includes(f)) return;
      count++;
      const opt = document.createElement('button');
      opt.type = 'button';
      opt.className = 'add-course-option' + (ineligible ? ' ineligible' : '');
      opt.textContent = labelText;
      if (ineligible) {
        opt.title = 'Will be assigned to this requirement, but won\'t count toward credits because it is not upper-level.';
      }
      opt.addEventListener('click', e => {
        e.stopPropagation();
        // Use index, not name — names can collide when a student has duplicate enrollments.
        _courses[idx].cpa_category = t.topic;
        recalculate();
      });
      list.appendChild(opt);
    });
    if (count === 0) {
      const empty = document.createElement('div');
      empty.className = 'add-course-empty';
      empty.textContent = candidates.length === 0
        ? 'No other courses available.'
        : 'No matching courses.';
      list.appendChild(empty);
    }
  }

  search.addEventListener('input', () => renderList(search.value));
  search.addEventListener('click', e => e.stopPropagation());
  search.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      popup.classList.remove('open');
      btn.focus();
    }
  });

  btn.addEventListener('click', e => {
    e.stopPropagation();
    const opening = !popup.classList.contains('open');
    document.querySelectorAll('.add-course-popup.open').forEach(p => {
      if (p !== popup) p.classList.remove('open');
    });
    popup.classList.toggle('open', opening);
    if (opening) {
      search.value = '';
      renderList('');
      setTimeout(() => search.focus(), 0);
    }
  });

  popup.appendChild(search);
  popup.appendChild(list);
  wrap.appendChild(btn);
  wrap.appendChild(popup);
  return wrap;
}

// ============================================================
// RENDER HOURS (rings)
// ============================================================
function renderHours(hourTotals) {
  if (!hourTotals) return;
  const R = 38, CIRC = 2 * Math.PI * R;
  ['accounting', 'business'].forEach(key => {
    const h = hourTotals[key];
    const prefix = key === 'accounting' ? 'acct' : 'biz';
    const rowEl  = document.getElementById('ring-row-' + prefix);
    if (!h) {
      if (rowEl) rowEl.style.display = 'none';
      return;
    }
    if (rowEl) rowEl.style.display = '';
    const target = h.required_undergrad || h.required_grad || 1;
    const pct = Math.min(1, h.earned_total / target);
    const dash = (pct * CIRC).toFixed(1);

    const ringEl = document.getElementById('ring-' + prefix);
    if (ringEl) {
      ringEl.setAttribute('stroke-dasharray', dash + ' ' + CIRC);
      ringEl.setAttribute('class', 'ring-fill-c ' + (h.met ? 'met' : 'unmet'));
    }
    const numEl  = document.getElementById('ring-' + prefix + '-num');
    const denEl  = document.getElementById('ring-' + prefix + '-den');
    const noteEl = document.getElementById('ring-' + prefix + '-note');
    if (numEl)  numEl.textContent  = h.earned_total;
    if (denEl)  denEl.textContent  = '/ ' + target;
    if (noteEl) {
      if (h.shortfall_message) {
        noteEl.textContent = h.shortfall_message;
        noteEl.className   = 'ring-note shortfall';
      } else if (h.earned_total > target) {
        noteEl.textContent = (h.earned_total - target) + ' hours over requirement';
        noteEl.className   = 'ring-note surplus';
      } else {
        noteEl.textContent = 'Requirement met';
        noteEl.className   = 'ring-note surplus';
      }
    }
  });
}

// ============================================================
// RENDER DEGREE
// ============================================================
function renderDegree(degreeInfo) {
  const sec = document.getElementById('degree-section');
  if (!degreeInfo) { sec.style.display = 'none'; return; }
  sec.style.display = '';
  document.getElementById('degree-note').textContent = degreeInfo.note;
  updateDegreeUI(_degreeConferred);
}
function updateDegreeUI(val) {
  document.getElementById('degree-yes-btn').className = 'tog' + (val === true  ? ' active-yes' : '');
  document.getElementById('degree-no-btn').className  = 'tog' + (val === false ? ' active-no'  : '');
}

// ============================================================
// RENDER ALERT CARDS
// ============================================================
function renderGradeFlags(flags) {
  const card = document.getElementById('grade-flags-card');
  const ul   = document.getElementById('grade-flags-list');
  ul.innerHTML = '';
  if (!flags || flags.length === 0) { card.style.display = 'none'; return; }
  card.style.display = '';
  flags.forEach(f => {
    const li = document.createElement('li');
    li.textContent = f.name + ' — Grade: ' + (f.grade || 'N/A') +
      ' (minimum required: ' + f.min_required + ', topic: ' + fmt(f.topic) + ')';
    ul.appendChild(li);
  });
}
function renderUnclear(list) {
  const card = document.getElementById('unclear-card');
  const ul   = document.getElementById('unclear-list');
  ul.innerHTML = '';
  if (!list || list.length === 0) { card.style.display = 'none'; return; }
  card.style.display = '';
  list.forEach(c => {
    const li = document.createElement('li');
    li.textContent = c.name + ' (' + (c.credits != null ? c.credits : '?') + ' cr)';
    ul.appendChild(li);
  });
}
function renderManual(checks) {
  const card = document.getElementById('manual-checks-card');
  const ul   = document.getElementById('manual-checks-list');
  ul.innerHTML = '';
  if (!checks || checks.length === 0) { card.style.display = 'none'; return; }
  card.style.display = '';
  checks.forEach(c => {
    const li = document.createElement('li');
    li.textContent = c;
    ul.appendChild(li);
  });
}
function renderLevelWarn(show) {
  document.getElementById('level-warning-card').style.display = show ? '' : 'none';
}

// ============================================================
// RENDER COURSES TABLE
// ============================================================
function renderCoursesTable(courses) {
  const tbody = document.getElementById('courses-tbody');
  tbody.innerHTML = '';
  if (!courses || courses.length === 0) return;
  const groups = {};
  courses.forEach(c => {
    const l = semLabel(c);
    if (!groups[l]) groups[l] = [];
    groups[l].push(c);
  });
  Object.keys(groups).sort((a, b) => semSort(a) - semSort(b)).forEach(label => {
    const htr = document.createElement('tr');
    htr.className = 'semester-header';
    const htd = document.createElement('td');
    htd.colSpan = 5;
    htd.textContent = label;
    htr.appendChild(htd);
    tbody.appendChild(htr);
    groups[label].forEach(c => {
      const tr = document.createElement('tr');
      const cells = [
        (c.code ? c.code + ': ' : '') + (c.name || '—'),
        c.credits != null ? c.credits : '—',
        c.grade || '—',
        c.level || '—',
        displayCategory(c.cpa_category),
      ];
      cells.forEach(v => {
        const td = document.createElement('td');
        td.textContent = v;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  });
}

// ============================================================
// FULL RENDER
// ============================================================
function renderAll() {
  if (!_results) return;
  renderStatus();
  renderTopics(_results.topic_results);
  renderHours(_results.hour_totals);
  renderDegree(_results.degree_info);
  renderGradeFlags(_results.grade_flags);
  renderUnclear(_results.unclear_courses);
  renderManual(_results.manual_checks);
  renderLevelWarn(_results.level_detection_warning);
  renderCoursesTable(_courses);
  document.getElementById('results-state-name').textContent = _results.state || '';

  const guidanceLink = document.getElementById('guidance-link');
  const guidanceUrl  = document.getElementById('guidance-url');
  const boardUrl = (_results.board_url || '').trim();
  if (boardUrl) {
    guidanceLink.href = boardUrl;
    guidanceUrl.textContent = boardUrl;
    guidanceLink.style.display = '';
  } else {
    guidanceLink.style.display = 'none';
  }

}

// ============================================================
// RECALCULATE — POST to /recalculate
// ============================================================
function recalculate() {
  fetch('/recalculate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      courses: _courses,
      state: _results.state,
      graduation_status: _graduation_status,
    }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) return;
      _results = data.results;
      renderAll();
    })
    .catch(() => {});
}

// ============================================================
// LOAD STATES
// ============================================================
async function loadStates() {
  const sel = document.getElementById('state-select-v2');
  try {
    const res  = await fetch('/states');
    const data = await res.json();
    sel.innerHTML = '<option value="">Select a state…</option>';
    (data.states || []).forEach(s => {
      const o = document.createElement('option');
      o.value = s; o.textContent = s;
      sel.appendChild(o);
    });
  } catch {
    sel.innerHTML = '<option value="">Could not load states</option>';
  }
}

// ============================================================
// SUBMIT
// ============================================================
async function handleSubmit() {
  hideError();
  const state = document.getElementById('state-select-v2').value;
  const file  = document.getElementById('transcript-v2').files[0];

  if (!state) { showError('Please select a state.'); return; }
  if (!file)  { showError('Please select a PDF transcript.'); return; }

  const fd = new FormData();
  fd.append('transcript', file);
  fd.append('state', state);

  showSection('loading');

  try {
    const res  = await fetch('/check', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok || data.error) {
      showSection('upload');
      showError(data.error || 'An unexpected error occurred. Please try again.');
      return;
    }
    _results = data.results;
    _courses = data.courses;
    _graduation_status = data.graduation_status || 'unknown';
    _openTopics = {};
    _degreeConferred = _results.degree_info ? _results.degree_info.assumed_conferred : null;
    renderAll();
    showSection('results');
  } catch {
    showSection('upload');
    showError('Network error. Please check your connection and try again.');
  }
}

// ============================================================
// EVENT WIRING
// ============================================================
document.getElementById('submit-btn').addEventListener('click', handleSubmit);

document.getElementById('degree-yes-btn').addEventListener('click', () => {
  _degreeConferred = true;
  updateDegreeUI(true);
  renderStatus();
});
document.getElementById('degree-no-btn').addEventListener('click', () => {
  _degreeConferred = false;
  updateDegreeUI(false);
  renderStatus();
});

document.getElementById('toggle-courses').addEventListener('click', function () {
  const wrap = document.getElementById('courses-table-wrap');
  const open = wrap.style.display === 'none';
  wrap.style.display = open ? '' : 'none';
  document.getElementById('ctb-icon').classList.toggle('open', open);
  document.getElementById('courses-toggle-label').textContent = open ? 'Hide Courses' : 'Show All Courses';
});

document.getElementById('start-over-btn').addEventListener('click', () => {
  _results = null;
  _courses = null;
  _graduation_status = 'unknown';
  _openTopics = {};
  _degreeConferred = null;

  const fileInput = document.getElementById('transcript-v2');
  fileInput.value = '';
  document.getElementById('drop-zone').classList.remove('has-file');
  document.getElementById('drop-primary-text').textContent = 'Drop your PDF here';
  document.getElementById('state-select-v2').value = '';
  hideError();

  showSection('upload');
});

// Drop zone cosmetics
const dz = document.getElementById('drop-zone');
if (dz) {
  dz.addEventListener('dragover',  e => { e.preventDefault(); dz.classList.add('drag-over'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
  dz.addEventListener('drop',      e => { e.preventDefault(); dz.classList.remove('drag-over'); });
  document.getElementById('transcript-v2').addEventListener('change', function () {
    if (this.files[0]) {
      dz.classList.add('has-file');
      document.getElementById('drop-primary-text').textContent = this.files[0].name;
    } else {
      dz.classList.remove('has-file');
      document.getElementById('drop-primary-text').textContent = 'Drop your PDF here';
    }
  });
}

// Close any open add-course popup on outside click.
document.addEventListener('click', e => {
  if (!e.target.closest || !e.target.closest('.add-course-wrap')) {
    document.querySelectorAll('.add-course-popup.open').forEach(p => p.classList.remove('open'));
  }
});

// ============================================================
// INIT
// ============================================================
showSection('upload');
loadStates();
