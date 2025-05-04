// en haut du fichier
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

                // AVANT la requête (dot loader)
                document.getElementById("dot-loader").style.display = "flex";


                const response = await fetch('/api/message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });

                // APRÈS réception
                document.getElementById("dot-loader").style.display = "none";
        
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
                
                  // il suffit de retirer reaction si on veut pas
                const iaBubble = `
                <div class="message assistant">
                  <div class="bubble">${escapeHtml(data.reply)}</div>
                    <div class="reactions">
                    <button class="react" data-emoji="❓" title="Expliquer">❓ <span class="count"></span></button>
                    <button class="react" data-emoji="⚑" title="Signaler">⚑ <span class="count"></span></button>
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
                scrollConvToBottom();

            } catch (error) {

                if (!isMobile()) {
                    loader.classList.add("hidden");
                  }
                
                conversation.innerHTML += "<p style='color:red;'><strong>Erreur :</strong> Impossible de contacter l'assistant.</p>";
            }
        }        
        
          











function sendMessageMobile() {
  const input = document.getElementById('userInputMobile');
  const message = input.value.trim();
  if (message) {
    document.getElementById('userInput').value = message;
    sendMessage();
    input.value = '';
    const btnMobile = document.querySelector('.send-btn'); // <— redéclaré ici
btnMobile.disabled = true;
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


      const loader = document.getElementById("loader");
      if (!isMobile()) {
        loader.classList.remove("hidden");
      }



      const promptText = `Peux tu réexpliquer ce passage ? « ${rawHtml} »`;


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

      // ④ injection de la réponse IA
      const iaBubble = `
        <div class="message assistant">
          <div class="bubble">${escapeHtml(data.reply)}</div>
               <div class="reactions">
                  <button class="react" data-emoji="❓" title="Expliquer">❓</button>
                  <button class="react" data-emoji="⚑" title="Signaler">⚑</button>
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
      }


    } else if (emoji === '⚑') {
      await fetch('/api/report', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ message_id: msgEl.dataset.messageId })
      });
      btn.classList.add('reported');
    }
  });
});
