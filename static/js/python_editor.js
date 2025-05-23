let cmInstance = null;
let editorVisible = false;
let lastOpenedLang = null;


function ensureEditor(lang = "python") {
  if (!cmInstance) {
    cmInstance = CodeMirror.fromTextArea(
      document.getElementById("pythonEditorTextarea"),
      {
        mode: lang,
        lineNumbers: true,
        indentUnit: 4,
        tabSize: 4,
        theme: "default"
      }
    );
    window._currentCodeMirror = cmInstance;
    
  } else {
    cmInstance.setOption("mode", lang);
  }
}

function toggleEditeur(lang = "python") {
  const zone = document.getElementById("python-editor");
  ensureEditor(lang);

  const isVisible = zone.style.display === "block";
  const currentMode = cmInstance?.getOption("mode");



  if (isVisible && currentMode === lang) {
    // Même mode déjà ouvert → referme
    zone.style.display = "none";
    return;
  }

  // Sinon : ouvrir ou changer de mode
  zone.style.display = "block";
  cmInstance.setOption("mode", lang);
  cmInstance.setOption("readOnly", false);
  cmInstance.refresh();
  cmInstance.focus();
  window.lastUsedLang = lang;
  updateMobileLangIcon();
  cmInstance.off("change", updateSendButtonState);
  cmInstance.on("change", updateSendButtonState);
}


function ouvrirEditeurDepuisReaction(code, lang = "python") {
  const select = document.getElementById("editorLangSelect");
  if (select) select.value = lang;
  window.lastUsedLang = lang;
  updateMobileLangIcon(); // ✅

  toggleEditeur(lang);

  if (window._currentCodeMirror) {
    window._currentCodeMirror.setOption("mode", lang);
    window._currentCodeMirror.setValue(code || "");
    window._currentCodeMirror.focus();
  }
}



function updateMobileLangIcon() {
  const img = document.getElementById("lang-icon");
  const lang = window.lastUsedLang || "python";

  if (!img) return;

  if (lang === "sql") {
    img.src = "/static/img/icon_sql.png";
    img.alt = "SQL";
  } else {
    img.src = "/static/img/icon_python.png";
    img.alt = "Python";
  }
}


function clearEditor() {
  if (window._currentCodeMirror) {
    window._currentCodeMirror.setValue("");
    updateSendButtonState();
  }
}

// pour le check lang dans hamburger menu
document.addEventListener("DOMContentLoaded", () => {
  // Appliquer la classe .active au bouton du langage actuel
  const langs = ["python", "sql"];
  langs.forEach(l => {
    const btn = document.getElementById(`btn-lang-${l}`);
    if (btn) btn.classList.toggle("active", l === window.lastUsedLang);
  });
});


// déplacable editeur sur ordi et tel
let isDragging = false;  // État du drag
let offsetX, offsetY;    // Position de l'éditeur par rapport au toucher

const editor = document.getElementById("python-editor");

// Pour les ordinateurs
editor.addEventListener("mousedown", (e) => {
  isDragging = true;
  offsetX = e.clientX - editor.offsetLeft;
  offsetY = e.clientY - editor.offsetTop;
  editor.style.cursor = "grabbing";
});

// Pour les appareils mobiles
editor.addEventListener("touchstart", (e) => {
  isDragging = true;
  offsetX = e.touches[0].clientX - editor.offsetLeft;
  offsetY = e.touches[0].clientY - editor.offsetTop;
  editor.style.cursor = "grabbing";  // Pour indiquer que c'est déplacable
});

// Déplacement de la fenêtre sur le mouvement de la souris ou du doigt
document.addEventListener("mousemove", (e) => {
  if (isDragging) {
    editor.style.left = e.clientX - offsetX + "px";
    editor.style.top = e.clientY - offsetY + "px";
  }
});

// Déplacement sur mobile
document.addEventListener("touchmove", (e) => {
  if (isDragging) {
    editor.style.left = e.touches[0].clientX - offsetX + "px";
    editor.style.top = e.touches[0].clientY - offsetY + "px";
  }
});

// Fin du déplacement
document.addEventListener("mouseup", () => {
  isDragging = false;
  editor.style.cursor = "move";  // Remettre le curseur par défaut
});

document.addEventListener("touchend", () => {
  isDragging = false;
  editor.style.cursor = "move";  // Remettre le curseur par défaut
});
