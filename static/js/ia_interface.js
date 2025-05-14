window.lastUsedLang = "python"; // accessible globalement
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
  if (window._currentCodeMirror && editorVisible) {
    code = window._currentCodeMirror.getValue().trim();
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

function extractCodeBlocksByLang(text, lang) {
  if (!text) return [];

  const decoded = text
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#96;/g, "`")
    .replace(/&amp;/g, "&");

  const blocks = [];
  const regex = new RegExp("```" + lang + "\\s*\\n([\\s\\S]*?)```", "g");
  let match;
  while ((match = regex.exec(decoded)) !== null) {
    blocks.push(match[1].trim());
  }
  return blocks;
}


function renderUserBubble(id, message, codeText) {
  const decodedMessage = message
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#96;/g, "`")
    .replace(/&amp;/g, "&")
    .trim();

  // 🧠 On découpe le message en blocs Markdown : texte et blocs ```lang\ncode```
  const parts = decodedMessage.split(/```([a-z]*)\n([\s\S]*?)```/g); // texte, lang, code, texte, lang, code...

  const chunks = [];

  for (let i = 0; i < parts.length; i += 3) {
    const text = parts[i];
    const lang = parts[i + 1];
    const code = parts[i + 2];

    if (text && text.trim()) {
      chunks.push(`<div>${escapeHtml(text.trim()).replace(/\n/g, "<br>")}</div>`);
    }

    if (code) {
      const language = lang || "plaintext";
      chunks.push(`<pre><code class="language-${language}">${escapeHtml(code.trim())}</code></pre>`);
    }
  }

  // ✅ N'ajoute codeText QUE s'il n'est pas déjà dans le message markdowné
  const includeExtra = codeText.trim() && !message.includes("```");

  const extraCode = includeExtra
    ? `<pre><code class="language-python">${escapeHtml(codeText.trim())}</code></pre>`
    : "";

  return `
    <div class="message user" data-message-id="${id}">
      <div class="bubble">${chunks.join("\n")}${extraCode}</div>
    </div>`;
}



        
  async function sendMessage(message, codeText = "",hiddenPrompt = null) {


            if (message.trim() === "" && codeText.trim() === "") return;

            let lang = window.lastUsedLang || "python";
            let codeBlock = codeText ? `\n\`\`\`${lang}\n${codeText}\n\`\`\`` : "";

          
            const fullMessage = [message, hiddenPrompt,codeBlock].filter(Boolean).join("\n");

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


                const formattedReply = formatCodeBlocks(reply);



                



                const hasPython = reply.includes("```python") || reply.includes("'''python");
                const hasSQL = reply.includes("```sql") || reply.includes('<code data-lang="sql"');



                const id = uuid();


                  // il suffit de retirer reaction si on veut pas
                  const rawTex = data.reply;
                  let reactionButtons = `
                        <button class="react" data-emoji="❓" title="Expliquer">❓</button>
                        <button class="react" data-emoji="🚩" title="Signaler">🚩</button>
                        <button class="react" data-emoji="🔄" title="Signaler">🔄</button>
                      `;

                      // après const hasPython...

                      const codeBlocks = extractPythonCodeBlocks(reply);
                      const codePython = codeBlocks.length > 0 ? codeBlocks[0] : "";

                      if (hasPython && codePython) {
                        reactionButtons += `<button class="react react-py" data-emoji="🐍" data-code="${encodeURIComponent(codePython)}" title="Copier dans l’éditeur"><img src="/static/img/icon_python.png" alt="Python" class="emoji-icon"></button>`;
                      }

                      const codeBlocksSQL = extractCodeBlocksByLang(reply, "sql");
                      const codeSQL = codeBlocksSQL.length > 0 ? codeBlocksSQL[0] : "";



                      if (rawTex.includes("🧩") && rawTex.includes("EXERCICE")) {
                        const numMatch = rawTex.match(/EXERCICE\s+(\d+)/);
                        const numEx = numMatch ? numMatch[1] : "?";

                        reactionButtons += `
                          <button class="react" data-emoji="➕" title="Exercice similaire">➕</button>
                        `;
                      }

                      if (hasSQL && codeSQL) {
                        reactionButtons += `
                          <button class="react react-sql" data-emoji="🧮" data-code="${encodeURIComponent(codeSQL)}" title="Copier dans l’éditeur SQL">
                            <img src="/static/img/icon_sql.png" alt="SQL" class="emoji-icon">
                          </button>
                        `;
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




                MathJax.typesetPromise().then(() => {
                  const conversation = document.getElementById("conversation");
                  setTimeout(() => {
                    conversation.scrollTop = conversation.scrollHeight;
                  }, 100);
                });

                

                scrollConvToBottom();


            } catch (error) {


                if (!isMobile()) {
                    loader.classList.add("hidden");
                  }
                
                conversation.innerHTML += "<p style='color:red;'><strong>Erreur :</strong> Impossible de contacter l'assistant.</p>";
            } finally {
              setSendingState(false); // toujours exécuté
              document.getElementById("dot-loader").style.display = "none";
            }
        }        
        
          

        function sendMessageMobile() {
          const input = document.getElementById('userInputMobile');
          const desktopInput = document.getElementById('userInput');
          const message = input.value.trim();
        
          const pythonZone = document.getElementById('python-editor');
          let codeText = "";
          // ✅ Récupère dynamiquement le code en cours, quel que soit le langage
          const editorVisible = pythonZone && pythonZone.style.display === "block";
          if (editorVisible && window._currentCodeMirror) {
            codeText = window._currentCodeMirror.getValue().trim();
          }

        
          if (message || codeText) {
            // Optionnel : tu peux toujours injecter dans le champ desktop pour historique ou backup
            if (desktopInput) {
              const rawForDesktop = [message, codeText].filter(Boolean).join("\n");
              desktopInput.value = rawForDesktop;
            }
        
            // Appel CORRECT de sendMessage avec les deux parties
            window.lastUsedLang = window._currentCodeMirror?.getOption("mode") || "python";
            // 3. Appelle sendMessage avec le code SEULEMENT s’il est visible
            sendMessage(message, editorVisible ? codeText : "");
        
            // Nettoyage
            input.value = '';
            document.querySelector('.send-btn')?.classList.remove('actif');
        
            // 4. N’efface le code que si on l’a effectivement envoyé
            /*
            if (editorVisible && codeText) {
              window._currentCodeMirror.setValue('');
            }*/

            // ✅ Ferme proprement
            if (editorVisible) {
              document.getElementById("python-editor").style.display = "none";
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
if (event.key === "Enter" && !event.shiftKey) {
event.preventDefault(); // éviter double soumission
if (sendingEnCours) return; // ⛔ empêche si déjà en train d’envoyer
sendMessageMobile();
this.blur(); // ferme le clavier mobile

// Double scroll espacé pour compenser le repli clavier
setTimeout(scrollToBottom, 150);
setTimeout(scrollToBottom, 350);
}
});


/*
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

*/



// pour le bouton envoi bloqué marche pas trop 
const inputMobile = document.getElementById('userInputMobile');
const btnMobile   = document.querySelector('.send-btn');

inputMobile.addEventListener('input', updateSendButtonState);

// init python 
document.addEventListener("DOMContentLoaded", () => {
  ensureEditor();
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
    
      /* 🧠 extraire tous les blocs python pour l'affichage (on garde seulement le premier pour l'instant)
      const codeMatch = quoted.match(/```python\s*\n([\s\S]*?)```/);
      const codeText = codeMatch ? codeMatch[1].trim() : "";*/
    
      const message = `Peux-tu expliquer un peu ce passage ?\n\n${quoted}`;
    
      //sendMessage(message, codeText);
      sendMessage(message);



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
          const allCodeBlocks = msgEl.querySelectorAll('pre code[data-lang="python"]');
          if (!allCodeBlocks.length) return;

          const code = Array.from(allCodeBlocks)
            .map(el => el.textContent.trim())
            .filter(Boolean)
            .join('\n\n');

          if (!code) return;

          // Toggle : si éditeur déjà ouvert en python → referme
          const zone = document.getElementById("python-editor");
          const isAlreadyOpen = zone.style.display === "block" && window._currentCodeMirror?.getOption("mode") === "python";

          if (isAlreadyOpen) {
            zone.style.display = "none";
            return;
          }

          ouvrirEditeurDepuisReaction(code, "python");
          btn.classList.add('used');
        }else if (emoji === '🧮') {
          const allSQLBlocks = msgEl.querySelectorAll('pre code[data-lang="sql"]');
          if (!allSQLBlocks.length) return;

          const code = Array.from(allSQLBlocks)
            .map(el => el.textContent.trim())
            .filter(Boolean)
            .join('\n\n');

          if (!code) return;

          const zone = document.getElementById("python-editor");
          const isAlreadyOpen = zone.style.display === "block" && window._currentCodeMirror?.getOption("mode") === "sql";

          if (isAlreadyOpen) {
            zone.style.display = "none";
            return;
          }

          ouvrirEditeurDepuisReaction(code, "sql");
          btn.classList.add('used');
        }

        
        
        else if (emoji === "➕") {
            
            btn.classList.add('reported');
            //btn.disabled = true;

            const rawTex = msgEl.querySelector('.bubble').dataset.tex;
            const quoted = decodeTexContent(rawTex).trim();

            const match = quoted.match(/EXERCICE\s+(\d+)/i);
            const numEx = match ? match[1] : "?";
            const hiddenPrompt = `⚠️ System :
             Propose un exercice du même type que celui demandé par l'élève, en gardant le même format (🧩 EXERCICE N, niveau x, LaTeX, etc.).

            Lorsque tu proposes un nouvel exercice, commence toujours par une ligne de type :
            🧩 EXERCICE N (niveau x)
            avec N un identifiant unique cohérent commençant par un nombre (par exemple 2bis, 4ter, etc.), même si c’est toi qui inventes l’exercice.

            ⚠️ Cet exercice est proposé par toi-même pour l'entraînement.
            Ne conclus jamais ta réponse pour les exercices que TU proposes par : "EXERCICE TERMINE : ✅", même si la réponse est correcte.

            Tu peux toutefois utiliser ✅ pour indiquer une bonne réponse, et ❌ pour signaler une erreur, afin que cela soit comptabilisé dans les statistiques de l’élève.

            N'écris pas "*Fin de l'énoncé*".`;


            const message = `➕ Propose un exercice du même type que l’exercice ${numEx}.`;

            
            sendMessage(message,"",hiddenPrompt);
        }else if (emoji === "🔄") {
            btn.classList.add('reported');

            const rawTex = msgEl.querySelector('.bubble').dataset.tex;
            const quoted = decodeTexContent(rawTex).trim();

            const visibleMessage = `🔄 Peux-tu vérifier si cette réponse termine bien l’exercice en cours ?`;
            const systemPrompt = `⚠️ System :
             Évalue discrètement si la réponse de l’élève permet de conclure l’exercice en cours et ce n'est valable que pour les exercices de la fiche, pas ceux que tu inventes.  
              Si oui, termine ta réponse par : "EXERCICE TERMINE : ✅"  
              Sinon, explique ce qui manque pour valider l’exercice.  
              Ne commente pas la consigne, et n'explique pas que tu vas écrire quoi que ce soit.`;

            sendMessage(visibleMessage, "", systemPrompt);
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
  fermerHamburgerMenu() ;
  fermerAccordeons();
  document.getElementById("infoModale").style.display = "flex";
}
function fermerModaleInfos() {
  document.getElementById("infoModale").style.display = "none";
}




function formatCodeBlocks(text) {
  const parts = text.split(/```([a-z]*)\n([\s\S]*?)```/g);
  let output = "";

  for (let i = 0; i < parts.length; i += 3) {
    const before = parts[i];
    const lang = parts[i + 1];
    const code = parts[i + 2];

    const cleaned = before.replace(/\n$/g, ""); // évite <br> final inutile
    output += cleaned.replace(/\n/g, "<br>");

    if (code) {
      const safe = escapeHtml(code.trim());
      output += `<pre><code data-lang="${lang || 'plaintext'}">${safe}</code></pre>`;
    }
  }

  return output;
}



// bulle initiale  
document.addEventListener("DOMContentLoaded", () => {
  const firstBubble = document.querySelector("#conversation .message.assistant .bubble");
  if (!firstBubble) return;

  const rawTex = firstBubble.innerText.trim();
  const hasPython = rawTex.includes("```python") || rawTex.includes("'''python");
  const hasSQL = rawTex.includes("```sql") || rawTex.includes('<code data-lang="sql"');
  
  const formatted = formatCodeBlocks(rawTex);
  firstBubble.innerHTML = formatted;


  let reactionButtons = `
    <button class="react" data-emoji="❓" title="Expliquer">❓</button>
    <button class="react" data-emoji="🚩" title="Signaler">🚩</button>
    <button class="react" data-emoji="🔄" title="Signaler">🔄</button>
  `;

  const codeBlocks = extractCodeBlocksByLang(rawTex, "python");
  const codePython = codeBlocks.length > 0 ? codeBlocks[0] : "";

  const codeBlocksSQL = extractCodeBlocksByLang(rawTex, "sql");
  const codeSQL = codeBlocksSQL.length > 0 ? codeBlocksSQL[0] : "";



  if (hasPython && codePython) {
    reactionButtons += `<button class="react react-py" data-emoji="🐍" data-code="${encodeURIComponent(codePython)}" title="Copier dans l’éditeur"><img src="/static/img/icon_python.png" alt="Python" class="emoji-icon"></button>`;
  }
if (hasSQL && codeSQL) {
  reactionButtons += `<button class="react react-sql" data-emoji="🧮" data-code="${encodeURIComponent(codeSQL)}" title="Copier dans l’éditeur SQL"><img src="/static/img/icon_sql.png" alt="SQL" class="emoji-icon"></button>`;
                      }
  if (rawTex.includes("🧩") && rawTex.includes("EXERCICE")) {
      const numMatch = rawTex.match(/EXERCICE\s+(\d+)/);
      const numEx = numMatch ? numMatch[1] : "?";

      reactionButtons += `<button class="react" data-emoji="➕" title="Exercice similaire">➕</button>`;
  }
  // Ajoute la div .reactions juste après la bulle
  const reactionDiv = document.createElement("div");
  reactionDiv.className = "reactions";
  reactionDiv.innerHTML = reactionButtons;

  firstBubble.parentElement.appendChild(reactionDiv);
});



// non au zoom double tap
document.addEventListener("touchstart", function (e) {
  if (e.touches.length > 1) e.preventDefault();
}, { passive: false });

let lastTouchEnd = 0;
document.addEventListener("touchend", function (e) {
  const now = new Date().getTime();
  if (now - lastTouchEnd <= 300) e.preventDefault();
  lastTouchEnd = now;
}, false);





