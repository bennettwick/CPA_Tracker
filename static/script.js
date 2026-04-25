// ---- Section helpers ----

function showSection(name) {
  document.getElementById('upload-section').style.display  = name === 'upload'  ? '' : 'none';
  document.getElementById('loading-section').style.display = name === 'loading' ? '' : 'none';
  document.getElementById('results-section').style.display = name === 'results' ? '' : 'none';
}

function showError(msg) {
  var el = document.getElementById('error-msg');
  el.textContent = msg;
  el.style.display = '';
}

function hideError() {
  document.getElementById('error-msg').style.display = 'none';
}

// ---- Populate state dropdown on load ----

async function loadStates() {
  try {
    var res = await fetch('/states');
    var data = await res.json();
    var select = document.getElementById('state-select');
    select.innerHTML = '<option value="">-- Select a state --</option>';
    data.states.forEach(function(s) {
      var opt = document.createElement('option');
      opt.value = s;
      opt.textContent = s;
      select.appendChild(opt);
    });
  } catch (e) {
    document.getElementById('state-select').innerHTML =
      '<option value="">Could not load states</option>';
  }
}

// ---- Form submit ----

document.getElementById('upload-form').addEventListener('submit', async function(e) {
  e.preventDefault();
  hideError();

  var file = document.getElementById('transcript-input').files[0];
  var state = document.getElementById('state-select').value;

  if (!state) { showError('Please select a state.'); return; }
  if (!file)  { showError('Please select a PDF transcript.'); return; }

  var formData = new FormData();
  formData.append('transcript', file);
  formData.append('state', state);

  showSection('loading');

  try {
    var res = await fetch('/check', { method: 'POST', body: formData });
    var data = await res.json();

    if (!res.ok || data.error) {
      showSection('upload');
      showError(data.error || 'An unexpected error occurred. Please try again.');
      return;
    }

    renderResults(data.results, data.courses);
    showSection('results');

  } catch (e) {
    showSection('upload');
    showError('Network error. Please check your connection and try again.');
  }
});

// ---- Start over ----

document.getElementById('start-over-btn').addEventListener('click', function() {
  document.getElementById('upload-form').reset();
  _results = null;
  _degreeConferred = null;
  showSection('upload');
});

// ---- Degree conferred toggle ----

document.getElementById('degree-yes-btn').addEventListener('click', function() {
  _degreeConferred = true;
  updateDegreeToggleUI(true);
  renderSummaryBanner();
});

document.getElementById('degree-no-btn').addEventListener('click', function() {
  _degreeConferred = false;
  updateDegreeToggleUI(false);
  renderSummaryBanner();
});

// ---- Toggle extracted courses table ----

document.getElementById('toggle-courses').addEventListener('click', function() {
  var wrap = document.getElementById('courses-table-wrap');
  var isHidden = wrap.style.display === 'none';
  wrap.style.display = isHidden ? '' : 'none';
  this.innerHTML = isHidden
    ? 'Hide Extracted Courses &#9650;'
    : 'Show All Extracted Courses &#9660;';
});

// ---- Results state ----

var _results = null;
var _degreeConferred = null;

// ---- Render results ----

function renderResults(results, courses) {
  _results = results;
  _degreeConferred = results.degree_info ? results.degree_info.assumed_conferred : null;

  renderSummaryBanner();
  renderDegreeCard(results.degree_info);
  renderTopicResults(results.topic_results);
  renderHourTotals(results.hour_totals);
  renderGradeFlags(results.grade_flags);
  renderUnclearCourses(results.unclear_courses);
  renderManualChecks(results.manual_checks);
  renderLevelWarning(results.level_detection_warning);
  renderCoursesTable(courses);
}

function calcSummary() {
  if (!_results) return 'not_eligible';

  if (_results.degree_info) {
    if (!_degreeConferred) return 'not_eligible';
  }
  if (_results.grade_flags && _results.grade_flags.length > 0) return 'needs_review';
  if (_results.unclear_courses && _results.unclear_courses.length > 0) return 'needs_review';

  var allTopicsMet = (_results.topic_results || []).every(function(t) { return t.met; });
  var allHoursMet = true;
  if (_results.hour_totals) {
    Object.keys(_results.hour_totals).forEach(function(k) {
      if (!_results.hour_totals[k].met) allHoursMet = false;
    });
  }
  return (allTopicsMet && allHoursMet) ? 'eligible' : 'not_eligible';
}

function renderSummaryBanner() {
  var summary = calcSummary();
  var banner  = document.getElementById('summary-banner');
  var icon    = document.getElementById('summary-icon');
  var text    = document.getElementById('summary-text');
  var state   = _results ? _results.state : '';

  banner.className = 'summary-banner';
  if (summary === 'eligible') {
    banner.classList.add('eligible');
    icon.textContent = '✓';
    text.textContent = state + ': You appear to meet the exam eligibility requirements.';
  } else if (summary === 'needs_review') {
    banner.classList.add('needs-review');
    icon.textContent = '⚠';
    text.textContent = state + ': Some items need your review before a determination can be made.';
  } else {
    banner.classList.add('not-eligible');
    icon.textContent = '✗';
    text.textContent = state + ': You do not yet meet all exam eligibility requirements.';
  }
}

function renderDegreeCard(degreeInfo) {
  var card = document.getElementById('degree-card');
  if (!degreeInfo) { card.style.display = 'none'; return; }
  card.style.display = '';
  document.getElementById('degree-note').textContent = degreeInfo.note;
  updateDegreeToggleUI(_degreeConferred);
}

