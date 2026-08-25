/* 出题交互系统 前端逻辑 */
"use strict";

const $ = (sel) => document.querySelector(sel);
const view = document.getElementById("view");

const state = {
  view: "home",
  qtypes: [],
  paper: null,
  answers: {},
  index: 0,
  result: null,
  bank: { subject: "", qtype: "", search: "", page: 1 },
  records: { subject: "", status: "", page: 1 },
  review: { page: 1 },
  qtypeSubject: "",
};

let lastImportText = "";
let lastImportSubject = "";
let lastImportCourse = "";

const TEMPLATE_PRESETS = {
  随堂小测: [
    ["single_choice", 3, 5], ["blank", 3, 5], ["judge", 3, 2],
    ["calc", 2, 10], ["essay", 1, 10],
  ],
  标准测验: [
    ["single_choice", 5, 4], ["blank", 5, 4], ["judge", 5, 2],
    ["calc", 3, 10], ["essay", 2, 10],
  ],
  综合练习: [
    ["single_choice", 5, 4], ["blank", 5, 4], ["judge", 5, 2],
    ["calc", 4, 10], ["essay", 3, 10],
  ],
};

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  let data = {};
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!res.ok) throw new Error(data.detail || res.statusText || "请求失败");
  return data;
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function qtypeLabel(value) {
  const found = state.qtypes.find((t) => t.value === value);
  return found ? found.label : value;
}

function toast(msg) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2600);
}

function openModal(html) {
  const root = document.getElementById("modal-root");
  root.innerHTML =
    `<div class="modal-mask" onclick="if(event.target===this)app.closeModal()">
       <div class="modal">${html}</div>
     </div>`;
}

function closeModal() {
  document.getElementById("modal-root").innerHTML = "";
}

function optionLetters(n) {
  return "ABCDEFGH".slice(0, n);
}

function imgTag(name, cls = "") {
  return `<img class="q-img ${cls}" src="/images/${encodeURIComponent(name)}" alt="题目图片" loading="lazy" onerror="this.style.display='none'">`;
}

function imgHtml(q, cls = "") {
  const list = (q && q.images) || [];
  if (!list.length) return "";
  // 题干锚点已在 richText 内联渲染，images 字段里重复的图不再额外显示
  const anchored = new Set(
    String((q && q.question) || "").match(/【图:([^】]+)】/g) || []
  );
  return list
    .map((p) => {
      const name = String(p).split(/[\\/]/).pop();
      if (anchored.has(`【图:${name}】`)) return "";
      return imgTag(name, cls);
    })
    .join("");
}

function formulaHtml(q) {
  const f = (q && q.formula) || "";
  if (!f) return "";
  return `<span class="q-formula" data-tex="${esc(f)}"></span>`;
}

function renderMath() {
  if (!window.katex) return;
  document.querySelectorAll(".q-formula").forEach((el) => {
    try {
      window.katex.render(el.dataset.tex, el, { throwOnError: false });
    } catch (e) {
      el.textContent = el.dataset.tex;
    }
  });
}

function highlightMarkers(s) {
  return String(s)
    .replace(
      /(&lt;Formula[^&]*&gt;.*?&lt;\/Formula&gt;|&lt;ImgRef[^&]*&gt;.*?&lt;\/ImgRef&gt;|&lt;Formula[^&]*&gt;|&lt;ImgRef[^&]*&gt;)/gi,
      '<span class="ph-mark">$1</span>'
    );
}

function richText(s) {
  const text = String(s ?? "");
  // 按 $...$ 分段：公式段用未转义的原文喂 KaTeX，其余文本才做 HTML 转义，
  // 避免 > < & 被转义成 &gt; 等导致 KaTeX 报 ParseError。
  return text
    .split(/(\$[^$]+\$)/g)
    .map((part) => {
      const m = part.match(/^\$([^$]+)\$$/);
      if (m) {
        try {
          if (!window.katex) return esc(part);
          return window.katex.renderToString(m[1], { throwOnError: false });
        } catch (e) {
          return esc(part);
        }
      }
      // 先按图片锚点切分：文件名用原文（未转义）拼 URL，其余文本再做 HTML 转义，
      // 避免文件名先被 esc() 转义再 encodeURIComponent 导致 URL 编码错误
      const html = [];
      let last = 0;
      for (const mm of part.matchAll(/【图:([^】]+)】/g)) {
        html.push(highlightMarkers(esc(part.slice(last, mm.index))));
        html.push(imgTag(mm[1], "inline"));
        last = mm.index + mm[0].length;
      }
      html.push(highlightMarkers(esc(part.slice(last))));
      return html.join("");
    })
    .join("");
}

function richTextBrief(s, n = 120) {
  // 先截原始文本再渲染，避免截断 <img> 等 HTML 标签产生残缺页面
  const text = String(s ?? "");
  return richText(text.length > n ? text.slice(0, n) + "…" : text);
}

async function loadQtypes(subject = "") {
  state.qtypeSubject = subject;
  const url = "/api/qtypes" + (subject ? `?subject=${encodeURIComponent(subject)}` : "");
  try {
    state.qtypes = await api(url);
  } catch (e) {
    state.qtypes = [
      { value: "single_choice", label: "单选题", count: 0 },
      { value: "multiple_choice", label: "多选题", count: 0 },
      { value: "blank", label: "填空题", count: 0 },
      { value: "judge", label: "判断题", count: 0 },
      { value: "essay", label: "简答题", count: 0 },
      { value: "calc", label: "计算题", count: 0 },
      { value: "thinking", label: "思考题", count: 0 },
    ];
  }
}

async function refreshQtypeCounts() {
  await loadQtypes(state.qtypeSubject || "");
  if (state.view === "practice" || state.view === "paper") render();
}

async function practiceSubjectChanged(subject) {
  await loadQtypes(subject);
  render();
}

async function paperSubjectChanged(subject) {
  await loadQtypes(subject);
  render();
}

/* ------------------------------------------------------------------ */

