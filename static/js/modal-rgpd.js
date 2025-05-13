document.addEventListener("DOMContentLoaded", function () {
    const modal = document.getElementById("rgpd-modal");
    const openBtn = document.getElementById("open-rgpd");
    const closeBtn = document.querySelector(".close");
    const consentForm = document.getElementById("consent-form");
    const body = document.body;

    if (modal && openBtn && closeBtn) {
        // Si la page indique qu'on doit afficher la modale automatiquement
        if (body.classList.contains('show-rgpd-modal')) {
            modal.style.display = "block";
        }

        // Si l'utilisateur clique sur le lien en bas
        openBtn.addEventListener("click", function (e) {
            e.preventDefault();
            modal.style.display = "block";
            body.classList.add("lecture-seule");

            // Lecture seule = masquer le formulaire d'acceptation RGPD

            if (consentForm) consentForm.style.display = "none";
            // 🔽 Fermer le menu hamburger si la fonction existe
            if (typeof fermerHamburgerMenu === "function") {
                fermerHamburgerMenu();
            }
        });

        // Si l'utilisateur ferme la modale
        closeBtn.addEventListener("click", function () {
            modal.style.display = "none";
            body.classList.remove("lecture-seule");

            // Réafficher le formulaire en mode normal
            if (consentForm) consentForm.style.display = "block";
        });
    }
});




