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
        
            const conversation = document.getElementById('conversation');
            conversation.innerHTML += "<p><strong>Vous :</strong> " + message + "</p>";
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
                

                conversation.innerHTML += `<div><strong>Assistant :</strong> ${formattedReply}</div>`;
  
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
                
                conversation.innerHTML += "<p style='color:red;'><strong>Erreur :</strong> Impossible de contacter HYDRA.</p>";
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