async function renderHome() {
  const s = await api("/api/stats");
  const typeChips = (s.qtypes || [])
    .map((t) => `<span class="badge info">${esc(t.label)} ${t.count}</span>`)
    .join(" ");
  view.innerHTML = `
    <div class="stats-grid">
      <div class="stat-card"><div class="num">${s.total}</div><div class="lbl">题库总题数</div></div>
      <div class="stat-card"><div class="num">${(s.subjects || []).length}</div><div class="lbl">学科数</div></div>
      <div class="stat-card"><div class="num">${s.records}</div><div class="lbl">历史记录</div></div>
    </div>
    <div class="card mt">
      <h2>快速开始</h2>
      <div class="toolbar">
        <button class="btn" onclick="app.go('import')">📚 添加学科题库</button>
        <button class="btn green" onclick="app.go('practice')">🎯 专项训练</button>
        <button class="btn" onclick="app.go('paper')">📝 自由组卷</button>
        <button class="btn secondary" onclick="app.go('records')">🗂 历史记录</button>
        ${s.pending_review ? `<button class="btn" onclick="app.go('review')">🧭 人工复核（${s.pending_review}）</button>` : ""}
      </div>
    </div>
    <div class="card">
      <h2>题型分布</h2>
      <div class="toolbar">${typeChips || '<span class="muted">题库为空，请先导入题目</span>'}</div>
      ${(s.subjects || []).length
        ? `<div class="muted">学科：${(s.subjects || []).map((x) => `${esc(x.subject)}（${x.count}题）`).join("、")}</div>`
        : ""}
    </div>`;
}

async function renderImport() {
  const subjects = await api("/api/subjects");
  view.innerHTML = `
    <div class="card">
      <h2>📚 添加学科题库</h2>
      <p class="muted mb">支持上传文件（.docx / .pdf / .txt）或直接粘贴文本；自动识别标准题目，笔记类内容会归纳为简答/名词解释/判断题。</p>
      <div class="inline">
        <div class="form-row"><label>学科</label>
          <input type="text" id="imp-subject" list="subject-list" placeholder="如：信号与系统">
          <datalist id="subject-list">${subjects.map((s) => `<option value="${esc(s.subject)}">`).join("")}</datalist>
        </div>
        <div class="form-row"><label>课程/来源（可选）</label><input type="text" id="imp-course" placeholder="如：模拟题1"></div>
      </div>
      <div class="form-row">
        <label>上传文件</label>
        <div class="toolbar">
          <input type="file" id="imp-file" accept=".docx,.pdf,.txt,.md" multiple>
          <button class="btn" onclick="app.uploadFile()">上传并识别入库</button>
        </div>
      </div>
      <div class="form-row"><label>题目文本</label><textarea id="imp-text" placeholder="1. 题目内容&#10;A. 选项一&#10;B. 选项二&#10;答案：A&#10;&#10;2. ……"></textarea></div>
      <div class="toolbar">
        <button class="btn green" onclick="app.doImport()">解析并入库</button>
        <span id="imp-result" class="muted"></span>
      </div>
      <div id="imp-preview"></div>
    </div>`;
}

async function doImport() {
  const text = $("#imp-text").value;
  const subject = $("#imp-subject").value.trim();
  const course = $("#imp-course").value.trim();
  if (!text.trim()) { toast("请输入题目文本"); return; }
  try {
    const r = await api("/api/question/import", {
      method: "POST",
      body: JSON.stringify({ text, subject, course }),
    });
    refreshQtypeCounts();
    if (r.inserted === 0 && !(r.preview || []).length) {
      lastImportText = text;
      lastImportSubject = subject;
      lastImportCourse = course;
      $("#imp-result").textContent = "⚠️ 未能解析出题目，可尝试用 AI 整理后再导入";
      $("#imp-preview").innerHTML = `
        <div class="mt"><button class="btn" onclick="app.aiOrganizeFromLast()">✨ 用 AI 整理后重新解析</button></div>`;
    } else {
      showImportResult(r);
      toast("导入完成");
    }
  } catch (e) {
    toast("导入失败：" + e.message);
  }
}

function showImportResult(r) {
  const typeChips = Object.entries(r.by_type || {})
    .map(([k, v]) => `<span class="badge info">${esc(qtypeLabel(k))} ${v}</span>`)
    .join(" ");
  const img = r.image_stats || {};
  let imgLine = "";
  if (img.extracted !== undefined || img.image_map_size !== undefined) {
    const parts = [];
    if (img.extracted !== undefined) parts.push(`提取 ${img.extracted} 张`);
    if (img.usable !== undefined) parts.push(`可用 ${img.usable} 张`);
    if (img.black_skipped !== undefined && img.black_skipped > 0) {
      parts.push(`跳过黑图 ${img.black_skipped} 张`);
    }
    if (img.ocr_used) parts.push("已用 OCR 识别");
    if (img.bound_certain !== undefined) {
      const bound = (img.bound_certain || 0) + (img.bound_uncertain || 0);
      parts.push(`绑定图片 ${bound} 张`);
      if (img.bound_uncertain) parts.push(`${img.bound_uncertain} 张待复核`);
    }
    if (img.unbound) parts.push(`${img.unbound} 张未绑定`);
    if (parts.length) imgLine = `，图片：${parts.join(" / ")}`;
  }
  $("#imp-result").textContent =
    `✅ 新增 ${r.inserted} 题，命中指纹合并 ${r.merged} 题` +
    (r.pending_review ? `，待人工复核 ${r.pending_review} 题` : "") +
    `，题库共 ${r.total} 题${imgLine}`;
  $("#imp-preview").innerHTML = `
    <div class="mt">${typeChips || ""}</div>
    <h3 class="mt">解析预览（前 ${r.preview.length} 条）</h3>
    <div class="table-wrap"><table>
      <tr><th>题型</th><th>题干</th><th>答案</th></tr>
      ${r.preview.map((q) => `
        <tr>
          <td><span class="badge info">${esc(q.qtype_label)}</span></td>
          <td>${richTextBrief(q.question, 180)}${imgHtml(q, "thumb")}</td>
          <td>${richText(q.correct_answer || "（待补充）")}</td>
        </tr>`).join("")}
    </table></div>`;
  renderMath();
}

