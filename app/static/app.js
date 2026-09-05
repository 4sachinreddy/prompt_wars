// MedLens Frontend Application Logic

let currentRecord = {
  patient: null,
  reports: [],
  lab_tests: [],
  inconsistencies: [],
  summary: ""
};

let activeFilter = "all";

// Document Elements
const patientNameInput = document.getElementById("patient-name");
const patientAgeInput = document.getElementById("patient-age");
const patientSexInput = document.getElementById("patient-sex");
const patientSymptomsInput = document.getElementById("patient-symptoms");
const patientConditionsInput = document.getElementById("patient-conditions");
const patientAllergiesInput = document.getElementById("patient-allergies");
const patientMedsInput = document.getElementById("patient-medications");
const patientNotesInput = document.getElementById("patient-notes");

const formPatientIntake = document.getElementById("form-patient-intake");
const fileReportUpload = document.getElementById("file-report-upload");
const docFilename = document.getElementById("doc-filename");
const sourcePreview = document.getElementById("source-preview");

const statTotal = document.getElementById("stat-total");
const statHigh = document.getElementById("stat-high");
const statLow = document.getElementById("stat-low");
const statNormal = document.getElementById("stat-normal");
const statConflicts = document.getElementById("stat-conflicts");

const conflictSection = document.getElementById("conflict-section");
const conflictList = document.getElementById("conflict-list");
const conflictCountBadge = document.getElementById("conflict-count-badge");

const labTableBody = document.getElementById("lab-table-body");
const summaryContent = document.getElementById("summary-content");

const modalVerify = document.getElementById("modal-verify");
const modalSnippet = document.getElementById("modal-snippet");
const snippetDisplay = document.getElementById("snippet-display");

// Modal Elements
const editItemId = document.getElementById("edit-item-id");
const editTestName = document.getElementById("edit-test-name");
const editValue = document.getElementById("edit-value");
const editUnit = document.getElementById("edit-unit");
const editRefLow = document.getElementById("edit-ref-low");
const editRefHigh = document.getElementById("edit-ref-high");
const editSnippetText = document.getElementById("edit-snippet-text");
const editVerifiedBy = document.getElementById("edit-verified-by");
const formVerifyItem = document.getElementById("form-verify-item");

// Init on load
document.addEventListener("DOMContentLoaded", () => {
  fetchRecord();
  setupEventListeners();
  if (window.lucide) lucide.createIcons();
});

