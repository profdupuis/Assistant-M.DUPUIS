let deferredPrompt;

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  const installSection = document.getElementById('installPwaSection');
  if (installSection) {
    installSection.style.display = 'block';
  }
});

function installerPwa() {
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt.userChoice.then(choiceResult => {
      if (choiceResult.outcome === 'accepted') {
        console.log('✅ Installation acceptée');
      }
      deferredPrompt = null;
    });
  }
}


document.addEventListener("DOMContentLoaded", function () {
  const pwaBtn = document.getElementById("installPwaBtn");
  if (pwaBtn) {
    pwaBtn.addEventListener("click", installerPwa);
  }
});
