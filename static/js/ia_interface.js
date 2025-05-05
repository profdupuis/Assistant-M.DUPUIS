// en haut du fichier
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

function setSendingState(isSending) {
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
  //if (inputDesktop) inputDesktop.readOnly = isSending;
  //if (inputMobile) inputMobile.readOnly = isSending;
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




        
        async function sendMessage() {
            const userInput = document.getElementById('userInput');
            const message = userInput.value.trim();

            
            const loader = document.getElementById("loader");
            if (!isMobile()) {
              loader.classList.remove("hidden");
            }



            if (!message) return;

            const conv = document.getElementById('conversation');
            conv.insertAdjacentHTML(
              'beforeend',
              `<div class="message user">
                 <div class="bubble">${escapeHtml(message)}</div>
               </div>`
            );






            userInput.value = '';




        
            scrollConvToBottom() 

            try {
              setSendingState(true); // désactive tout les envois
                // AVANT la requête (dot loader)

                document.getElementById("dot-loader").style.display = "flex";


                const response = await fetch('/api/message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });

        
                const data = await response.json();
                let reply = data.reply;
        
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
                        formattedReply += `<pre><code>${codeWithBr}</code></pre>`;
                    }
                }
                const id = uuid();


                  // il suffit de retirer reaction si on veut pas
                  const rawTex = data.reply;
                  const iaBubble = `<div class="message assistant" data-message-id="${id}">
                      <div class="bubble" data-tex="${rawTex}">${rawTex}</div>
                      <div class="reactions">
                        <button class="react" data-emoji="❓" title="Expliquer">❓</button>
                        <button class="react" data-emoji="🚩" title="Signaler">🚩</button>
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
  const message = input.value.trim();
  if (message) {
    document.getElementById('userInput').value = message;
    sendMessage();
    input.value = '';

  }
  scrollConvToBottom();
}





// Fermer clavier et repositionner sur mobile
document.getElementById("userInput").addEventListener("keydown", function (event) {
if (event.key === "Enter") {
event.preventDefault(); // éviter double soumission
sendMessage();
this.blur(); // ferme le clavier mobile


}
});





document.getElementById("userInputMobile").addEventListener("keydown", function (event) {
if (event.key === "Enter") {
event.preventDefault(); // éviter double soumission
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






const inputMobile = document.getElementById('userInputMobile');
const btnMobile   = document.querySelector('.send-btn');

inputMobile.addEventListener('input', () => {
  btnMobile.disabled = inputMobile.value.trim() === '';
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


      const loader = document.getElementById("loader");
      if (!isMobile()) {
        loader.classList.remove("hidden");
      }
      document.getElementById("dot-loader").style.display = "flex";

    // on prend le code TeX stocké, pas le HTML
    const tex = msgEl.querySelector('.bubble').dataset.tex;


    const promptText = `Peux-tu expliquer un peu ce passage ? « ${tex} »`


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

      btn.classList.add('reported');
      btn.disabled = true;  

      if (!isMobile()) {
        loader.classList.add("hidden");
      }document.getElementById("dot-loader").style.display = "none";


    } else if (emoji === '🚩') {
      // 1) Si déjà reporté, on sort
      if (btn.classList.contains('reported')) return;



      await fetch('/api/report', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ message_id: msgEl.dataset.messageId })
      });
      btn.classList.add('reported');
        // 3) feedback visuel + désactivation
  btn.classList.add('reported');
  btn.disabled = true;              // bloque le clic
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