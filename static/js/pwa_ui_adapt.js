document.addEventListener('DOMContentLoaded', () => {
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches
                    || window.navigator.standalone === true;

  if (isStandalone) {
    document.body.classList.add('pwa-installed');
  }
});



//loader PWA
window.addEventListener('DOMContentLoaded', () => {
  const isStandalone = window.matchMedia('(display-mode: standalone)').matches
                    || window.navigator.standalone === true;

  if (isStandalone) {
    const loader = document.getElementById('pwa-loader');
    if (loader) loader.classList.remove('hidden');

    window.addEventListener('load', () => {
      if (loader) loader.classList.add('hidden');
    });
  }
});
