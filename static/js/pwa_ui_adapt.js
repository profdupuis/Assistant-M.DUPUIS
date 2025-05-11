document.addEventListener('DOMContentLoaded', () => {
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches
                    || window.navigator.standalone === true;

  if (isStandalone) {
    document.body.classList.add('pwa-installed');
  }
});




/* ============================================================================
   🔄 UI Loader – Indicateur de chargement global pour navigation serveur
   ----------------------------------------------------------------------------
   - Affiche le petit spinner en haut à droite ( #ui-loader ) pendant toute
     action lente côté serveur : changement de page, POST, ou redirection.
   - Couvre les formulaires, les liens <a>, et les sélecteurs <select> avec
     soumission automatique (onchange → this.form.submit()).
   - Fonctionne automatiquement si les éléments ont la classe "with-loader".
   - Indispensable en PWA (plein écran sans barre de chargement du navigateur)
     mais fonctionne aussi sur web pour fluidifier l’expérience.
============================================================================ */

function showUILoader() {
  const loader = document.getElementById("ui-loader");
  if (loader) loader.classList.remove("hidden");
}

function hideUILoader() {
  const loader = document.getElementById("ui-loader");
  if (loader) loader.classList.add("hidden");
}


document.addEventListener("DOMContentLoaded", () => {
  const loader = document.getElementById("ui-loader");
  if (!loader) return;

document.querySelectorAll("form.with-loader").forEach(form => {
  // Intercepte le submit classique
  form.addEventListener("submit", () => {
    loader.classList.remove("hidden");
  });

  // Cas spécial : select.onchange => this.form.submit()
  const select = form.querySelector("select");
  if (select) {
    select.addEventListener("change", () => {
      loader.classList.remove("hidden");
    });
  }
});

  document.querySelectorAll("a.with-loader").forEach(link => {
    link.addEventListener("click", () => loader.classList.remove("hidden"));
  });
});

/* ============================================================================ */

