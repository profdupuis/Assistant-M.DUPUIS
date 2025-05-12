async function sendMessage(message, codeText = "") {
    if (message === "" && codeText === "") return;


    const loader = document.getElementById("loader");
    if (!isMobile()) {
      loader.classList.remove("hidden");
    }
  
    let codeBlock = codeText ? `\n\`\`\`python\n${codeText}\n\`\`\`` : "";

    
    const fullMessage = [message, codeBlock].filter(Boolean).join("\n");




    const trimmedMessage = message.trim();
    const trimmedCode = codeText.trim();

    codeBlock = trimmedCode ? `\n\`\`\`python\n${trimmedCode}\n\`\`\`` : "";
      


    // Pour l’affichage HTML — sans ligne vide
    const cleanMessage = trimmedMessage.replace(/\n{2,}/g, "\n").trim();


    const conv = document.getElementById("conversation");
      const id = uuid();
      
      const userHtml = `
      <div class="message user" data-message-id="${id}">
        <div class="bubble">
          ${escapeHtml(cleanMessage).replace(/\n/g, "<br>")}
          ${trimmedCode ? `<pre><code class="language-python">${escapeHtml(trimmedCode)}</code></pre>` : ""}
        </div>
      </div>`;
    
      conv.insertAdjacentHTML("beforeend", userHtml);
      scrollConvToBottom();




      userInput.value = '';

      
      setSendingState(true); // désactive tout les envois


  
      scrollConvToBottom() 

  return;

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


                const iaBubble = `
                <div class="message assistant" data-message-id="${id}">
                  <div class="bubble" data-tex="${escapeHtml(rawTex)}">${formattedReply}</div>
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
  

