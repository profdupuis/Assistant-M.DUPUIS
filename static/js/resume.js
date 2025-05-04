function toggleResume(link) {
    const box = link.nextElementSibling;
    box.classList.toggle('show');
  
    // Si on vient d’ouvrir, scroll fluide vers le résumé
    if (box.classList.contains('show')) {
      setTimeout(() => {
        box.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 100); // petit délai pour que l’affichage soit effectif
    }
  }