function updateDegreeToggleUI(conferred) {
  var yesBtn = document.getElementById('degree-yes-btn');
  var noBtn  = document.getElementById('degree-no-btn');
  yesBtn.className = 'toggle-btn' + (conferred === true  ? ' active-yes' : '');
  noBtn.className  = 'toggle-btn' + (conferred === false ? ' active-no'  : '');
}

function renderTopicResults(topicResults) {
  var ul = document.getElementById('topic-list');
  ul.innerHTML = '';

  if (!topicResults || topicResults.length === 0) {
    ul.innerHTML = '<li>No required topics found for this state.</li>';
    return;
  }

  topicResults.forEach(function(t) {
    var li = document.createElement('li');

    var nameSpan = document.createElement('span');
    nameSpan.className = 'topic-name';
    nameSpan.textContent = formatTopicKey(t.topic);

    var credSpan = document.createElement('span');
    credSpan.className = 'topic-credits';
    credSpan.textContent = t.earned_credits + ' / ' + t.required_credits + ' cr';

    var badge = document.createElement('span');
    badge.className = 'badge ' + (t.met ? 'met' : 'unmet');
    badge.textContent = t.met ? 'Met' : 'Not Met';

    li.appendChild(nameSpan);
    li.appendChild(credSpan);
    li.appendChild(badge);
    ul.appendChild(li);
  });
}

function renderHourTotals(hourTotals) {
  var container = document.getElementById('hour-totals');
  container.innerHTML = '';
  if (!hourTotals) return;

  ['accounting', 'business'].forEach(function(section) {
    var h = hourTotals[section];
    if (!h) return;
    var label = section.charAt(0).toUpperCase() + section.slice(1) + ' Hours';
    var target = h.required_undergrad || h.required_grad;
    renderHourBar(container, label, h.earned_total, target, h.met ? 'met' : 'unmet', h.shortfall_message);
  });
}

function renderHourBar(container, label, earned, required, colorClass, shortfall) {
  var pct = required > 0 ? Math.min(100, Math.round((earned / required) * 100)) : 0;

  var row = document.createElement('div');
  row.className = 'hour-row';

  var labelEl = document.createElement('div');
  labelEl.className = 'hour-label';
  labelEl.textContent = label;

  var barWrap = document.createElement('div');
  barWrap.className = 'progress-bar-wrap';

  var bar = document.createElement('div');
  bar.className = 'progress-bar ' + colorClass;
  bar.style.width = pct + '%';
  barWrap.appendChild(bar);

  var numLabel = document.createElement('div');
  numLabel.className = 'hour-numeric';
  numLabel.textContent = earned + ' / ' + required;

  row.appendChild(labelEl);
  row.appendChild(barWrap);
  row.appendChild(numLabel);

  if (shortfall) {
    var sub = document.createElement('div');
    sub.className = 'hour-sub shortfall';
    sub.textContent = shortfall;
    row.appendChild(sub);
  }

  container.appendChild(row);
}

function renderGradeFlags(flags) {
  var card = document.getElementById('grade-flags-card');
  var ul   = document.getElementById('grade-flags-list');
  ul.innerHTML = '';

  if (!flags || flags.length === 0) {
    card.style.display = 'none';
    return;
  }

  card.style.display = '';
  flags.forEach(function(f) {
    var li = document.createElement('li');
    li.textContent = f.name + ' — Grade: ' + (f.grade || 'N/A') +
      ' (minimum required: ' + f.min_required + ', topic: ' + formatTopicKey(f.topic) + ')';
    ul.appendChild(li);
  });
}

function renderUnclearCourses(unclear) {
  var card = document.getElementById('unclear-card');
  var ul   = document.getElementById('unclear-list');
  ul.innerHTML = '';

  if (!unclear || unclear.length === 0) {
    card.style.display = 'none';
    return;
  }

  card.style.display = '';
  unclear.forEach(function(c) {
    var li = document.createElement('li');
    li.textContent = c.name + ' (' + (c.credits || '?') + ' cr)';
    ul.appendChild(li);
  });
}

function renderManualChecks(checks) {
  var card = document.getElementById('manual-checks-card');
  var ul   = document.getElementById('manual-checks-list');
  ul.innerHTML = '';

  if (!checks || checks.length === 0) {
    card.style.display = 'none';
    return;
  }

  card.style.display = '';
  checks.forEach(function(c) {
    var li = document.createElement('li');
    li.textContent = c;
    ul.appendChild(li);
  });
}

function renderLevelWarning(show) {
  document.getElementById('level-warning-card').style.display = show ? '' : 'none';
}

function renderCoursesTable(courses) {
  var tbody = document.getElementById('courses-tbody');
  tbody.innerHTML = '';

  if (!courses || courses.length === 0) return;

  courses.forEach(function(c) {
    var tr = document.createElement('tr');
    [
      c.name || '—',
      c.credits != null ? c.credits : '—',
      c.grade  || '—',
      c.year   || '—',
      c.level  || '—',
      formatTopicKey(c.cpa_category || 'other'),
    ].forEach(function(val) {
      var td = document.createElement('td');
      td.textContent = val;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

// ---- Helpers ----

function formatTopicKey(key) {
  if (!key) return '';
  return key.replace(/_/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
}

// ---- Init ----
loadStates();