async function uploadFile() {
  const input = $("#imp-file");
  if (!input.files || !input.files.length) { toast("请先选择文件"); return; }
  const subject = $("#imp-subject").value.trim();
  const course = $("#imp-course").value.trim();
  const files = [...input.files];
  if (files.length === 1) {
    const fd = new FormData();
    fd.append("file", files[0]);
    fd.append("subject", subject);
    fd.append("course", course);
    try {
      const res = await fetch("/api/question/import-file", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "导入失败");
      showImportResult(data);
      refreshQtypeCounts();
      toast("导入完成");
    } catch (e) {
      toast("导入失败：" + e.message);
    }
    return;
  }
  let inserted = 0, merged = 0, failed = 0;
  for (const file of files) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("subject", subject);
    fd.append("course", course);
    try {
      const res = await fetch("/api/question/import-file", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "导入失败");
      inserted += data.inserted || 0;
      merged += data.merged || 0;
    } catch (e) {
      failed++;
      console.error(`导入失败: ${file.name}`, e);
    }
  }
  refreshQtypeCounts();
  toast(failed
    ? `完成：新增 ${inserted} 题，合并 ${merged} 题，${failed} 个文件失败`
    : `批量导入完成：新增 ${inserted} 题，合并 ${merged} 题`);
  input.value = "";
}

async function renderPractice() {
  await loadQtypes(state.qtypeSubject || "");
  const subjects = await api("/api/subjects");
  const qtypes = state.qtypes.filter((t) => t.count > 0);
  view.innerHTML = `
    <div class="card">
      <h2>🎯 专项训练</h2>
      <p class="muted mb">选定学科 + 单题型，系统随机抽题练习。</p>
      <div class="inline">
        <div class="form-row"><label>学科</label>
          <select id="pr-subject" onchange="app.practiceSubjectChanged(this.value)">
            <option value="" ${state.qtypeSubject === "" ? "selected" : ""}>全部学科</option>
            ${subjects.map((s) => `<option value="${esc(s.subject)}" ${state.qtypeSubject === s.subject ? "selected" : ""}>${esc(s.subject)}（${s.count}）</option>`).join("")}
          </select>
        </div>
        <div class="form-row"><label>题型</label>
          <select id="pr-qtype">
            ${qtypes.map((t) => `<option value="${t.value}">${esc(t.label)}（${t.count}）</option>`).join("")}
          </select>
          <span class="muted">数量为当前学科</span>
        </div>
        <div class="form-row"><label>题数</label><input type="number" id="pr-count" value="5" min="0" max="50"></div>
      </div>
      <button class="btn green" onclick="app.startPractice()">开始训练</button>
    </div>`;
}

async function startPractice() {
  try {
    const body = {
      subject: $("#pr-subject").value,
      qtype: $("#pr-qtype").value,
      count: parseInt($("#pr-count").value, 10) || 5,
    };
    const paper = await api("/api/practice/start", { method: "POST", body: JSON.stringify(body) });
    if (!paper.question_count) {
      toast(parseInt($("#pr-count").value, 10) <= 0 ? "题数需至少为 1" : "该题型题库为空，请先导入题目");
      return;
    }
    enterAnswer(paper);
  } catch (e) {
    toast("启动失败：" + e.message);
  }
}

async function renderPaper() {
  await loadQtypes(state.qtypeSubject || "");
  const subjects = await api("/api/subjects");
  const qtypes = state.qtypes;
  view.innerHTML = `
    <div class="card">
      <h2>📝 自由组卷</h2>
      <p class="muted mb">自选学科、各题型数量与分值，生成试卷并保存。</p>
      <div class="inline">
        <div class="form-row"><label>试卷标题</label><input type="text" id="pp-title" value="自由组卷"></div>
        <div class="form-row"><label>学科</label>
          <select id="pp-subject" onchange="app.paperSubjectChanged(this.value)">
            <option value="" ${state.qtypeSubject === "" ? "selected" : ""}>全部学科</option>
            ${subjects.map((s) => `<option value="${esc(s.subject)}" ${state.qtypeSubject === s.subject ? "selected" : ""}>${esc(s.subject)}</option>`).join("")}
          </select>
        </div>
      </div>
      <div class="toolbar">
        <span class="muted">快速模板：</span>
        ${Object.keys(TEMPLATE_PRESETS).map((name) => `<button class="btn sm secondary" onclick="app.applyTemplate('${name}')">${name}</button>`).join("")}
      </div>
      <div class="sections-grid" id="pp-sections">
        ${qtypes.map((t) => `
          <div class="section-item">
            <div class="sec-name">${esc(t.label)} <span class="muted">现有 ${t.count}</span></div>
            <label class="muted">数量 <input type="number" id="sec-count-${t.value}" value="0" min="0" max="200"></label>
            <label class="muted">分值 <input type="number" id="sec-score-${t.value}" value="5" min="0" step="0.5"></label>
          </div>`).join("")}
      </div>
      <div class="mt">
        <button class="btn green" onclick="app.generatePaper()">生成试卷并答题</button>
        <span id="pp-result" class="muted"></span>
      </div>
    </div>`;
}

function applyTemplate(name) {
  const preset = TEMPLATE_PRESETS[name];
  for (const t of state.qtypes) {
    const countEl = document.getElementById(`sec-count-${t.value}`);
    const scoreEl = document.getElementById(`sec-score-${t.value}`);
    const found = preset.find((p) => p[0] === t.value);
    if (found) {
      countEl.value = found[1];
      scoreEl.value = found[2];
    } else {
      countEl.value = 0;
    }
  }
}

async function generatePaper() {
  const sections = state.qtypes
    .map((t) => ({
      qtype: t.value,
      count: parseInt(document.getElementById(`sec-count-${t.value}`).value, 10) || 0,
      score: parseFloat(document.getElementById(`sec-score-${t.value}`).value) || 5,
    }))
    .filter((s) => s.count > 0);
  if (!sections.length) { toast("请至少配置一个题型数量"); return; }
  try {
    const paper = await api("/api/paper/generate", {
      method: "POST",
      body: JSON.stringify({
        title: $("#pp-title").value || "自由组卷",
        subject: $("#pp-subject").value,
        sections,
      }),
    });
    if (!paper.question_count) { toast("没有抽到题目（题库不足或为空）"); return; }
    enterAnswer(paper);
  } catch (e) {
    toast("生成失败：" + e.message);
  }
}

