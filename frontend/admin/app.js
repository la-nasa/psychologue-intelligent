const api = "/api/v1";
let token = sessionStorage.getItem("pi_admin_token");
const ROLE_LABELS = { PATIENT: "Patient", CLINICIAN: "Clinicien", ADMIN: "Administrateur" };
const STATUS_LABELS = { ACTIVE: "Active", ENDED: "Terminée" };

function appMessage(text) { const el = document.getElementById("app-message"); if (el) el.textContent = text || ""; }
function loginMessage(text) { document.getElementById("login-message").textContent = text || ""; }
function formatDate(iso) { try { return new Date(iso).toLocaleString("fr-FR"); } catch { return iso; } }

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
    sessionStorage.setItem("pi_admin_token", token);
    document.getElementById("login").classList.add("hidden");
    document.getElementById("dashboard").classList.remove("hidden");
    await bootDashboard();
  } catch (error) {
    loginMessage(error.message);
  }
};

document.getElementById("logout").onclick = async () => {
  try { await request("/auth/logout", { method: "POST" }); } catch (error) { /* session already gone */ }
  sessionStorage.removeItem("pi_admin_token");
  token = null;
  document.getElementById("dashboard").classList.add("hidden");
  document.getElementById("login").classList.remove("hidden");
};

document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
  button.onclick = () => {
    appMessage("");
    showView(button.dataset.view);
    if (button.dataset.view === "relationships") loadRelationships();
    if (button.dataset.view === "users") loadUsers();
    if (button.dataset.view === "learning") loadLearning();
  };
});

async function bootDashboard() {
  showView("relationships");
  await populateRelationshipSelects();
  await loadRelationships();
}

async function populateRelationshipSelects() {
  const [patients, clinicians] = await Promise.all([
    request("/admin/users?role=PATIENT"),
    request("/admin/users?role=CLINICIAN"),
  ]);
  fillSelect(document.getElementById("patient-select"), patients.items);
  fillSelect(document.getElementById("clinician-select"), clinicians.items);
}

function fillSelect(select, users) {
  select.innerHTML = users.map((u) => `<option value="${u.id}">${escapeHtml(u.email)}</option>`).join("");
}

document.getElementById("create-relationship").onsubmit = async (event) => {
  event.preventDefault();
  const patientId = document.getElementById("patient-select").value;
  const clinicianId = document.getElementById("clinician-select").value;
  try {
    await request("/admin/relationships", { method: "POST", body: { patient_id: patientId, clinician_id: clinicianId } });
    appMessage("Relation créée.");
    await loadRelationships();
  } catch (error) {
    appMessage(error.message);
  }
};

document.getElementById("relationship-status-filter").onchange = loadRelationships;
document.getElementById("user-role-filter").onchange = loadUsers;

async function loadRelationships() {
  try {
    const status = document.getElementById("relationship-status-filter").value;
    const { items } = await request(`/admin/relationships${status ? "?status=" + status : ""}`);
    const body = document.querySelector("#relationships-table tbody");
    body.innerHTML = "";
    document.getElementById("relationships-empty").classList.toggle("hidden", items.length > 0);
    for (const rel of items) {
      const row = document.createElement("tr");
      row.innerHTML = `<td>${escapeHtml(rel.patient_email)}</td><td>${escapeHtml(rel.clinician_email)}</td>` +
        `<td>${STATUS_LABELS[rel.status] || rel.status}</td><td>${formatDate(rel.created_at)}</td><td></td>`;
      if (rel.status === "ACTIVE") {
        const button = document.createElement("button");
        button.className = "text";
        button.textContent = "Terminer";
        button.onclick = async () => {
          try {
            await request(`/admin/relationships/${rel.id}/end`, { method: "POST" });
            appMessage("Relation terminée.");
            loadRelationships();
          } catch (error) {
            appMessage(error.message);
          }
        };
        row.lastElementChild.appendChild(button);
      }
      body.appendChild(row);
    }
  } catch (error) {
    appMessage(error.message);
  }
}

async function loadUsers() {
  try {
    const role = document.getElementById("user-role-filter").value;
    const { items } = await request(`/admin/users${role ? "?role=" + role : ""}`);
    const body = document.querySelector("#users-table tbody");
    body.innerHTML = "";
    document.getElementById("users-empty").classList.toggle("hidden", items.length > 0);
    for (const user of items) {
      const row = document.createElement("tr");
      row.innerHTML = `<td>${escapeHtml(user.email)}</td><td>${ROLE_LABELS[user.role] || user.role}</td>` +
        `<td>${user.is_active ? "Oui" : "Non"}</td><td>${user.mfa_enabled ? "Activée" : "—"}</td><td>${formatDate(user.created_at)}</td>`;
      body.appendChild(row);
    }
  } catch (error) {
    appMessage(error.message);
  }
}

