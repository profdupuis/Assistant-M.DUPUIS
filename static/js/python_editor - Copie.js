/* python_editor.js */


function ensureEditorIsReady() {
    if (!cmInstance) {
      cmInstance = CodeMirror.fromTextArea(
        document.getElementById("pythonEditorTextarea"),
        {
          mode: "python",
          lineNumbers: true,
          indentUnit: 4,
          tabSize: 4,
          theme: "default"
        }
      );
      window.pythonEditor = cmInstance;
    }
  }

  


let cmInstance = null;
let editorVisible = false;

function toggleEditeurPython(){
  const zone = document.getElementById("python-editor");

  ensureEditorIsReady();  // ← nouvelle ligne

  // first time → build CodeMirror
  if(!cmInstance){
      cmInstance = CodeMirror.fromTextArea(
          document.getElementById("pythonEditorTextarea"),
          {
              mode: "python",
              lineNumbers: true,
              indentUnit: 4,
              tabSize: 4,
              theme: "default"
          }
      );
  }

  setTimeout(() => cmInstance.refresh(), 100);  // 👈 Ajoute ceci juste après
  
  window.pythonEditor = cmInstance;    // ✅ expose bien ton éditeur

  // toggle visibility
  editorVisible = !editorVisible;
  zone.style.display = editorVisible ? "block" : "none";

if (window.pythonEditor) {
  window.pythonEditor.off("change", updateSendButtonState); // 🔁 enlève l'ancien si existant
  window.pythonEditor.on("change", updateSendButtonState);  // 🆕 ajoute le nouveau
}

if (window.pythonEditor) {
  window.pythonEditor.setOption("readOnly", false);
  window.pythonEditor.focus();
}


  // give CodeMirror a nudge when showing
  if(editorVisible){ cmInstance.refresh(); }

  // optionally focus the first line
  if(editorVisible){ cmInstance.focus(); }
}





