// en haut du fichier

let sendingEnCours = false;


// fonction pour générer un UUID
function uuid() {
  // si le navigateur supporte crypto.randomUUID(), on l'utilise
  if (window.crypto && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // fallback simple (version RFC4122v4)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}



function telechargerConversation() {
  const a = document.createElement("a");
  a.href = "/telecharger_conversation";
  a.download = "conversation.pdf"; // ou .txt automatiquement géré
  document.body.appendChild(a);
  a.click();
  a.remove();
}



/// a voir pour faire fonctionner 


function setSendingState(isSending) {
  sendingEnCours = isSending; // ← nouvelle ligne
  if (isSending && 'vibrate' in navigator) {
    navigator.vibrate(30);
  }
  const sendBtn = document.querySelector('.input-desktop button'); // desactiver envoi
  const sendBtnMobile = document.querySelector('.send-btn');
  //const inputDesktop = document.getElementById('userInput');
  //const inputMobile = document.getElementById('userInputMobile');   desactiver saisie aussi 

  if (sendBtn) {
    sendBtn.disabled = isSending;
    sendBtn.classList.toggle('sending-disabled', isSending);
  }
  if (sendBtnMobile) {

    sendBtnMobile.disabled = isSending;
    sendBtnMobile.classList.toggle('envoi-en-cours', isSending);


  }

  // ✅ désactiver temporairement la saisie mobile
  if (inputMobile) {
    inputMobile.readOnly = isSending;
    inputMobile.classList.toggle('input-readonly', isSending); // pour style optionnel
  }
  updateSendButtonState();  // ✅ met à jour l'état réel du bouton après envoi

}


function updateSendButtonState() {
  if (sendingEnCours) return; // ⛔ empêche le bouton de se réactiver
  const input = document.getElementById("userInputMobile");
  const sendBtn = document.querySelector(".send-btn");
  const message = input?.value.trim();
  
  let code = "";
  const editorVisible = document.getElementById("python-editor")?.style.display === "block";
  if (window.pythonEditor && editorVisible) {
    code = window.pythonEditor.getValue().trim();
  }

  const hasContent = message || code;

  if (sendBtn) {
    sendBtn.disabled = !hasContent;
    sendBtn.classList.toggle("actif", hasContent);
  }
}

function extractPythonCodeBlocks(text) {
  const regex = /```python\s*([\s\S]*?)```/g;
  const blocks = [];
  let match;
  while ((match = regex.exec(text)) !== null) {
    blocks.push(match[1]);
  }
  return blocks;
}


function scrollConvToBottom() {
  const conv = document.getElementById('conversation');
  const bar  = document.querySelector('.mobile-action-bar');
  const barH = bar ? bar.getBoundingClientRect().height : 0;

  // on attend que le navigateur ait mis à jour le layout
  requestAnimationFrame(() => {
    // conv.scrollHeight - conv.clientHeight = contenuHeight - viewportHeight
    // + barH pour laisser la place sous le dernier message
    const target = conv.scrollHeight - conv.clientHeight + barH;
    conv.scrollTo({ top: target, behavior: 'smooth' });
  });
}



// on échappe le texte pour éviter l'injection de HTML
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}




// Mettre à jour les vars CSS au chargement et à chaque redimensionnement
function refreshOffsets(){
  const root   = document.documentElement;
  const header = document.querySelector('.mobile-header');
  const bar    = document.querySelector('.mobile-action-bar');
  if (header) root.style.setProperty('--header-h', header.offsetHeight + 'px');
  if (bar)    root.style.setProperty('--bar-h',    bar.offsetHeight    + 'px');
}
window.addEventListener('load',   refreshOffsets);
window.addEventListener('resize', refreshOffsets);
window.addEventListener('orientationchange', refreshOffsets);




document.getElementById("userInput").addEventListener("keydown", function (event) {
  if (event.key === "Enter") {
      event.preventDefault(); // éviter double soumission
      sendMessage();
      this.blur(); // ferme le clavier mobile   
  }
  scrollConvToBottom();
});

        
function isMobile() {
    return window.matchMedia("(max-width: 768px)").matches;
  }


  function extractAllPythonBlocks(text) {
    if (!text) return [];
  
    const decoded = text
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#96;/g, "`")
      .replace(/&amp;/g, "&");
  
    const blocks = [];
    const regex = /```python\s*\n([\s\S]*?)```/g;
    let match;
    while ((match = regex.exec(decoded)) !== null) {
      blocks.push(match[1].trim());
    }
    return blocks;
  }

  

// bulle user 
function renderUserBubble(id, message, codeText) {
  const decodedMessage = message
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#96;/g, "`")
    .replace(/&amp;/g, "&")
    .trim();

  // Découpe texte/code dans l'ordre
  const parts = decodedMessage.split(/```python\s*\n([\s\S]*?)```/g); // texte, code, texte, code...

  const chunks = parts.map((part, index) => {
    if (index % 2 === 0) {
      // Texte brut
      return part.trim()
        ? `<div>${escapeHtml(part.trim()).replace(/\n/g, "<br>")}</div>`
        : "";
    } else {
      // Bloc code
      return `<pre><code class="language-python">${escapeHtml(part.trim())}</code></pre>`;
    }
  });

  // ✅ N'ajoute codeText QUE s'il n'est pas déjà dans le message markdowné
  const includeExtra = codeText.trim() && !message.includes("```python");

  const extraCode = includeExtra
    ? `<pre><code class="language-python">${escapeHtml(codeText.trim())}</code></pre>`
    : "";

  return `
    <div class="message user" data-message-id="${id}">
      <div class="bubble">${chunks.join("\n")}${extraCode}</div>
    </div>`;
}


        
  async function sendMessage(message, codeText = "") {


            if (message.trim() === "" && codeText.trim() === "") return;
            const loader = document.getElementById("loader");
            if (!isMobile()) {
              loader.classList.remove("hidden");
            }




  


            let codeBlock = codeText ? `\n\`\`\`python\n${codeText}\n\`\`\`` : "";

          
            const fullMessage = [message, codeBlock].filter(Boolean).join("\n");

            const id = uuid();
            
            const conv = document.getElementById("conversation");


            // affiche bulle user 
            const userHtml = renderUserBubble(id, message, codeText);
            conv.insertAdjacentHTML("beforeend", userHtml);

            if (window.MathJax) {
              MathJax.typesetPromise([conv]);
            } else if (window.renderMathInElement) {
              renderMathInElement(conv);
            }

            

            userInput.value = '';


            setSendingState(true); // désactive tout les envois


        
            scrollConvToBottom() 

            try {
              
                // AVANT la requête (dot loader)

                document.getElementById("dot-loader").style.display = "flex";


                const response = await fetch('/api/message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: fullMessage })
                });

        
                const data = await response.json();
                let reply = data.reply;
                const hasPython = reply.includes("```python") || reply.includes("'''python");

        
                // Gérer les blocs de code markdown ```python
                const parts = reply.split(/```(?:python)?\n([\s\S]*?)```/g);
                let formattedReply = "";
        
                for (let i = 0; i < parts.length; i++) {
                    if (i % 2 === 0) {
                        // Texte normal : ajouter <br> à chaque \n
                        formattedReply += parts[i].replace(/\n/g, "<br>");
                    } else {
                        // Bloc de code : ajouter <br> à chaque ligne sauf la dernière
                        const lines = parts[i].split("\n");
                        const codeWithBr = lines.map((line, index) =>
                            index === lines.length - 1 ? line : line + "<br>"
                        ).join("");
                        // ancienne version remplacee par les deux lignes desssous formattedReply += `<pre><code>${codeWithBr}</code></pre>`;

                        const safeCode = escapeHtml(parts[i]);  // on échappe le code
                        formattedReply += `<pre><code>${safeCode}</code></pre>`;
                    }
                }
                const id = uuid();


                  // il suffit de retirer reaction si on veut pas
                  const rawTex = data.reply;
                  let reactionButtons = `
                        <button class="react" data-emoji="❓" title="Expliquer">❓</button>
                        <button class="react" data-emoji="🚩" title="Signaler">🚩</button>
                      `;

                      // après const hasPython...

                      const codeBlocks = extractPythonCodeBlocks(reply);
                      const codePython = codeBlocks.length > 0 ? codeBlocks[0] : "";

                      if (hasPython && codePython) {
                        reactionButtons += `<button class="react react-py" data-emoji="🐍" data-code="${encodeURIComponent(codePython)}" title="Copier dans l’éditeur"><img src="/static/img/icon_python.png" alt="Python" class="emoji-icon"></button>`;
                      }
                      const safeTex = rawTex
                      .replace(/&/g, "&amp;")
                      .replace(/"/g, "&quot;")
                      .replace(/</g, "&lt;")
                      .replace(/>/g, "&gt;");


                      const iaBubble = `
                      <div class="message assistant" data-message-id="${id}">
                        <div class="bubble" data-tex="${safeTex}">${formattedReply}</div>
                        <div class="reactions">
                          ${reactionButtons}
                        </div>
                      </div>
                    `;
                  conv.insertAdjacentHTML('beforeend', iaBubble);
                  scrollConvToBottom();


                if (!isMobile()) {
                  loader.classList.add("hidden");

                }

                MathJax.typesetPromise().then(() => {
                  const conversation = document.getElementById("conversation");
                  setTimeout(() => {
                    conversation.scrollTop = conversation.scrollHeight;
                  }, 100);
                });

                
                // APRÈS réception
                document.getElementById("dot-loader").style.display = "none";
                scrollConvToBottom();


            } catch (error) {


                if (!isMobile()) {
                    loader.classList.add("hidden");
                  }
                
                conversation.innerHTML += "<p style='color:red;'><strong>Erreur :</strong> Impossible de contacter l'assistant.</p>";
            } finally {
              setSendingState(false); // toujours exécuté
            }
        }        
        
          

        function sendMessageMobile() {
          const input = document.getElementById('userInputMobile');
          const desktopInput = document.getElementById('userInput');
          const message = input.value.trim();
        
          const pythonZone = document.getElementById('python-editor');
          let codeText = "";
        
          // Vérifie si l'éditeur est affiché et accessible
          if (pythonZone && pythonZone.style.display === "block" && window.pythonEditor) {
            codeText = window.pythonEditor.getValue().trim();
          }
        
          if (message || codeText) {
            // Optionnel : tu peux toujours injecter dans le champ desktop pour historique ou backup
            if (desktopInput) {
              const rawForDesktop = [message, codeText].filter(Boolean).join("\n");
              desktopInput.value = rawForDesktop;
            }
        
            // Appel CORRECT de sendMessage avec les deux parties
            sendMessage(message, codeText);
        
            // Nettoyage
            input.value = '';
            document.querySelector('.send-btn')?.classList.remove('actif');
        
            if (window.pythonEditor) {
              window.pythonEditor.setValue('');
            }
        
            if (pythonZone && pythonZone.style.display === "block") {
              toggleEditeurPython();
            }
          }
        
          scrollConvToBottom();
        }
        
      


// Fermer clavier et repositionner sur mobile
/*
document.getElementById("userInput").addEventListener("keydown", function (event) {
if (event.key === "Enter") {
event.preventDefault(); // éviter double soumission
sendMessage();
this.blur(); // ferme le clavier mobile


}
});*/





document.getElementById("userInputMobile").addEventListener("keydown", function (event) {
if (event.key === "Enter") {
event.preventDefault(); // éviter double soumission
if (sendingEnCours) return; // ⛔ empêche si déjà en train d’envoyer
sendMessage();
this.blur(); // ferme le clavier mobile

// Double scroll espacé pour compenser le repli clavier
setTimeout(scrollToBottom, 150);
setTimeout(scrollToBottom, 350);
}
});

document.addEventListener("DOMContentLoaded", () => {
const inputMobile = document.getElementById("userInputMobile");
if (inputMobile) {
inputMobile.addEventListener("keydown", (e) => {
if (e.key === "Enter") {
e.preventDefault();
sendMessageMobile();
}
});
}
});





// pour le bouton envoi bloqué marche pas trop 
const inputMobile = document.getElementById('userInputMobile');
const btnMobile   = document.querySelector('.send-btn');

inputMobile.addEventListener('input', updateSendButtonState);

// init python 
document.addEventListener("DOMContentLoaded", () => {
  ensureEditorIsReady();
});


// scroll quand on essaye d'envoyer
let _scrolledOnFocus = false;
inputMobile.addEventListener('focus', () => {
  scrollConvToBottom();
  _scrolledOnFocus = false;
});
inputMobile.addEventListener('keydown', () => {
  if (!_scrolledOnFocus) {
    scrollConvToBottom();
    _scrolledOnFocus = true;
  }
});

// Liste des inputs à « hooker »
['userInputMobile', 'userInput'].forEach(id => {
  const input = document.getElementById(id);
  if (!input) return;
  ['focus', 'click', 'keydown'].forEach(evt =>
    input.addEventListener(evt, scrollConvToBottom)
  );
});





// bouton scroll 
document.addEventListener('DOMContentLoaded', () => {
  const conv      = document.getElementById('conversation');
  const scrollBtn = document.getElementById('scrollToBottomBtn');
  if (!conv || !scrollBtn) return;  // quitte si l'un ou l'autre manquant

  // met à jour la visibilité du bouton
  function updateScrollBtn() {
    const distanceToBottom = conv.scrollHeight - conv.scrollTop - conv.clientHeight;
    scrollBtn.classList.toggle('show', distanceToBottom > 10); // seuil à 10px
  }

  // 1) on place la conversation tout en bas puis on cache ou montre
  scrollConvToBottom();
  updateScrollBtn();

  // 2) dès qu’on scroll dans la boîte, on met à jour l’affichage du bouton
  conv.addEventListener('scroll', updateScrollBtn);

  // 3) clic sur le bouton → scroll en bas + cache le bouton
  scrollBtn.addEventListener('click', () => {
    scrollConvToBottom();
    scrollBtn.classList.remove('show');
  });
});

function extractCodeFromTex(tex) {
  if (!tex) return "";

  const decoded = tex
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#96;/g, "`");

  const match = decoded.match(/```python\s*\n([\s\S]*?)```/);
  return match ? match[1].trim() : "";
}

function decodeTexContent(tex) {
  if (!tex) return "";
  return tex
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#96;/g, "`")
    .replace(/&amp;/g, "&");
}


/////////// react sous les bulles //////
document.addEventListener('DOMContentLoaded', () => {
  const conv = document.getElementById('conversation');
  if (!conv) return;

  conv.addEventListener('click', async e => {
    const btn = e.target.closest('.react');
    if (!btn) return;

    const emoji = btn.dataset.emoji;
    console.log('clic réaction', emoji);  // ① diagnostic
    const msgEl = btn.closest('.message');
    const rawHtml  = msgEl.querySelector('.bubble').innerText.trim();

    if (emoji === '❓') {
      // ② on ré-affiche le texte de la bulle dans une bulle user

      if (btn.classList.contains('reported')) return;
      btn.classList.add('reported');
      btn.disabled = true;
    
      const rawTex = msgEl.querySelector('.bubble').dataset.tex;
      const quoted = decodeTexContent(rawTex).trim();
    
      // 🧠 extraire tous les blocs python pour l'affichage (on garde seulement le premier pour l'instant)
      const codeMatch = quoted.match(/```python\s*\n([\s\S]*?)```/);
      const codeText = codeMatch ? codeMatch[1].trim() : "";
    
      const message = `Peux-tu expliquer un peu ce passage ?\n\n${quoted}`;
    
      sendMessage(message, codeText);

      /*
      const loader = document.getElementById("loader");
      if (!isMobile()) {
        loader.classList.remove("hidden");
      }


      document.getElementById("dot-loader").style.display = "flex";

    // on prend le code TeX stocké, pas le HTML
    const tex = msgEl.querySelector('.bubble').dataset.tex;


    const promptText = `Peux-tu expliquer un peu ce passage ? « ${tex} »`

      // a modifier peut etre pour recopier message avec code 
      const userBubble = `
        <div class="message user">
          <div class="bubble">${promptText}</div>
        </div>
      `;
      conv.insertAdjacentHTML('beforeend', userBubble);
      scrollConvToBottom();


      // relancer le rendu LaTeX
      if (window.MathJax) {
        MathJax.typesetPromise([conv]);
      } else if (window.renderMathInElement) {
        renderMathInElement(conv);
      }
      // ③ envoi à l'API avec la clé "prompt"
      
      
      const res = await fetch('/api/message', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ message: promptText })
      });

      
      const data = await res.json();
      const id = uuid();
      // ④ injection de la réponse IA
      const iaBubble = `
        <div class="message assistant" data-message-id="${id}">
          <div class="bubble" data-tex="${escapeHtml(data.reply)}">${escapeHtml(data.reply)}</div>
               <div class="reactions">
                  <button class="react" data-emoji="❓" title="Expliquer">❓</button>
                  <button class="react" data-emoji="🚩" title="Signaler">🚩</button>
              </div>
        </div>
      `;
      conv.insertAdjacentHTML('beforeend', iaBubble);
      scrollConvToBottom();
      // relancer le rendu LaTeX
      if (window.MathJax) {
        MathJax.typesetPromise([conv]);
      } else if (window.renderMathInElement) {
        renderMathInElement(conv);
      }

      

      if (!isMobile()) {
        loader.classList.add("hidden");
      }document.getElementById("dot-loader").style.display = "none";
      */

    } else if (emoji === '🚩') {
      // 1) Si déjà reporté, on sort
      if (btn.classList.contains('reported')) return;



      await fetch('/api/report', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ message_id: msgEl.dataset.messageId })
      });

        // 3) feedback visuel + désactivation
      btn.classList.add('reported');
       btn.disabled = true;              // bloque le clic

        } else if (emoji === '🐍') {
          const codeBlocks = msgEl.querySelectorAll('pre code');
          if (!codeBlocks.length) return;
        
          // Concaténer tous les blocs de code
          const code = Array.from(codeBlocks)
            .map(el => el.textContent.trim())
            .filter(Boolean)
            .join('\n\n');
        
          if (!code) return;
        
          if (window.toggleEditeurPython && window.pythonEditor) {
            const zone = document.getElementById("python-editor");
            if (zone && zone.style.display !== "block") {
              toggleEditeurPython(); // ouvre si fermé
            }
            window.pythonEditor.setValue(code);
            window.pythonEditor.focus();
          }
        
          btn.classList.add('used');
        }
      
    
    
  });
});



