const api = "/api/v1";
let token = sessionStorage.getItem("pi_clinician_token");

const TRANSITIONS = {
  OPEN: ["ACKNOWLEDGED", "ESCALATED", "CANCELLED"],
  ACKNOWLEDGED: ["IN_REVIEW", "ESCALATED", "RESOLVED"],
  IN_REVIEW: ["ESCALATED", "RESOLVED"],
  ESCALATED: ["RESOLVED"],
  RESOLVED: ["CLOSED"],
};
const ACTION_LABELS = {
  ACKNOWLEDGED: "Prendre en compte", IN_REVIEW: "Mettre en revue", ESCALATED: "Escalader",
  RESOLVED: "Résoudre", CLOSED: "Clôturer", CANCELLED: "Annuler",
};
const LEVEL_LABELS = { RED: "Rouge", ORANGE: "Orange", GREEN: "Vert" };

function appMessage(text) { const el = document.getElementById("app-message"); if (el) el.textContent = text || ""; }
function loginMessage(text) { document.getElementById("login-message").textContent = text || ""; }

async function request(path, options = {}) {
  const res = await fetch(api + path, {
    method: options.method || "GET",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.title || "Une erreur est survenue.");
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

function showView(id) {
  document.querySelectorAll(".view").forEach((el) => el.classList.add("hidden"));
  const section = document.getElementById("view-" + id);
  section.classList.remove("hidden");
  document.querySelectorAll(".nav-item[data-view]").forEach((el) => el.setAttribute("aria-current", el.dataset.view === id ? "page" : "false"));
  // Move focus to the new view's heading so screen reader users get an
  // announcement and a sane tab order, instead of focus staying on the nav
  // button that's now hidden behind an unrelated section.
  const heading = section.querySelector("h2");
  if (heading) {
    heading.setAttribute("tabindex", "-1");
    heading.focus();
  }
}

document.getElementById("login-form").onsubmit = async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  try {
    const res = await fetch(api + "/auth/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    if (!res.ok) throw new Error((await res.json()).title || "Connexion refusée.");
    const payload = await res.json();
    token = payload.access_token;
    sessionStorage.setItem("pi_clinician_token", token);
    document.getElementById("login").classList.add("hidden");
    document.getElementById("dashboard").classList.remove("hidden");
    await loadPatients();
  } catch (error) {
    loginMessage(error.message);
  }
};

document.getElementById("logout").onclick = async () => {
  try { await request("/auth/logout", { method: "POST" }); } catch (error) { /* session already gone */ }
  sessionStorage.removeItem("pi_clinician_token");
  token = null;
  document.getElementById("dashboard").classList.add("hidden");
  document.getElementById("login").classList.remove("hidden");
};

document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
  button.onclick = () => {
    appMessage("");
    showView(button.dataset.view);
    if (button.dataset.view === "patients") loadPatients();
    if (button.dataset.view === "alerts") loadAlerts();
    if (button.dataset.view === "learning") loadLearning();
  };
});

async function loadPatients() {
  showView("patients");
  try {
    const { items } = await request("/clinician/patients");
    const body = document.querySelector("#patients-table tbody");
    body.innerHTML = "";
    document.getElementById("patients-empty").classList.toggle("hidden", items.length > 0);
    for (const patient of items) {
      const row = document.createElement("tr");
      const score = patient.latest_phq9_score === null ? "—" : `${patient.latest_phq9_score} / 27`;
      row.innerHTML = `<td>${escapeHtml(patient.display_name || patient.patient_id)}</td><td>${score}</td><td>${patient.open_alert_count}</td><td></td>`;
      const actionCell = row.lastElementChild;
      const button = document.createElement("button");
      button.className = "text";
      button.textContent = "Voir le suivi";
      button.onclick = () => loadTimeline(patient.patient_id, patient.display_name);
      actionCell.appendChild(button);
      body.appendChild(row);
    }
  } catch (error) {
    appMessage(error.message);
  }
}

async function loadTimeline(patientId, displayName) {
  try {
    const timeline = await request(`/clinician/patients/${patientId}/timeline`);
    document.getElementById("timeline-name").textContent = displayName || timeline.display_name || "Suivi patient";
    const phq9Body = document.querySelector("#phq9-table tbody");
    phq9Body.innerHTML = "";
    document.getElementById("phq9-empty").classList.toggle("hidden", timeline.phq9_history.length > 0);
    for (const entry of timeline.phq9_history) {
      const row = document.createElement("tr");
      row.innerHTML = `<td>${formatDate(entry.completed_at)}</td><td>${entry.total_score} / 27</td><td>${entry.item9_score}</td>`;
      phq9Body.appendChild(row);
    }
    renderAlerts(document.getElementById("timeline-alerts"), timeline.alerts, patientId);
    showView("timeline");
  } catch (error) {
    appMessage(error.message);
  }
}

async function loadAlerts() {
  try {
    const level = document.getElementById("filter-level").value;
    const status = document.getElementById("filter-status").value;
    const query = new URLSearchParams();
    if (level) query.set("level", level);
    if (status) query.set("status", status);
    const { items } = await request(`/clinician/alerts${query.toString() ? "?" + query.toString() : ""}`);
    const container = document.getElementById("alerts-list");
    document.getElementById("alerts-empty").classList.toggle("hidden", items.length > 0);
    renderAlerts(container, items, null);
  } catch (error) {
    appMessage(error.message);
  }
}