/* ---------------- 答题 ---------------- */

function enterAnswer(paper) {
  state.paper = paper;
  state.answers = {};
  state.index = 0;
  state.view = "answer";
  render();
}

function renderAnswer() {
  const paper = state.paper;
  const item = paper.questions[state.index];
  const q = item.question;
  const total = paper.questions.length;
  const key = q.id;
  const val = state.answers[key] || "";

  let inputHtml = "";
  if (q.qtype === "single_choice" && q.options.length) {
    inputHtml = `<div class="q-options">${q.options.map((o, i) => {
      const letter = optionLetters(q.options.length)[i];
      return `<label class="q-option ${val === letter ? "selected" : ""}">
        <input type="radio" name="ans" value="${letter}" ${val === letter ? "checked" : ""} onchange="app.setAnswer(${key}, this.value)">
        <span><b>${letter}.</b> ${richText(o)}</span></label>`;
    }).join("")}</div>`;
  } else if (q.qtype === "multiple_choice" && q.options.length) {
    const cur = val ? val.split("") : [];
    inputHtml = `<div class="q-options">${q.options.map((o, i) => {
      const letter = optionLetters(q.options.length)[i];
      return `<label class="q-option ${cur.includes(letter) ? "selected" : ""}">
        <input type="checkbox" value="${letter}" ${cur.includes(letter) ? "checked" : ""} onchange="app.toggleMulti(${key}, this)">
        <span><b>${letter}.</b> ${richText(o)}</span></label>`;
    }).join("")}</div>`;
  } else if (q.qtype === "judge") {
    inputHtml = `<div class="q-options">
      <label class="q-option ${val === "对" ? "selected" : ""}"><input type="radio" name="ans" value="对" ${val === "对" ? "checked" : ""} onchange="app.setAnswer(${key}, this.value)"><span>对（正确）</span></label>
      <label class="q-option ${val === "错" ? "selected" : ""}"><input type="radio" name="ans" value="错" ${val === "错" ? "checked" : ""} onchange="app.setAnswer(${key}, this.value)"><span>错（错误）</span></label>
    </div>`;
  } else {
    inputHtml = `<div class="form-row"><textarea id="ans-text-${key}" placeholder="请输入你的答案" rows="4">${esc(val)}</textarea></div>`;
  }

  view.innerHTML = `
    <div class="card">
      <div class="toolbar">
        <h2 style="flex:1">${esc(paper.title)}</h2>
        <span class="badge info">第 ${state.index + 1} / ${total} 题</span>
      </div>
      <div class="progress"><div style="width:${Math.round(((state.index + 1) / total) * 100)}%"></div></div>
      <div class="question-card">
        <div class="q-stem">
          <span class="badge info">${esc(q.qtype_label || qtypeLabel(q.qtype))}</span>
          <span class="badge pending">${item.score} 分</span>
          <div class="mt">${richText(q.question)}</div>
          ${imgHtml(q)}
        </div>
        ${inputHtml}
      </div>
      <div class="pager">
        <button class="btn secondary" ${state.index === 0 ? "disabled" : ""} onclick="app.prevQ()">上一题</button>
        ${state.index < total - 1
          ? `<button class="btn" onclick="app.nextQ()">下一题</button>`
          : `<button class="btn green" onclick="app.submitPaper()">提交试卷</button>`}
      </div>
    </div>`;
  renderMath();
  if (inputHtml.includes("textarea")) {
    const ta = document.getElementById(`ans-text-${key}`);
    ta.addEventListener("input", (e) => (state.answers[key] = e.target.value));
  }
}

function setAnswer(qid, value) {
  state.answers[qid] = value;
  renderAnswer();
}

function toggleMulti(qid, el) {
  const cur = new Set((state.answers[qid] || "").split(""));
  if (el.checked) cur.add(el.value);
  else cur.delete(el.value);
  state.answers[qid] = [...cur].sort().join("");
  renderAnswer();
}

function nextQ() {
  if (state.index < state.paper.questions.length - 1) {
    state.index += 1;
    renderAnswer();
  }
}

function prevQ() {
  if (state.index > 0) {
    state.index -= 1;
    renderAnswer();
  }
}

async function submitPaper() {
  const answers = state.paper.questions.map((pq) => ({
    question_id: pq.question.id,
    user_answer: state.answers[pq.question.id] || "",
  }));
  try {
    const r = await api("/api/submit", {
      method: "POST",
      body: JSON.stringify({ paper_id: state.paper.paper_id, answers }),
    });
    state.result = r;
    state.view = "result";
    render();
  } catch (e) {
    toast("提交失败：" + e.message);
  }
}

/* ---------------- 结果 ---------------- */

function renderResult() {
  const r = state.result;
  const rows = r.details.map((d, i) => {
    const badge = `<span class="badge ${d.status}">${d.status === "correct" ? "正确" : d.status === "wrong" ? "错误" : "待补充"}</span>`;
    const fillBtn = d.status === "pending"
      ? `<button class="btn sm green" onclick="app.fillAnswer(${d.question_id})">补充答案</button>` : "";
    return `
      <div class="question-card">
        <div class="q-stem"><b>${i + 1}.</b> ${esc(d.question)}</div>
        <div class="muted">你的答案：${esc(d.user_answer || "（未作答）")}</div>
        <div class="muted">参考答案：${richText(d.correct_answer)}</div>
        <div class="muted">${badge} 得分：${d.score}　${esc(d.comment || "")}</div>
        ${d.explanation ? `<div class="muted">解析：${esc(d.explanation)}</div>` : ""}
        <div class="mt">${fillBtn}</div>
      </div>`;
  }).join("");

  view.innerHTML = `
    <div class="card center">
      <h2>${r.status === "graded" ? "✅ 判卷完成" : "⚠️ 部分题目待补充答案"}</h2>
      <div class="stats-grid mt">
        <div class="stat-card"><div class="num">${r.score} / ${r.total_score}</div><div class="lbl">得分</div></div>
        <div class="stat-card"><div class="num" style="color:var(--green)">${r.correct_count}</div><div class="lbl">正确</div></div>
        <div class="stat-card"><div class="num" style="color:var(--red)">${r.wrong_count}</div><div class="lbl">错误</div></div>
        <div class="stat-card"><div class="num" style="color:var(--amber)">${r.pending_count}</div><div class="lbl">待补充</div></div>
      </div>
      <div class="toolbar center mt" style="justify-content:center">
        <button class="btn" onclick="app.go('records')">查看历史记录</button>
        <button class="btn secondary" onclick="app.go('home')">返回首页</button>
      </div>
    </div>
    <div class="card">${rows}</div>`;
}

