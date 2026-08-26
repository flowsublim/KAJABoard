(() => {
  const modal = document.getElementById("kb-modal");
  const body = document.getElementById("kb-modal-body");
  const dialog = modal?.querySelector(".kb-modal__dialog");
  const title = document.getElementById("kb-modal-title");
  const subtitle = document.getElementById("kb-modal-subtitle");
  const footer = document.getElementById("kb-modal-footer");
  const toasts = document.getElementById("toast-container");
  let lastFocused;

  const autoModal = (url) => /\/(new|edit|lines|confirm|cancel|post|hold-release|credit-override|activate|release|complete|lifecycle)\//.test(url);
  const isPreview = (url) => /\/print\/$/.test(url);
  const closeModal = () => {
    modal?.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
    body.replaceChildren(); footer.replaceChildren();
    lastFocused?.focus();
  };
  const toast = (text, type = "success") => {
    if (!toasts || !text) return;
    const item = document.createElement("div");
    item.className = `toast toast-${type}`; item.setAttribute("role", "status");
    item.innerHTML = `<span></span><button type="button" aria-label="Tutup notifikasi" data-toast-close>×</button>`;
    item.querySelector("span").textContent = text; toasts.append(item);
    if (type !== "error") window.setTimeout(() => item.remove(), type === "warning" ? 6500 : 4500);
  };
  const documentFrom = (html) => new DOMParser().parseFromString(html, "text/html");
  const load = async (url, preview = false) => {
    lastFocused = document.activeElement;
    modal.setAttribute("aria-hidden", "false"); document.body.classList.add("modal-open");
    body.innerHTML = '<p class="modal-loading">Memuat...</p>'; footer.replaceChildren();
    const response = await fetch(url, {headers: {"X-KAJABoard-Modal": "1"}});
    if (!response.ok) { body.innerHTML = '<p class="field-error">Konten tidak dapat dimuat.</p>'; return; }
    const page = documentFrom(await response.text());
    const content = preview ? page.body : page.querySelector("main.content");
    title.textContent = preview ? "Preview dokumen" : (content?.querySelector("h1")?.textContent || "KAJABoard");
    subtitle.textContent = preview ? "Periksa sebelum mencetak" : "";
    body.innerHTML = content?.innerHTML || '<p class="field-error">Konten tidak tersedia.</p>';
    if (preview) {
      const print = document.createElement("button"); print.type = "button"; print.className = "button button-primary"; print.textContent = "Cetak";
      print.addEventListener("click", () => { document.getElementById("kb-print-root").innerHTML = body.innerHTML; window.print(); });
      footer.append(print);
    }
    dialog.focus();
  };
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (link && (link.dataset.modal !== undefined || autoModal(link.pathname) || isPreview(link.pathname))) {
      event.preventDefault(); load(link.href, isPreview(link.pathname));
    }
    if (event.target.closest("[data-modal-close]")) closeModal();
    if (event.target.closest("[data-toast-close]")) event.target.closest(".toast")?.remove();
  });
  document.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!modal?.contains(form)) {
      if (!autoModal(new URL(form.action || location.href, location.href).pathname)) return;
      event.preventDefault();
      lastFocused = document.activeElement;
      modal.setAttribute("aria-hidden", "false"); document.body.classList.add("modal-open");
      title.textContent = "Konfirmasi tindakan"; subtitle.textContent = "Perubahan status akan diproses";
      body.innerHTML = "<p>Pastikan tindakan ini sudah benar.</p>";
      const confirm = form.cloneNode(true);
      confirm.querySelectorAll("button").forEach((button) => button.remove());
      const submit = document.createElement("button"); submit.type = "submit"; submit.className = "button button-primary"; submit.textContent = "Konfirmasi";
      confirm.append(submit); body.append(confirm); dialog.focus(); return;
    }
    event.preventDefault();
    const response = await fetch(form.action || location.href, {method: form.method || "POST", body: new FormData(form), headers: {"X-KAJABoard-Modal": "1"}});
    const page = documentFrom(await response.text());
    if (response.redirected) {
      const success = page.querySelector(".toast span")?.textContent || "Data berhasil disimpan.";
      toast(success); closeModal(); location.reload(); return;
    }
    const content = page.querySelector("main.content");
    if (content) { body.innerHTML = content.innerHTML; toast("Periksa kembali data yang diinput.", "warning"); }
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && modal?.getAttribute("aria-hidden") === "false") closeModal(); });
  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.querySelector("[data-sidebar-toggle]"), sidebar = document.getElementById("sidebar");
    toggle?.addEventListener("click", () => { const open = document.body.classList.toggle("sidebar-open"); toggle.setAttribute("aria-expanded", String(open)); });
    sidebar?.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => document.body.classList.remove("sidebar-open")));
    document.querySelectorAll(".toast").forEach((item) => { if (!item.classList.contains("toast-error")) window.setTimeout(() => item.remove(), 4500); });
  });
})();
