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