function fillAnswer(qid) {
  openModal(`
    <h3>补充参考答案</h3>
    <div class="form-row"><label>标准答案</label><input type="text" id="fill-answer" placeholder="如：A 或 42"></div>
    <div class="form-row"><label>解析（可选）</label><textarea id="fill-explain" rows="3"></textarea></div>
    <div class="modal-actions">
      <button class="btn secondary" onclick="app.closeModal()">取消</button>
      <button class="btn green" onclick="app.saveAnswer(${qid})">保存</button>
    </div>`);
}

async function saveAnswer(qid) {
  const answer = $("#fill-answer").value.trim();
  const explanation = $("#fill-explain").value.trim();
  if (!answer) { toast("答案不能为空"); return; }
  try {
    await api(`/api/question/${qid}/answer`, {
      method: "POST",
      body: JSON.stringify({ answer, explanation }),
    });
    closeModal();
    toast("答案已补充到题库 ✅");
    const rid = state.result.record_id;
    const rec = await api(`/api/record/${rid}`);
    state.result = {
      record_id: rec.id,
      score: rec.score,
      total_score: rec.total_score,
      correct_count: rec.correct_count,
      wrong_count: rec.wrong_count,
      pending_count: rec.pending_count,
      status: rec.status,
      details: rec.answers,
    };
    renderResult();
  } catch (e) {
    toast("保存失败：" + e.message);
  }
}

/* ---------------- 题库管理 ---------------- */

async function renderBank() {
  const params = new URLSearchParams();
  if (state.bank.subject) params.set("subject", state.bank.subject);
  if (state.bank.qtype) params.set("qtype", state.bank.qtype);
  if (state.bank.search) params.set("search", state.bank.search);
  params.set("page", state.bank.page);
  params.set("page_size", "20");
  const data = await api(`/api/questions?${params.toString()}`);
  const subjects = await api("/api/subjects");

  const rows = data.items.map((q) => `
    <tr>
      <td><input type="checkbox" class="q-check" value="${q.id}" onchange="app.updateBankSelection()"></td>
      <td>${q.id}</td>
      <td>${esc(q.subject)}</td>
      <td><span class="badge info">${esc(q.qtype_label)}</span></td>
      <td>${richTextBrief(q.question, 120)}${imgHtml(q, "thumb")}</td>
      <td>${richText(q.correct_answer || "（待补充）")}</td>
      <td>
        <button class="btn sm secondary" onclick="app.viewQuestion(${q.id})">查看</button>
        <button class="btn sm green" onclick="app.fillAnswer(${q.id})">补答案</button>
        <button class="btn sm" onclick="app.openVariants(${q.id})">变式</button>
        <button class="btn sm danger" onclick="app.deleteQuestion(${q.id})">删除</button>
      </td>
    </tr>`).join("");

  view.innerHTML = `
    <div class="card">
      <h2>📖 题库管理</h2>
      <div class="toolbar">
        <select onchange="state.bank.subject=this.value; state.bank.page=1; app.go('bank')">
          <option value="">全部学科</option>
          ${subjects.map((s) => `<option value="${esc(s.subject)}" ${state.bank.subject === s.subject ? "selected" : ""}>${esc(s.subject)}</option>`).join("")}
        </select>
        <select onchange="state.bank.qtype=this.value; state.bank.page=1; app.go('bank')">
          <option value="">全部题型</option>
          ${state.qtypes.map((t) => `<option value="${t.value}" ${state.bank.qtype === t.value ? "selected" : ""}>${esc(t.label)}</option>`).join("")}
        </select>
        <input type="text" placeholder="搜索题干/知识点" value="${esc(state.bank.search)}" onchange="state.bank.search=this.value; state.bank.page=1; app.go('bank')">
        <button class="btn sm danger" id="batch-delete-btn" onclick="app.deleteSelected()" disabled>批量删除</button>
        <button class="btn" onclick="app.go('import')">＋ 导入题目</button>
      </div>
      <div class="table-wrap">
        <table>
          <tr><th><input type="checkbox" id="check-all" onchange="app.toggleSelectAll(this)"></th><th>ID</th><th>学科</th><th>题型</th><th>题干</th><th>答案</th><th>操作</th></tr>
          ${rows || '<tr><td colspan="7" class="empty">暂无题目</td></tr>'}
        </table>
      </div>
      <div class="pager">
        <button class="btn sm secondary" ${data.page <= 1 ? "disabled" : ""} onclick="state.bank.page--; app.go('bank')">上一页</button>
        <span class="muted">第 ${data.page} 页 / 共 ${Math.max(1, Math.ceil(data.total / 20))} 页（${data.total} 题）</span>
        <button class="btn sm secondary" ${data.page >= Math.ceil(data.total / 20) ? "disabled" : ""} onclick="state.bank.page++; app.go('bank')">下一页</button>
      </div>
    </div>`;
  renderMath();
  updateBankSelection();
}

