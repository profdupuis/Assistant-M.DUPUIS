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

function toggleEditeurPython() {
  const zone = document.getElementById("python-editor");

  ensureEditorIsReady(); // crée cmInstance si nécessaire

  editorVisible = !editorVisible;
  zone.style.display = editorVisible ? "block" : "none";

  if (editorVisible) {
    if (window.pythonEditor) {
      window.pythonEditor.setOption("readOnly", false);
      window.pythonEditor.refresh(); // ← obligatoire après display: none
      window.pythonEditor.focus();
      window.pythonEditor.off("change", updateSendButtonState);
      window.pythonEditor.on("change", updateSendButtonState);
    }
  }
}