const MODEL_STATUS_LABELS = {
  DRAFT: "Brouillon", PENDING_REVIEW: "En attente de revue", APPROVED: "Approuvé",
  DEPLOYED: "Déployé", ROLLED_BACK: "Retiré", REJECTED: "Rejeté",
};

document.getElementById("trigger-sample").onclick = async () => {
  try {
    const result = await request("/admin/learning/sample", { method: "POST", body: {} });
    appMessage(`${result.created} nouveau(x) message(s) échantillonné(s) pour revue.`);
  } catch (error) {
    appMessage(error.message);
  }
};

document.getElementById("create-dataset").onclick = async () => {
  try {
    const dataset = await request("/admin/learning/datasets", { method: "POST", body: {} });
    appMessage(`Dataset ${dataset.version} créé avec ${dataset.item_count} élément(s).`);
    loadLearning();
  } catch (error) {
    appMessage(error.message);
  }
};

document.getElementById("register-model").onsubmit = async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  try {
    await request("/admin/learning/models", {
      method: "POST",
      body: { kind: data.kind, version: data.version, dataset_id: data.dataset_id || null },
    });
    appMessage("Modèle enregistré, en attente de revue clinicienne.");
    event.target.reset();
    loadLearning();
  } catch (error) {
    appMessage(error.message);
  }
};

async function loadLearning() {
  try {
    const [{ items: datasets }, { items: models }] = await Promise.all([
      request("/admin/learning/datasets"),
      request("/admin/learning/models"),
    ]);

    const datasetSelect = document.querySelector('#register-model select[name="dataset_id"]');
    datasetSelect.innerHTML = '<option value="">Aucun</option>' +
      datasets.map((d) => `<option value="${d.id}">${escapeHtml(d.version)}</option>`).join("");

    const datasetsBody = document.querySelector("#datasets-table tbody");
    datasetsBody.innerHTML = "";
    document.getElementById("datasets-empty").classList.toggle("hidden", datasets.length > 0);
    for (const dataset of datasets) {
      const row = document.createElement("tr");
      row.innerHTML = `<td>${escapeHtml(dataset.version)}</td><td>${dataset.status}</td><td>${dataset.item_count}</td><td>${formatDate(dataset.created_at)}</td>`;
      datasetsBody.appendChild(row);
    }

    const modelsBody = document.querySelector("#models-table tbody");
    modelsBody.innerHTML = "";
    document.getElementById("models-empty").classList.toggle("hidden", models.length > 0);
    for (const model of models) {
      const row = document.createElement("tr");
      row.innerHTML = `<td>${escapeHtml(model.kind)}</td><td>${escapeHtml(model.version)}</td>` +
        `<td>${MODEL_STATUS_LABELS[model.status] || model.status}</td><td>${model.approval_count} / 2</td><td></td>`;
      const actionCell = row.lastElementChild;
      if (model.status === "APPROVED") {
        const button = document.createElement("button");
        button.className = "text";
        button.textContent = "Déployer";
        button.onclick = async () => {
          try {
            await request(`/admin/learning/models/${model.id}/deploy`, { method: "POST", body: {} });
            appMessage("Modèle déployé.");
            loadLearning();
          } catch (error) {
            appMessage(error.message);
          }
        };
        actionCell.appendChild(button);
      }
      if (model.status === "DEPLOYED") {
        const button = document.createElement("button");
        button.className = "text";
        button.textContent = "Retirer (rollback)";
        button.onclick = async () => {
          try {
            await request(`/admin/learning/models/${model.id}/rollback`, { method: "POST", body: {} });
            appMessage("Modèle retiré.");
            loadLearning();
          } catch (error) {
            appMessage(error.message);
          }
        };
        actionCell.appendChild(button);
      }
      modelsBody.appendChild(row);
    }
  } catch (error) {
    appMessage(error.message);
  }
}

function escapeHtml(text) { const div = document.createElement("div"); div.textContent = text; return div.innerHTML; }

if (token) {
  document.getElementById("login").classList.add("hidden");
  document.getElementById("dashboard").classList.remove("hidden");
  bootDashboard();
}
