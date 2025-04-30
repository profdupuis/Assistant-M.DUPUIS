        document.getElementById("userInput").addEventListener("keydown", function(event) {
            if (event.key === "Enter") {
                event.preventDefault();
                sendMessage();
            }
        });
        
        async function sendMessage() {
            const userInput = document.getElementById('userInput');
            const message = userInput.value.trim();
            const loader = document.getElementById("loader");
            
            loader.classList.remove("hidden");


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
                
                loader.classList.add("hidden");

                conversation.innerHTML += `<div><strong>Assistant :</strong> ${formattedReply}</div>`;
        
        
                MathJax.typeset();
                conversation.scrollTop = conversation.scrollHeight;
            } catch (error) {

                loader.classList.add("hidden");
                
                conversation.innerHTML += "<p style='color:red;'><strong>Erreur :</strong> Impossible de contacter HYDRA.</p>";
            }
        }