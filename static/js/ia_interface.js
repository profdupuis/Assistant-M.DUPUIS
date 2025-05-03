        document.getElementById("userInput").addEventListener("keydown", function(event) {
            if (event.key === "Enter") {
                event.preventDefault();
                sendMessage();
            }
        });

        
function isMobile() {
    return window.matchMedia("(max-width: 768px)").matches;
  }




        function afficherTexteLigneParLigne(htmlContent, container, delay = 150) {
            const tempDiv = document.createElement("div");
            container.appendChild(tempDiv);
        
            const lignes = htmlContent.split(/<br\s*\/?>/gi);
            let i = 0;
        
            const titre = document.createElement("div");
            titre.innerHTML = "<strong>Assistant :</strong>";
            tempDiv.appendChild(titre);
        
            function afficherLigne() {
                if (i < lignes.length) {
                    const ligne = lignes[i].trim();
                    const ligneDiv = document.createElement("div");
        
                    if (ligne) {
                        ligneDiv.innerHTML = ligne;
                    } else {
                        ligneDiv.innerHTML = "<br>";
                    }
        
                    tempDiv.appendChild(ligneDiv);
        
                    // 🔧 Scroll avec compensation pour la barre fixe
                    setTimeout(() => {
                        const yOffset = -160; // HAUTEUR estimée de la barre + champ
                        const rect = ligneDiv.getBoundingClientRect();
                        const absoluteY = window.scrollY + rect.top + yOffset;
                        window.scrollTo({ top: absoluteY, behavior: 'smooth' });
                    }, 20);
        
                    i++;
                    setTimeout(afficherLigne, delay);
                } else {
                    if (window.MathJax) MathJax.typesetPromise([tempDiv]);
                }
            }
        
            afficherLigne();
        }
        
        
        async function sendMessage() {
            const userInput = document.getElementById('userInput');
            const message = userInput.value.trim();
            
            const loader = document.getElementById("loader");
            if (!isMobile()) {
              loader.classList.remove("hidden");
            }


            if (!message) return;


            if (!message) return;
        
            const conversation = document.getElementById('conversation');
            conversation.innerHTML += "<p><strong>Vous :</strong> " + message + "</p>";
            userInput.value = '';
        
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
                
                if (!isMobile()) {
                    loader.classList.add("hidden");
                  }

                conversation.innerHTML += `<div><strong>Assistant :</strong> ${formattedReply}</div>`;
        
        
                MathJax.typeset();
                conversation.scrollTop = conversation.scrollHeight;
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
            }
          }
          





// Forcer le scroll vers le bas quand une réponse est ajoutée
function scrollToBottom() {
    const conversation = document.getElementById("conversation");
    const lastElement = conversation.lastElementChild;
  
    if (lastElement) {
      setTimeout(() => {
        lastElement.scrollIntoView({ behavior: "smooth", block: "end" });
      }, 100); // petit délai pour laisser le DOM se rafraîchir
    }
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
  