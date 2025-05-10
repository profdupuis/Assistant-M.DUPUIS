document.addEventListener('DOMContentLoaded', () => {
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches
                    || window.navigator.standalone === true;

  if (isStandalone) {
    document.body.classList.add('pwa-installed');
  }
});
