// HamburgerMenu
function toggleHamburgerMenu() {
  const menu = document.getElementById("hamburgerMenu");
  if (menu) {
    menu.classList.toggle("show");
  }
}

function fermerHamburgerMenu() {
  document.getElementById("hamburgerMenu").classList.remove("show");
}

function fermerHamburgerEtAccordeon() {
  const menu = document.getElementById("hamburgerMenu");
  if (menu.classList.contains("show")) {
    menu.classList.remove("show");
  }
  document.querySelectorAll(".accordion-section").forEach(section => {
    section.classList.remove("open");
  });
}


function changerLangageEditeur(lang) {
  window.lastUsedLang = lang;
  updateMobileLangIcon();
  fermerHamburgerMenu();
  fermerAccordeons(); // ← ferme toutes les sections accordéon ouvertes

  const langs = ["python", "sql"];
  langs.forEach(l => {
    const btn = document.getElementById(`btn-lang-${l}`);
    if (btn) btn.classList.toggle("active", l === lang);
  });
}

/*
function telechargerConversation() {
  fermerHamburgerMenu();
  fermerAccordeons();
  const a = document.createElement("a");
  a.href = "/telecharger_conversation";
  a.download = "conversation.pdf"; // ou .txt automatiquement géré
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function telechargerConversation() {
  fetch("/telecharger_conversation")
    .then(response => {
      if (!response.ok) throw new Error("Échec du téléchargement.");
      return response.blob().then(blob => ({ blob, response }));
    })
    .then(({ blob, response }) => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;

      const disposition = response.headers.get("Content-Disposition");
      const filename = disposition?.match(/filename="?([^"]+)"?$/)?.[1] || "conversation.pdf";

      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    })
    .catch(err => {
      alert("❌ Impossible de télécharger la conversation.");
      console.error(err);
    });
}*/

function showToast(message, duration = 3000) {
  let toast = document.getElementById("toast-message");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast-message";
    toast.style.position = "fixed";
    toast.style.top = "1rem";
    toast.style.right = "1rem";
    toast.style.left = "auto";
    toast.style.transform = "none";
    toast.style.background = "#333";
    toast.style.color = "#fff";
    toast.style.padding = "0.8rem 1.2rem";
    toast.style.borderRadius = "1rem";
    toast.style.boxShadow = "0 0 10px rgba(0,0,0,0.3)";
    toast.style.zIndex = 9999;
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.style.opacity = "1";

  setTimeout(() => {
    toast.style.opacity = "0";
  }, duration);
}


function telechargerConversation() {
  const bouton = document.querySelector("button[onclick='telechargerConversation()']");
  if (bouton) bouton.disabled = true;

  showToast("📥 Préparation du fichier...");

  fetch("/telecharger_conversation")
    .then(response => {
      if (!response.ok) throw new Error("Échec du téléchargement.");
      return response.blob().then(blob => ({ blob, response }));
    })
    .then(({ blob, response }) => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;

      const disposition = response.headers.get("Content-Disposition");
      const filename = disposition?.match(/filename="?([^"]+)"?$/)?.[1] || "conversation.pdf";

      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      showToast("✅ Fichier téléchargé !");
    })
    .catch(err => {
      console.error(err);
      showToast("❌ Échec du téléchargement.");
    })
    .finally(() => {
      if (bouton) bouton.disabled = false;
    });
}


function fermerAccordeons() {
  document.querySelectorAll(".accordion-section.open").forEach(section => {
    section.classList.remove("open");
  });
}



document.addEventListener("click", function (e) {
  const menu = document.getElementById("hamburgerMenu");
  const burger = document.querySelector(".burger-toggle");

  if (
    menu.classList.contains("show") &&
    !menu.contains(e.target) &&
    !burger.contains(e.target)
  ) {
    menu.classList.remove("show");
  }
});

//acordeon burger 
document.addEventListener("DOMContentLoaded", () => {
  const toggles = document.querySelectorAll(".accordion-toggle");
  toggles.forEach((btn) => {
    btn.addEventListener("click", () => {
      const section = btn.closest(".accordion-section");
      section.classList.toggle("open");
    });
  });
});