async function viewQuestion(qid) {
  const q = await api(`/api/question/${qid}`);
  openModal(`
    <h3>题目 #${q.id}　<span class="badge info">${esc(q.qtype_label)}</span></h3>
    <div class="detail-row"><div class="tag">学科/课程：</div>${esc(q.subject)} / ${esc(q.course || "-")}</div>
    <div class="detail-row"><div class="tag">题干：</div><div>${richText(q.question)}</div></div>
    ${imgHtml(q)}
    ${formulaHtml(q)}
    ${q.options.length ? `<div class="detail-row"><div class="tag">选项：</div><div>${q.options.map((o, i) => `<div>${optionLetters(q.options.length)[i]}. ${richText(o)}</div>`).join("")}</div></div>` : ""}
    <div class="detail-row"><div class="tag">答案：</div>${richText(q.correct_answer || "（待补充）")}</div>
    ${q.explanation ? `<div class="detail-row"><div class="tag">解析：</div><pre>${esc(q.explanation)}</pre></div>` : ""}
    <div class="modal-actions"><button class="btn secondary" onclick="app.closeModal()">关闭</button></div>`);
  renderMath();
}

async function deleteQuestion(qid) {
  if (!confirm("确定删除这道题吗？")) return;
  try {
    await api(`/api/question/${qid}`, { method: "DELETE" });
    refreshQtypeCounts();
    toast("已删除");
    renderBank();
  } catch (e) {
    toast("删除失败：" + e.message);
  }
}

function selectedIds() {
  return [...document.querySelectorAll(".q-check:checked")].map((c) => Number(c.value));
}

function updateBankSelection() {
  const btn = $("#batch-delete-btn");
  if (!btn) return;
  const n = selectedIds().length;
  btn.disabled = n === 0;
  btn.textContent = n ? `批量删除（${n}）` : "批量删除";
}

function toggleSelectAll(el) {
  document.querySelectorAll(".q-check").forEach((c) => { c.checked = el.checked; });
  updateBankSelection();
}

async function deleteSelected() {
  const ids = selectedIds();
  if (!ids.length) return;
  if (!confirm(`确定删除选中的 ${ids.length} 道题吗？`)) return;
  try {
    const r = await api("/api/question/batch-delete", {
      method: "POST",
      body: JSON.stringify({ ids }),
    });
    refreshQtypeCounts();
    toast(`已删除 ${r.deleted} 道题`);
    renderBank();
  } catch (e) {
    toast("删除失败：" + e.message);
  }
}

async function openVariants(qid) {
  openModal(`
    <h3>生成变式题</h3>
    <p class="muted">基于该题用 AI 生成同考点变式，确认后勾选入库。</p>
    <div class="form-row"><label>数量</label><input type="number" id="var-count" value="3" min="1" max="10"></div>
    <div id="var-list" class="mt"></div>
    <div class="modal-actions">
      <button class="btn secondary" onclick="app.closeModal()">取消</button>
      <button class="btn green" id="var-go" onclick="app.generateVariants(${qid})">生成</button>
    </div>`);
}

async function generateVariants(qid) {
  const count = Number($("#var-count").value) || 3;
  const btn = $("#var-go");
  btn.disabled = true;
  btn.textContent = "生成中…";
  try {
    const r = await api(`/api/question/${qid}/variants`, {
      method: "POST",
      body: JSON.stringify({ count }),
    });
    const items = r.items || [];
    if (!items.length) throw new Error("没有生成到题目");
    $("#var-list").innerHTML = `
      <div class="table-wrap"><table>
        <tr><th>选</th><th>题干</th><th>答案</th></tr>
        ${items.map((it, i) => `
          <tr>
            <td><input type="checkbox" class="var-check" value="${i}" checked></td>
            <td>${esc(it.question)}${it.options.length ? `<div class="muted">${it.options.map(esc).join("；")}</div>` : ""}</td>
            <td>${richText(it.correct_answer)}</td>
          </tr>`).join("")}
      </table></div>`;
    btn.textContent = "勾选后入库";
    btn.onclick = () => app.importVariants(qid, items);
  } catch (e) {
    toast("生成失败：" + e.message);
    btn.disabled = false;
    btn.textContent = "重试";
  }
}

async function importVariants(qid, items) {
  const checked = [...document.querySelectorAll(".var-check:checked")].map((c) => Number(c.value));
  const selected = checked.map((i) => items[i]).filter(Boolean);
  if (!selected.length) { toast("请至少勾选一条"); return; }
  try {
    const q = await api(`/api/question/${qid}`);
    const r = await api("/api/variants/import", {
      method: "POST",
      body: JSON.stringify({
        items: selected.map((it) => ({
          question: it.question,
          options: it.options,
          correct_answer: it.correct_answer,
          explanation: it.explanation,
          qtype: q.qtype,
          subject: q.subject,
          course: q.course,
          topic: q.topic,
        })),
        source_file: `变式-题目${qid}`,
      }),
    });
    refreshQtypeCounts();
    toast(`已入库 ${r.inserted} 题`);
    closeModal();
    renderBank();
  } catch (e) {
    toast("入库失败：" + e.message);
  }
}

async function aiOrganize(text, subject, course) {
  toast("AI 整理中，可能需要十几秒…");
  try {
    const r = await api("/api/question/ai-organize", {
      method: "POST",
      body: JSON.stringify({ text, subject, course }),
    });
    $("#imp-text").value = r.organized_text;
    toast("整理完成，请确认后点击“解析并入库”");
  } catch (e) {
    toast("AI 整理失败：" + e.message);
  }
}

async function aiOrganizeFromLast() {
  if (!lastImportText) { toast("没有可整理的文本"); return; }
  await aiOrganize(lastImportText, lastImportSubject, lastImportCourse);
}

/* ---------------- 历史记录 ---------------- */

/* ---------------- 人工复核（残缺标记） ---------------- */