// annimation bouton envoi
document.addEventListener("DOMContentLoaded", () => {
  const sendBtnMobile = document.querySelector('.send-btn');
  if (sendBtnMobile) {
    sendBtnMobile.addEventListener('click', () => {
      sendBtnMobile.classList.add('clicked');
      setTimeout(() => sendBtnMobile.classList.remove('clicked'), 250);
    });
  }
});

// annimation chargement
window.addEventListener('DOMContentLoaded', () => {
  document.body.classList.add('fade-in');
});


// modale info 
function ouvrirModaleInfos() {
  document.getElementById("infoModale").style.display = "flex";
}
function fermerModaleInfos() {
  document.getElementById("infoModale").style.display = "none";
}

// telechargement discussion 
document.addEventListener("DOMContentLoaded", () => {
  console.log("DOM chargé");
  const saveBtn = document.getElementById("btn-save-conv");
  console.log("Bouton trouvé ?", saveBtn);
  if (saveBtn) {
    saveBtn.addEventListener("click", telechargerConversation);
  }
});


// bulle initiale  
document.addEventListener("DOMContentLoaded", () => {
  const firstBubble = document.querySelector("#conversation .message.assistant .bubble");
  if (!firstBubble) return;

  const rawTex = firstBubble.innerText.trim();
  const hasPython = rawTex.includes("```python") || rawTex.includes("'''python");

  let reactionButtons = `
    <button class="react" data-emoji="❓" title="Expliquer">❓</button>
    <button class="react" data-emoji="🚩" title="Signaler">🚩</button>
  `;

  const codeBlocks = extractPythonCodeBlocks(rawTex);
  const codePython = codeBlocks.length > 0 ? codeBlocks[0] : "";

  if (hasPython && codePython) {
    reactionButtons += `<button class="react react-py" data-emoji="🐍" data-code="${encodeURIComponent(codePython)}" title="Copier dans l’éditeur"><img src="/static/img/icon_python.png" alt="Python" class="emoji-icon"></button>`;
  }

  // Ajoute la div .reactions juste après la bulle
  const reactionDiv = document.createElement("div");
  reactionDiv.className = "reactions";
  reactionDiv.innerHTML = reactionButtons;

  firstBubble.parentElement.appendChild(reactionDiv);
});


