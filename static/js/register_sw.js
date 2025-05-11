if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/service-worker.js')
    .then(reg => console.log("✅ Service worker enregistré"))
    .catch(err => console.warn("❌ Service worker erreur", err));
}