async function renderReview() {
  const params = new URLSearchParams();
  params.set("page", state.review.page);
  params.set("page_size", "20");
  const data = await api(`/api/admin/pending-questions?${params.toString()}`);
  const cards = data.items.map((q) => `
    <div class="question-card">
      <div class="q-stem">
        <span class="badge info">${esc(q.subject)}</span>
        <span class="badge info">${esc(q.qtype_label)}</span>
        <span class="badge pending">待复核</span>
        <span class="muted">#${q.id} · ${esc(q.source_file || "-")}</span>
      </div>
      <div class="mt">${richText(q.question)}</div>
      ${imgHtml(q)}
      <div class="img-manager mt">
        <div class="img-chips">
          ${(q.images || []).map((p) => {
            const name = String(p).split(/[\\/]/).pop();
            return `
            <span class="img-chip">
              ${imgTag(name, "chip")}
              <button class="btn sm secondary" onclick="app.insertImageAnchor(${q.id}, '${esc(name)}')">插题干</button>
              <button class="btn sm danger" onclick="app.removeQuestionImage(${q.id}, '${esc(name)}')">删</button>
            </span>`;
          }).join("")}
          ${(q.images || []).length ? "" : '<span class="muted">未绑定图片</span>'}
        </div>
        <div class="toolbar mt">
          <input type="file" accept="image/*" id="img-up-${q.id}">
          <button class="btn sm" onclick="app.uploadQuestionImage(${q.id})">上传并绑定</button>
        </div>
      </div>
      ${formulaHtml(q)}
      ${q.options.length ? `<div class="mt muted">${q.options.map((o, i) => `${optionLetters(q.options.length)[i]}. ${richText(o)}`).join("<br>")}</div>` : ""}
      <div class="mt muted">参考答案：${richText(q.correct_answer || "（待补充）")}</div>
      ${q.explanation ? `<div class="muted">解析：${esc(q.explanation)}</div>` : ""}
      <div class="toolbar mt">
        <button class="btn green sm" onclick="app.openResolveModal(${q.id})">补全并确认对齐</button>
        <button class="btn secondary sm" onclick="app.clearPending(${q.id})">直接确认对齐</button>
      </div>
    </div>`).join("");

  view.innerHTML = `
    <div class="card">
      <div class="toolbar">
        <h2 style="flex:1">🧭 人工复核</h2>
        <span class="muted">共 ${data.total} 题待复核</span>
      </div>
      <p class="muted mb">这些题目包含 <span class="ph-mark">&lt;Formula&gt;</span> / <span class="ph-mark">&lt;ImgRef&gt;</span> 占位符，请对照原始 PDF 补全公式或题干后点击“确认对齐”。</p>
      ${cards || '<div class="empty">🎉 没有待复核题目</div>'}
      <div class="pager">
        <button class="btn sm secondary" ${data.page <= 1 ? "disabled" : ""} onclick="state.review.page--; app.go('review')">上一页</button>
        <span class="muted">第 ${data.page} 页 / 共 ${Math.max(1, Math.ceil(data.total / 20))} 页</span>
        <button class="btn sm secondary" ${data.page >= Math.ceil(data.total / 20) ? "disabled" : ""} onclick="state.review.page++; app.go('review')">下一页</button>
      </div>
    </div>`;
  renderMath();
}

async function openResolveModal(qid) {
  const q = await api(`/api/question/${qid}`);
  openModal(`
    <h3>复核补全 #${q.id}</h3>
    <p class="muted mb">对照原始 PDF，把占位符替换为完整内容后保存。</p>
    <div class="form-row"><label>题干</label><textarea id="rs-question" rows="4">${esc(q.question)}</textarea></div>
    <div class="form-row"><label>公式（LaTeX）</label><input type="text" id="rs-formula" value="${esc(q.formula)}"></div>
    <div class="form-row"><label>标准答案</label><input type="text" id="rs-answer" value="${esc(q.correct_answer)}"></div>
    <div class="form-row"><label>解析（可选）</label><textarea id="rs-explain" rows="3">${esc(q.explanation)}</textarea></div>
    <div class="modal-actions">
      <button class="btn secondary" onclick="app.closeModal()">取消</button>
      <button class="btn green" onclick="app.resolvePending(${q.id})">保存并确认对齐</button>
    </div>`);
}

async function resolvePending(qid) {
  const body = {
    question: $("#rs-question").value.trim(),
    formula: $("#rs-formula").value.trim(),
    answer: $("#rs-answer").value.trim(),
    explanation: $("#rs-explain").value.trim(),
  };
  try {
    await api(`/api/admin/pending/${qid}/resolve`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    closeModal();
    toast("已确认对齐 ✅");
    renderReview();
  } catch (e) {
    toast("保存失败：" + e.message);
  }
}

async function clearPending(qid) {
  try {
    await api(`/api/admin/pending/${qid}/clear`, { method: "POST" });
    toast("已确认对齐 ✅");
    renderReview();
  } catch (e) {
    toast("操作失败：" + e.message);
  }
}

async function uploadQuestionImage(qid) {
  const input = document.getElementById(`img-up-${qid}`);
  const file = input && input.files && input.files[0];
  if (!file) { toast("请先选择图片"); return; }
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/images/upload", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "上传失败");
    const q = await api(`/api/question/${qid}`);
    const names = [...(q.images || []), data.name];
    await api(`/api/question/${qid}/images`, {
      method: "PUT",
      body: JSON.stringify({ images: names }),
    });
    toast("图片已上传并绑定 ✅");
    renderReview();
  } catch (e) {
    toast("上传失败：" + e.message);
  }
}

async function removeQuestionImage(qid, name) {
  try {
    const q = await api(`/api/question/${qid}`);
    const names = (q.images || []).filter((n) => n !== name);
    const question = String(q.question || "").split(`【图:${name}】`).join("");
    await api(`/api/question/${qid}/images`, {
      method: "PUT",
      body: JSON.stringify({ images: names, question }),
    });
    toast("图片已移除 ✅");
    renderReview();
  } catch (e) {
    toast("操作失败：" + e.message);
  }
}

async function insertImageAnchor(qid, name) {
  try {
    const q = await api(`/api/question/${qid}`);
    const question = String(q.question || "").trim() + `【图:${name}】`;
    await api(`/api/question/${qid}/images`, {
      method: "PUT",
      body: JSON.stringify({ images: q.images, question }),
    });
    toast("已插入题干锚点 ✅");
    renderReview();
  } catch (e) {
    toast("操作失败：" + e.message);
  }
}