function setupEventListeners() {
  // Demo Case Button
  document.getElementById("btn-load-sample").addEventListener("click", async () => {
    try {
      const btn = document.getElementById("btn-load-sample");
      btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Loading...`;
      if (window.lucide) lucide.createIcons();

      const res = await fetch("/api/load-sample", { method: "POST" });
      if (!res.ok) throw new Error("Failed to load sample");
      currentRecord = await res.json();
      renderAll();
    } catch (err) {
      alert("Error loading sample data: " + err.message);
    } finally {
      const btn = document.getElementById("btn-load-sample");
      btn.innerHTML = `<i data-lucide="sparkles" class="w-4 h-4"></i> <span>⚡ Load Demo Case</span>`;
      if (window.lucide) lucide.createIcons();
    }
  });

  // Reset Button
  document.getElementById("btn-clear-record").addEventListener("click", async () => {
    if (confirm("Reset clinical record session?")) {
      const res = await fetch("/api/clear", { method: "POST" });
      currentRecord = await res.json();
      resetForms();
      renderAll();
    }
  });

  // Print Record
  document.getElementById("btn-print-record").addEventListener("click", () => {
    window.print();
  });

  // Copy Summary
  document.getElementById("btn-copy-summary").addEventListener("click", () => {
    if (currentRecord.summary) {
      navigator.clipboard.writeText(currentRecord.summary);
      alert("Summary copied to clipboard!");
    }
  });

  // Patient Intake Form Submit
  formPatientIntake.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      name: patientNameInput.value.trim(),
      age: parseInt(patientAgeInput.value) || 0,
      sex: patientSexInput.value,
      symptoms: patientSymptomsInput.value.split(",").map(s => s.trim()).filter(Boolean),
      existing_conditions: patientConditionsInput.value.split(",").map(s => s.trim()).filter(Boolean),
      allergies: patientAllergiesInput.value.split(",").map(s => s.trim()).filter(Boolean),
      current_medications: patientMedsInput.value.split(",").map(s => s.trim()).filter(Boolean),
      notes: patientNotesInput.value.trim(),
      provenance: "USER_PROVIDED"
    };

    try {
      const res = await fetch("/api/intake", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error("Failed to save intake");
      currentRecord = await res.json();
      renderAll();
    } catch (err) {
      alert("Error saving patient intake: " + err.message);
    }
  });

  // File Report Upload
  fileReportUpload.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      docFilename.textContent = "Processing " + file.name + "...";
      const res = await fetch("/api/upload-report", {
        method: "POST",
        body: formData
      });
      if (!res.ok) throw new Error("Upload and processing failed.");
      currentRecord = await res.json();
      renderAll();
    } catch (err) {
      alert("Error processing report: " + err.message);
      docFilename.textContent = "Error loading report";
    } finally {
      fileReportUpload.value = "";
    }
  });

  // Filter Buttons
  document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      document.querySelectorAll(".filter-btn").forEach(b => {
        b.className = "filter-btn px-2.5 py-1 rounded-md bg-white border border-slate-200 text-slate-600 hover:bg-slate-100";
      });
      e.target.className = "filter-btn px-2.5 py-1 rounded-md bg-slate-900 font-semibold text-white";
      activeFilter = e.target.dataset.filter;
      renderLabTable();
    });
  });

  // HITL Form Submit
  formVerifyItem.addEventListener("submit", async (e) => {
    e.preventDefault();
    const itemId = editItemId.value;
    const payload = {
      item_id: itemId,
      test_name: editTestName.value.trim(),
      value: editValue.value !== "" ? parseFloat(editValue.value) : null,
      unit: editUnit.value.trim() || null,
      ref_range_low: editRefLow.value !== "" ? parseFloat(editRefLow.value) : null,
      ref_range_high: editRefHigh.value !== "" ? parseFloat(editRefHigh.value) : null,
      verified_by: editVerifiedBy.value.trim() || "Attending Clinician"
    };

    try {
      const res = await fetch("/api/verify-item", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error("Failed to verify item");
      currentRecord = await res.json();
      modalVerify.classList.add("hidden");
      renderAll();
    } catch (err) {
      alert("Verification error: " + err.message);
    }
  });

  // Modal Closers
  document.getElementById("modal-close").addEventListener("click", () => modalVerify.classList.add("hidden"));
  document.getElementById("modal-cancel").addEventListener("click", () => modalVerify.classList.add("hidden"));
  document.getElementById("snippet-close").addEventListener("click", () => modalSnippet.classList.add("hidden"));
}

async function fetchRecord() {
  try {
    const res = await fetch("/api/record");
    if (res.ok) {
      currentRecord = await res.json();
      renderAll();
    }
  } catch (err) {
    console.error("Initial load error:", err);
  }
}

function resetForms() {
  formPatientIntake.reset();
  docFilename.textContent = "No document loaded";
  sourcePreview.textContent = "// Upload a lab report or click '⚡ Load Demo Case' to preview source document and highlights...";
}

function renderAll() {
  renderPatientIntake();
  renderSourcePreview();
  renderCounters();
  renderInconsistencies();
  renderLabTable();
  renderSummary();
  if (window.lucide) lucide.createIcons();
}

function renderPatientIntake() {
  if (!currentRecord.patient) return;
  const p = currentRecord.patient;
  patientNameInput.value = p.name || "";
  patientAgeInput.value = p.age || "";
  patientSexInput.value = p.sex || "Male";
  patientSymptomsInput.value = (p.symptoms || []).join(", ");
  patientConditionsInput.value = (p.existing_conditions || []).join(", ");
  patientAllergiesInput.value = (p.allergies || []).join(", ");
  patientMedsInput.value = (p.current_medications || []).join(", ");
  patientNotesInput.value = p.notes || "";
}

function renderSourcePreview() {
  if (currentRecord.reports && currentRecord.reports.length > 0) {
    const lastReport = currentRecord.reports[currentRecord.reports.length - 1];
    docFilename.textContent = `${lastReport.filename} (${lastReport.lab_name || "Diagnostic Lab"})`;
    sourcePreview.textContent = lastReport.raw_text || "// No raw text extracted.";
  }
}

function renderCounters() {
  const tests = currentRecord.lab_tests || [];
  const high = tests.filter(t => t.status === "HIGH").length;
  const low = tests.filter(t => t.status === "LOW").length;
  const normal = tests.filter(t => t.status === "NORMAL").length;
  const conflicts = (currentRecord.inconsistencies || []).length;

  statTotal.textContent = tests.length;
  statHigh.textContent = high;
  statLow.textContent = low;
  statNormal.textContent = normal;
  statConflicts.textContent = conflicts;
}

function renderInconsistencies() {
  const list = currentRecord.inconsistencies || [];
  if (list.length === 0) {
    conflictSection.classList.add("hidden");
    return;
  }

  conflictSection.classList.remove("hidden");
  conflictCountBadge.textContent = `${list.length} Discrepanc${list.length > 1 ? 'ies' : 'y'} Flagged`;

  conflictList.innerHTML = list.map(item => {
    let badgeClass = "bg-amber-100 text-amber-800 border-amber-300";
    let iconName = "alert-triangle";
    if (item.severity === "CRITICAL") {
      badgeClass = "bg-rose-100 text-rose-800 border-rose-300";
      iconName = "shield-alert";
    } else if (item.severity === "INFO") {
      badgeClass = "bg-blue-100 text-blue-800 border-blue-300";
      iconName = "info";
    }

    return `
      <div class="bg-white p-3.5 rounded-xl border border-amber-200/70 shadow-2xs space-y-2">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2 font-bold text-xs text-slate-900">
            <i data-lucide="${iconName}" class="w-4 h-4 text-amber-600"></i>
            <span>${item.title}</span>
          </div>
          <span class="text-[10px] font-bold px-2 py-0.5 rounded-full border ${badgeClass}">
            ${item.severity}
          </span>
        </div>
        <p class="text-xs text-slate-700 leading-relaxed">${item.explanation}</p>
        <div class="text-[11px] bg-slate-50 p-2 rounded-lg border border-slate-100 text-slate-600 space-y-0.5">
          <div class="font-semibold text-slate-700">Contradictory Evidence:</div>
          ${item.conflicting_points.map(pt => `<div>• ${pt}</div>`).join('')}
        </div>
        <div class="text-[11px] text-brand-700 font-medium flex items-start gap-1">
          <i data-lucide="help-circle" class="w-3.5 h-3.5 flex-shrink-0 mt-0.5"></i>
          <span><strong>Clarification Prompt:</strong> ${item.suggested_clarification}</span>
        </div>
      </div>
    `;
  }).join('');
}

function renderLabTable() {
  const tests = currentRecord.lab_tests || [];
  let filtered = tests;

  if (activeFilter === "flagged") {
    filtered = tests.filter(t => t.status === "LOW" || t.status === "HIGH");
  } else if (activeFilter === "verified") {
    filtered = tests.filter(t => t.is_verified);
  }

  if (filtered.length === 0) {
    labTableBody.innerHTML = `
      <tr>
        <td colspan="6" class="py-8 text-center text-slate-400">
          ${tests.length === 0 ? "No lab tests processed yet. Upload a report or load the demo case." : "No tests match active filter."}
        </td>
      </tr>
    `;
    return;
  }

  labTableBody.innerHTML = filtered.map(test => {
    let statusClass = "status-pill-unknown";
    if (test.status === "HIGH") statusClass = "status-pill-high";
    else if (test.status === "LOW") statusClass = "status-pill-low";
    else if (test.status === "NORMAL") statusClass = "status-pill-normal";

    let provBadge = `<span class="provenance-tag-ai text-[10px] font-semibold px-2 py-0.5 rounded-full">[AI_EXTRACTED]</span>`;
    if (test.is_verified) {
      provBadge = `<span class="provenance-tag-verified text-[10px] font-semibold px-2 py-0.5 rounded-full" title="Verified by ${test.verified_by || 'Clinician'}">[HUMAN_VERIFIED]</span>`;
    }

    const refString = (test.ref_range_low !== null || test.ref_range_high !== null)
      ? `${test.ref_range_low ?? '-'} – ${test.ref_range_high ?? '-'}`
      : (test.raw_ref_range || '<span class="text-slate-400 italic">Not stated</span>');

    const valueDisplay = test.value !== null ? test.value : (test.value_text || '-');

    return `
      <tr class="hover:bg-slate-50/80 transition group">
        <td class="py-2.5 px-3 font-medium text-slate-900">
          <div>${test.test_name}</div>
          ${test.clinical_flag_note ? `<div class="text-[10px] text-slate-500 line-clamp-1">${test.clinical_flag_note}</div>` : ''}
        </td>
        <td class="py-2.5 px-3 font-semibold font-mono text-slate-800">
          ${valueDisplay} <span class="text-[10px] text-slate-500 font-sans">${test.unit || ''}</span>
        </td>
        <td class="py-2.5 px-3 text-slate-600 font-mono text-[11px]">
          ${refString}
        </td>
        <td class="py-2.5 px-3">
          <span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${statusClass}">
            ${test.status}
          </span>
        </td>
        <td class="py-2.5 px-3">
          ${provBadge}
        </td>
        <td class="py-2.5 px-3 text-right action-col">
          <div class="inline-flex items-center gap-1">
            <button onclick="openSnippetModal('${test.id}')" title="Inspect source text" class="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100">
              <i data-lucide="scan" class="w-3.5 h-3.5"></i>
            </button>
            <button onclick="openEditModal('${test.id}')" title="Verify / Edit value" class="p-1 rounded text-slate-400 hover:text-brand-600 hover:bg-brand-50">
              <i data-lucide="edit-2" class="w-3.5 h-3.5"></i>
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function renderSummary() {
  if (!currentRecord.summary) {
    summaryContent.innerHTML = `<p class="text-slate-400 italic">Summary will generate automatically once patient data and lab reports are submitted.</p>`;
    return;
  }
  if (window.marked) {
    summaryContent.innerHTML = marked.parse(currentRecord.summary);
  } else {
    summaryContent.innerText = currentRecord.summary;
  }
}

// Global modal triggers
window.openSnippetModal = function(id) {
  const test = (currentRecord.lab_tests || []).find(t => t.id === id);
  if (!test) return;
  snippetDisplay.textContent = test.source_snippet || "No source snippet recorded.";
  modalSnippet.classList.remove("hidden");
  if (window.lucide) lucide.createIcons();
};

window.openEditModal = function(id) {
  const test = (currentRecord.lab_tests || []).find(t => t.id === id);
  if (!test) return;

  editItemId.value = test.id;
  editTestName.value = test.test_name;
  editValue.value = test.value !== null ? test.value : "";
  editUnit.value = test.unit || "";
  editRefLow.value = test.ref_range_low !== null ? test.ref_range_low : "";
  editRefHigh.value = test.ref_range_high !== null ? test.ref_range_high : "";
  editSnippetText.textContent = test.source_snippet || "N/A";
  editVerifiedBy.value = "Dr. Vance, MD (Attending)";

  modalVerify.classList.remove("hidden");
  if (window.lucide) lucide.createIcons();
};
