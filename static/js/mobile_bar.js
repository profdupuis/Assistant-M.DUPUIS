/* static/js/mobile_bar.js  — version images PNG  */

document.addEventListener('DOMContentLoaded', () => {
  /* ─── sélecteurs DOM ─────────────────────────────── */
  const matSelect      = document.getElementById('matiere-select');   // <select> matière
  const matImg         = document.getElementById('matiere-icon');     // <img> dans la barre
  const scenSelect     = document.getElementById('scenario-select');  // <select> scénarios
  const scenForm       = document.getElementById('scenario-form');    // <form> scénarios

  /* ─── table de correspondance matière → fichier PNG ─ */
  const ICON = {
    MATHS: 'icon_maths.png',
    SVT  : 'icon_svt.png',
    NSI  : 'icon_nsi.png',
    '':    'icon_default.png'            // 📚  (= « Toutes »)
  };

  /* ─── met à jour l’icône dans la barre ────────────── */
  function refreshIcon() {
    const file = ICON[matSelect.value] || ICON[''];
    matImg.src = `/static/img/${file}`;
    matImg.alt = matSelect.value || 'Toutes';
  }

  /* ─── filtre la liste des fiches après changement de matière */
  function refreshScenarioList() {
    // si tu relies déjà la liste côté back-end, ce bloc peut être vide
    // → ici on montre juste comment masquer l’ancienne liste :
    scenSelect.selectedIndex = 0; // revient sur « Choisir une fiche… »
  }

  /* ─── événements ─────────────────────────────────── */
  matSelect.addEventListener('change', () => {
    refreshIcon();
    refreshScenarioList();
    matSelect.form.submit();             // rechargement GET /mon_dashboard
  });

  scenSelect.addEventListener('change', () => {
    scenForm.submit();                   // POST /changer_scenario
  });

  /* ─── init au chargement ──────────────────────────── */
  refreshIcon();
});