async function renderRecords() {
  const params = new URLSearchParams();
  if (state.records.subject) params.set("subject", state.records.subject);
  if (state.records.status) params.set("status", state.records.status);
  params.set("page", state.records.page);
  params.set("page_size", "20");
  const data = await api(`/api/records?${params.toString()}`);
  const subjects = await api("/api/subjects");

  const rows = data.items.map((r) => `
    <tr>
      <td>${r.id}</td>
      <td>${esc(r.title)}</td>
      <td>${esc(r.subject)}</td>
      <td>${r.score} / ${r.total_score}</td>
      <td>${r.correct_count} / ${r.wrong_count} / ${r.pending_count}</td>
      <td><span class="badge ${r.status === "graded" ? "correct" : "pending"}">${r.status === "graded" ? "已判" : "待补充"}</span></td>
      <td>${esc(r.created_at)}</td>
      <td>
        <button class="btn sm secondary" onclick="app.viewRecord(${r.id})">详情</button>
        <a class="btn sm secondary" href="/api/record/${r.id}/export?format=json" target="_blank">JSON</a>
        <a class="btn sm secondary" href="/api/record/${r.id}/export?format=csv" target="_blank">CSV</a>
      </td>
    </tr>`).join("");

  view.innerHTML = `
    <div class="card">
      <h2>🗂 历史记录</h2>
      <div class="toolbar">
        <select onchange="state.records.subject=this.value; state.records.page=1; app.go('records')">
          <option value="">全部学科</option>
          ${subjects.map((s) => `<option value="${esc(s.subject)}" ${state.records.subject === s.subject ? "selected" : ""}>${esc(s.subject)}</option>`).join("")}
        </select>
        <select onchange="state.records.status=this.value; state.records.page=1; app.go('records')">
          <option value="">全部状态</option>
          <option value="graded" ${state.records.status === "graded" ? "selected" : ""}>已判</option>
          <option value="pending" ${state.records.status === "pending" ? "selected" : ""}>待补充</option>
        </select>
      </div>
      <div class="table-wrap">
        <table>
          <tr><th>ID</th><th>试卷</th><th>学科</th><th>得分</th><th>对/错/待</th><th>状态</th><th>时间</th><th>操作</th></tr>
          ${rows || '<tr><td colspan="8" class="empty">暂无记录</td></tr>'}
        </table>
      </div>
      <div class="pager">
        <button class="btn sm secondary" ${data.page <= 1 ? "disabled" : ""} onclick="state.records.page--; app.go('records')">上一页</button>
        <span class="muted">第 ${data.page} 页 / 共 ${Math.max(1, Math.ceil(data.total / 20))} 页（${data.total} 条）</span>
        <button class="btn sm secondary" ${data.page >= Math.ceil(data.total / 20) ? "disabled" : ""} onclick="state.records.page++; app.go('records')">下一页</button>
      </div>
    </div>`;
}

async function viewRecord(rid) {
  const r = await api(`/api/record/${rid}`);
  const rows = r.answers.map((d, i) => `
    <div class="detail-row">
      <div class="tag">${i + 1}. <span class="badge ${d.status}">${d.status === "correct" ? "正确" : d.status === "wrong" ? "错误" : "待补充"}</span> 得分 ${d.score}</div>
      <div>${esc(d.question)}</div>
      <div class="muted">作答：${richText(d.user_answer || "（未作答）")}　参考答案：${richText(d.correct_answer)}</div>
      ${d.comment ? `<div class="muted">${esc(d.comment)}</div>` : ""}
    </div>`).join("");
  openModal(`
    <h3>记录 #${r.id}　${esc(r.title)}</h3>
    <div class="muted mb">学科：${esc(r.subject)}　时间：${esc(r.created_at)}</div>
    <div class="stats-grid mb">
      <div class="stat-card"><div class="num">${r.score}/${r.total_score}</div><div class="lbl">得分</div></div>
      <div class="stat-card"><div class="num" style="color:var(--green)">${r.correct_count}</div><div class="lbl">正确</div></div>
      <div class="stat-card"><div class="num" style="color:var(--red)">${r.wrong_count}</div><div class="lbl">错误</div></div>
      <div class="stat-card"><div class="num" style="color:var(--amber)">${r.pending_count}</div><div class="lbl">待补充</div></div>
    </div>
    ${rows}
    <div class="modal-actions">
      <a class="btn secondary" href="/api/record/${r.id}/export?format=json" target="_blank">导出 JSON</a>
      <a class="btn secondary" href="/api/record/${r.id}/export?format=csv" target="_blank">导出 CSV</a>
      <button class="btn" onclick="app.closeModal()">关闭</button>
    </div>`);
}

/* ---------------- 路由 ---------------- */

async function render() {
  document.querySelectorAll(".nav-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === state.view));
  view.innerHTML = '<div class="center muted" style="padding:60px">加载中…</div>';
  try {
    if (state.view === "home") await renderHome();
    else if (state.view === "import") await renderImport();
    else if (state.view === "practice") await renderPractice();
    else if (state.view === "paper") await renderPaper();
    else if (state.view === "bank") await renderBank();
    else if (state.view === "review") await renderReview();
    else if (state.view === "records") await renderRecords();
    else if (state.view === "answer") renderAnswer();
    else if (state.view === "result") renderResult();
  } catch (e) {
    view.innerHTML = `<div class="card"><h2>加载失败</h2><p class="muted">${esc(e.message)}</p></div>`;
  }
}

function go(name) {
  const from = state.view;
  state.view = name;
  // 只有真正切换视图时才重置页码；同一视图内翻页（上一页/下一页）保留当前页
  if (name === "bank" && from !== "bank") state.bank.page = 1;
  if (name === "records" && from !== "records") state.records.page = 1;
  render();
}

document.querySelectorAll(".nav-btn").forEach((btn) =>
  btn.addEventListener("click", () => go(btn.dataset.view)));

window.app = {
  go, closeModal, doImport, startPractice, applyTemplate, generatePaper,
  enterAnswer, setAnswer, toggleMulti, nextQ, prevQ, submitPaper,
  fillAnswer, saveAnswer, viewQuestion, deleteQuestion, viewRecord, uploadFile,
  updateBankSelection, toggleSelectAll, deleteSelected,
  openVariants, generateVariants, importVariants,
  aiOrganize, aiOrganizeFromLast,
  openResolveModal, resolvePending, clearPending,
  uploadQuestionImage, removeQuestionImage, insertImageAnchor,
  practiceSubjectChanged, paperSubjectChanged,
};

loadQtypes().then(render);
