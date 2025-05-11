document.addEventListener('DOMContentLoaded', function() {
    const flash = document.querySelector('.flash');
    if (flash) {
      setTimeout(() => {
        flash.style.opacity = '0';
        setTimeout(() => {
          flash.remove();
        }, 1000); // attendre la transition pour supprimer
      }, 4000); // attendre 4 secondes avant de commencer le fade-out
    }
  });
  