function renderAlerts(container, alerts, contextPatientId) {
  container.innerHTML = "";
  for (const alert of alerts) {
    const card = document.createElement("article");
    card.className = `alert-card level-${alert.level.toLowerCase()}`;
    const label = alert.patient_display_name && !contextPatientId ? `<p class="quiet">${escapeHtml(alert.patient_display_name)}</p>` : "";
    card.innerHTML = `<p class="alert-level">Niveau ${LEVEL_LABELS[alert.level] || alert.level}</p>${label}<p class="alert-status">Statut : ${alert.status}</p><p class="quiet">Ouverte le ${formatDate(alert.created_at)}</p>`;
    const nextStatuses = TRANSITIONS[alert.status] || [];
    if (nextStatuses.length > 0) {
      const form = document.createElement("form");
      form.className = "alert-action";
      form.innerHTML = `<label>Justification<textarea name="justification" maxlength="500" required></textarea></label>` +
        `<label>Action<select name="action">${nextStatuses.map((s) => `<option value="${s}">${ACTION_LABELS[s] || s}</option>`).join("")}</select></label>` +
        `<button>Appliquer</button>`;
      form.onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));
        try {
          await request(`/clinician/alerts/${alert.id}/actions`, { method: "POST", body: data });
          appMessage("Action enregistrée.");
          if (contextPatientId) loadTimeline(contextPatientId, document.getElementById("timeline-name").textContent);
          else loadAlerts();
        } catch (error) {
          appMessage(error.message);
        }
      };
      card.appendChild(form);
    }
    container.appendChild(card);
  }
}

document.getElementById("filter-level").onchange = loadAlerts;
document.getElementById("filter-status").onchange = loadAlerts;

async function loadLearning() {
  try {
    const [{ items: feedbackItems }, { items: modelItems }] = await Promise.all([
      request("/clinician/learning/feedback"),
      request("/clinician/learning/models"),
    ]);

    const feedbackList = document.getElementById("feedback-list");
    feedbackList.innerHTML = "";
    document.getElementById("feedback-empty").classList.toggle("hidden", feedbackItems.length > 0);
    for (const item of feedbackItems) {
      const card = document.createElement("article");
      card.className = "alert-card level-green";
      card.innerHTML = `<p class="quiet">Échantillonné le ${formatDate(item.sampled_at)}</p><p>${escapeHtml(item.anonymized_content)}</p>`;
      const form = document.createElement("form");
      form.className = "alert-action";
      form.innerHTML = `<label>Justification<textarea name="justification" maxlength="500" required></textarea></label>` +
        `<label>Décision<select name="decision"><option value="APPROVED">Approuver pour le dataset</option><option value="REJECTED">Rejeter</option></select></label>` +
        `<button>Valider</button>`;
      form.onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));
        try {
          await request(`/clinician/learning/feedback/${item.id}/review`, { method: "POST", body: data });
          appMessage("Décision enregistrée.");
          loadLearning();
        } catch (error) {
          appMessage(error.message);
        }
      };
      card.appendChild(form);
      feedbackList.appendChild(card);
    }

    const pendingModels = modelItems.filter((m) => m.status === "PENDING_REVIEW");
    const modelsList = document.getElementById("models-review-list");
    modelsList.innerHTML = "";
    document.getElementById("models-review-empty").classList.toggle("hidden", pendingModels.length > 0);
    for (const model of pendingModels) {
      const card = document.createElement("article");
      card.className = "alert-card level-orange";
      card.innerHTML = `<p class="alert-level">${escapeHtml(model.kind)} — ${escapeHtml(model.version)}</p>` +
        `<p class="quiet">Approbations reçues : ${model.approval_count} / 2</p>` +
        `<p class="quiet">Métriques : ${escapeHtml(model.metrics_json)}</p>`;
      const form = document.createElement("form");
      form.className = "alert-action";
      form.innerHTML = `<label>Justification<textarea name="justification" maxlength="500" required></textarea></label>` +
        `<label>Décision<select name="decision"><option value="APPROVED">Approuver</option><option value="REJECTED">Rejeter</option></select></label>` +
        `<button>Valider</button>`;
      form.onsubmit = async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(event.target));
        try {
          await request(`/clinician/learning/models/${model.id}/decisions`, { method: "POST", body: data });
          appMessage("Décision enregistrée.");
          loadLearning();
        } catch (error) {
          appMessage(error.message);
        }
      };
      card.appendChild(form);
      modelsList.appendChild(card);
    }
  } catch (error) {
    appMessage(error.message);
  }
}

function formatDate(iso) { try { return new Date(iso).toLocaleString("fr-FR"); } catch { return iso; } }
function escapeHtml(text) { const div = document.createElement("div"); div.textContent = text; return div.innerHTML; }

if (token) {
  document.getElementById("login").classList.add("hidden");
  document.getElementById("dashboard").classList.remove("hidden");
  loadPatients();
}
