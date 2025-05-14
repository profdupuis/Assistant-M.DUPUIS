"""
Fonctions d'export LaTeX et texte brut pour les conversations assistant-élève.

Ce module fournit :
- la conversion des messages assistant/élève (cconv) en format LaTeX ou TXT
- le nettoyage des caractères problématiques pour LaTeX
- la normalisation des titres d'exercice
- la découpe intelligente des messages en sections par exercice
- la compilation automatique d'un fichier PDF via pdflatex
- un fallback vers un fichier texte brut si la génération LaTeX échoue

Les formats gérés :
- `.pdf` (via LaTeX) avec math, code (`lstlisting`), titres, rôles
- `.txt` structuré par exercice avec indentation

Dépendances :
- Flask (session, logger)
- SQLAlchemy (text)
- pdflatex (doit être installé pour produire les fichiers PDF)

Ce module est destiné à être utilisé dans un contexte Flask avec une session active.
"""


import os
import re
import tempfile
import subprocess
from io import StringIO
from textwrap import indent
from collections import defaultdict

from flask import session, Response, send_file, current_app as app
from sqlalchemy import text


def normalize_quotes(text):
    """
    Remplace les guillemets typographiques et caractères similaires par leurs équivalents simples.

    - Remplace les apostrophes et guillemets typographiques (‘’, “”) par ' et "
    - Corrige les accents mal encodés et backticks isolés
    - Évite les erreurs dans LaTeX ou dans le traitement de texte brut

    Retourne une version normalisée du texte.
    """
    return (
        text.replace("‘", "'")
            .replace("’", "'")
            .replace("“", '"')
            .replace("”", '"')
            .replace("´", "'")     # accent aigu mal converti
            .replace("`", "'")     # backtick isolé (souvent problématique en LaTeX)
            .replace("‛", "'")     # single high-reversed-9 quote
            .replace("″", '"')     # double prime
            .replace("‶", '"')     # double high-reversed-9 quote
    )


def normaliser_titre_exo(raw: str) -> str:
    """
    Convertit un titre d'exercice en forme homogène : Exercice X [niveau Y]
    """
    if not raw:
        return "Introduction"
    raw = raw.strip()

    # Majuscules normalisées → minuscules, capitalise ensuite
    raw = raw.lower()

    # Uniformisation : EXERCICE X (niveau Y) → Exercice X [niveau Y]
    raw = raw.replace("exercice", "Exercice")
    raw = raw.replace("(", "[")
    raw = raw.replace(")", "]")

    return raw


def clean_code_block_for_latex(code):
    """
    Nettoie un bloc de code destiné à un environnement LaTeX lstlisting.

    - Remplace certaines commandes LaTeX techniques (\cf, \tg, \ln) par leur équivalent texte
    - Supprime les caractères non-ASCII (emoji, symboles invisibles)
    - Laisse le reste du code intact

    Retourne un code nettoyé, compatible avec \begin{lstlisting}...\end{lstlisting}.
    """
    code = code.replace(r"\cf", "cf")
    code = code.replace(r"\tg", "tan")
    code = code.replace(r"\ln", "log")
    code = re.sub(r'[^\x00-\x7F]+', '', code)
    return code

def sanitize_tex(text):
    """Nettoie une chaîne pour LaTeX en échappant les caractères spéciaux et en supprimant les emojis."""
    if not text:
        return ""
    # Remplacer les caractères spéciaux LaTeX
    replacements = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
        '\\': r'\textbackslash{}',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Supprimer TOUS les caractères Unicode non-ASCII (emoji, symboles spéciaux)
    text = re.sub(r'[^\x00-\x7F]+', '', text)

    return text


def sanitize_tex_preserving_math(text: str) -> str:
    """
    Prépare un texte pour une insertion sûre dans un document LaTeX.

    Cette fonction :
    - remplace les guillemets typographiques et normalise les apostrophes
    - supprime les caractères Unicode non compatibles (emojis, etc.)
    - protège les blocs \texttt{...} pour éviter qu'ils ne soient échappés
    - échappe tous les caractères spéciaux LaTeX en dehors des environnements mathématiques
    - applique le rendu \textbf{...} pour les doubles astérisques (Markdown → LaTeX)
    - conserve intactes les formules mathématiques dans \(...\), \[...\] ou $$...$$

    Retourne le texte formaté, prêt à être inséré dans un document LaTeX.
    """
    text = normalize_quotes(text)

    # 🔴 Supprime les emojis et autres caractères unicode problématiques
    text = re.sub(r'[^\x00-\xFF]', '', text)

    math_pattern = re.compile(r'(\\\(.+?\\\)|\\\[.+?\\\]|\$\$.+?\$\$)', re.DOTALL)
    parts = math_pattern.split(text)

    protected_texttt = []

    def protect_texttt(match):
        protected_texttt.append(match.group(0))
        return f"__TEXTTT_{len(protected_texttt)}__"

    text = re.sub(r'\\texttt\{[^}]*\}', protect_texttt, text)

    sanitized_parts = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            sanitized_parts.append(part)
        else:
            replacements = {
                '&': r'\&',
                '%': r'\%',
                '$': r'\$',
                '#': r'\#',
                '_': r'\_',
                '{': r'\{',
                '}': r'\}',
                '~': r'\textasciitilde{}',
                '^': r'\textasciicircum{}',#'\\': r'\textbackslash{}',
            }
            for old, new in replacements.items():
                part = part.replace(old, new)

            part = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', part)
            part = re.sub(r'\n{2,}', '\n\n', part)
            sanitized_parts.append(part)

    final_text = ''.join(sanitized_parts)

    # Restaurer les blocs \texttt{...} protégés
    for i, original in enumerate(protected_texttt):
        final_text = final_text.replace(f"__TEXTTT_{i}__", original)

    return final_text


def filter_latex_macros(tex):
    """
    Filtre certaines macros LaTeX mathématiques mal interprétées et les remplace par leur équivalent texte.

    - Remplace \cf par cf
    - Remplace \tg par tan
    - Remplace \ln par log
    - Ne remplace que les macros isolées (\macro suivies d’un espace, point, etc.)

    Utile pour corriger automatiquement les notations GPT non compatibles ou non souhaitées dans un contexte PDF.
    """
    tex = re.sub(r'\\cf\b', r'cf', tex)
    tex = re.sub(r'\\tg\b', r'tan', tex)
    tex = re.sub(r'\\ln\b', r'log', tex)
    return tex


def format_content_latex(content):
    """
    Transforme un contenu texte enrichi (Markdown simplifié) en LaTeX.

    - Détecte et extrait les blocs de code Markdown (```lang\ncode```), rendus en \\begin{lstlisting}...\end{lstlisting}
    - Traite le texte hors code avec sanitize_tex_preserving_math() pour échapper les caractères LaTeX
    - Corrige les blocs mathématiques \\[...\\] et $$...$$ mal formés
    - Retourne un contenu LaTeX prêt à être injecté dans le document (section, message IA, etc.)

    Cette fonction suppose que `content` contient un format de type Markdown minimal, tel qu’utilisé par l’IA dans les réponses structurées.
    """
    parts = re.split(r"```([a-z]*)\n([\s\S]*?)```", content)
    latex = ""

    for i in range(0, len(parts), 3):
        texte = parts[i].strip()
        if texte:
            # Élimine tous les sauts de ligne problématiques dans les \[...\]
            texte = re.sub(r'\\\[(.+?)\\\]', 
                           lambda m: "\\[" + " ".join(m.group(1).split()) + "\\]", 
                           texte, 
                           flags=re.DOTALL)
            
            # Même nettoyage pour $$...$$
            texte = re.sub(r'\$\$(.+?)\$\$', 
                           lambda m: "\\[" + " ".join(m.group(1).split()) + "\\]", 
                           texte, 
                           flags=re.DOTALL)
            latex += sanitize_tex_preserving_math(texte).replace("\n", "\n\n") + "\n\n"

        if i + 2 < len(parts):
            lang = parts[i+1].strip()
            code = parts[i+2].strip()

            code = clean_code_block_for_latex(code)

            latex += r"\begin{lstlisting}" + "\n"
            latex += code + "\n"
            latex += r"\end{lstlisting}" + "\n\n"

    return latex



def retirer_prompt_cache(content: str, role: str) -> str:
    """
    Supprime les parties de message utilisateur qui commencent à ⚠️ (prompt caché).
    Utilisé pour les exports PDF/TXT.
    """
    if role in ("user", "élève"):
        return content.split("⚠️")[0].strip()
    return content.strip()

def tri_exercice_key(titre: str):
    """
    Extrait un tuple de tri à partir d'un titre de type :
    'Exercice 1', 'Exercice 1bis', 'Exercice 2', etc.
    
    Renvoie (numéro, suffixe) → ex : (1, 'bis') ou (2, '').
    Si échec : renvoie un tuple très haut pour aller à la fin.
    """
    match = re.search(r'exercice\s+(\d+)([a-z]*)', titre.lower())
    if match:
        num = int(match.group(1))
        suffixe = match.group(2)
        return (num, suffixe)
    return (9999, titre.lower())  # fallback


def decouper_conversation_par_exercice(history):
    """
    Découpe les messages en sections :
    - Introduction (meta.subtype = intro)
    - Exercices (par "exo" ou 🧩)
    - Bilan final (meta.subtype = feedback)
    """

    sections = defaultdict(list)
    current_exo = None

    for msg in history:
        role = msg.get("role", "")
        content = retirer_prompt_cache(msg.get("content", ""), role)
        subtype = msg.get("subtype", None)
        
        if not content:
            continue
        
        # --- Gestion des messages META avec subtype ---
        if role == "meta":
            if subtype == "intro":
                sections["Introduction"].append((role, subtype, content))
            elif subtype == "feedback":
                sections["📝 Bilan final"].append((role, subtype, content))
            else:
                sections["📝 Bilan final"].append((role, subtype, content))  # Par défaut
            continue
        
        # --- Navigation vers un exo (depuis bouton ou commande texte) ---
        if role == "exo":
            current_exo = content.split(":")[0].strip()
            continue  # l'énoncé sera ajouté dynamiquement via MAP_JSON

        # --- Détection d’un exo généré dynamiquement par l’IA (🧩) ---
        if role == "assistant":
            lines = content.splitlines()
            for line in lines:
                if line.strip().startswith("🧩"):
                    titre = line.strip("🧩 ").split(":")[0].strip()
                    current_exo = titre
                    if current_exo not in sections:
                        sections[current_exo] = []
                    break
        if current_exo not in sections:
            sections[current_exo] = []

        sections[current_exo].append((role, subtype, content))

    # 🟢 Tri explicite des sections : intro → exos (triés) → bilan
    ordered_sections = {}

    # Intro d'abord
    if "Introduction" in sections:
        ordered_sections["Introduction"] = sections.pop("Introduction")

    # Exercices par ordre alphabétique (ex : Exercice 1, Exercice 2, Exercice 2bis, etc.)
    for k in sorted(sections.keys(), key=tri_exercice_key):  # version 1 simple
        if not k.startswith("📝"):
            ordered_sections[k] = sections[k]

    # Feedback à la fin
    if "📝 Bilan final" in sections:
        ordered_sections["📝 Bilan final"] = sections.pop("📝 Bilan final")

    return ordered_sections



def build_conversation_txt(engine):
    """
    Construit une version texte brute de la conversation, organisée par exercice.
    """


    history = session.get("cconv", [])
    if not history:
        app.logger.warning("TXT : aucun historique dans cconv.")
        return ""

    # Récupération des infos de contexte
    matiere = session.get("active_matiere", "Inconnue").capitalize()
    scenario_id = session.get("active_scenario_id")
    scenario_name = "Scénario en cours"

    with engine.connect() as cn:
        scenario_name = cn.scalar(text("""
            SELECT name FROM scenarios WHERE id = :sid
        """), {"sid": scenario_id}) or scenario_name
        
        
    # creation des sections
    sections = decouper_conversation_par_exercice(history)

    # Génération du contenu brut
    output = StringIO()
    output.write(f"🧠 Conversation pédagogique\n")
    output.write(f"Matière : {matiere}\n")
    output.write(f"Fiche : {scenario_name}\n\n")

    for section, messages in sections.items():
        titre_section = section
        if section == "📝 Bilan final":
            titre_section = "Bilan final"

        output.write(f"========== {titre_section or 'Introduction'} ==========\n\n")

        # Injection automatique de l'énoncé si section = "Exercice X"
        ref = extract_ref_from_section_title(section)
        if ref and ref in session.get("MAP_JSON", {}):
            enonce = session["MAP_JSON"][ref].strip()
            enonce = retirer_premiere_ligne_si_titre(enonce)
            output.write(indent(enonce, "    "))
            output.write("\n\n")
        for role, subtype, content in messages:
            if role == "meta":
                label = {
                    "intro": "Note d’introduction",
                    "feedback": "Bilan final"
                }.get(subtype, "Note système")
            else:
                label = {
                    "user": "Élève",
                    "assistant": "Assistant IA"
                }.get(role, role.capitalize())
            # 🔍 Supprime le titre redondant dans les réponses assistant IA
            if role == "assistant":
                lines = content.strip().splitlines()
                if lines and lines[0].strip().lower().startswith("🧩 exercice"):
                    content = "\n".join(lines[1:]).strip()
            output.write(f"--- {label} ---\n")
            output.write(indent(content.strip(), "    "))
            output.write("\n\n")

    return output.getvalue()

def extract_ref_from_section_title(title: str) -> str | None:
    """
    À partir d'un titre de section du type 'EXERCICE 2bis [niveau 1]',
    extrait la référence 'exo_2bis'.
    """
    match = re.search(r"exercice\s+([a-z0-9]+)", title, re.IGNORECASE)
    return f"exo_{match.group(1).lower()}" if match else None

def retirer_premiere_ligne_si_titre(enonce: str) -> str:
    """
    Supprime la première ligne de l'énoncé si elle commence par 'EXERCICE',
    afin d'éviter la redondance dans le PDF (déjà dans \section).
    """
    lines = enonce.strip().splitlines()
    if lines:
        first = lines[0].strip().lower()
        if first.startswith("exercice") or first.startswith("🧩 exercice"):
            return "\n".join(lines[1:]).strip()
    return enonce.strip()




def build_conversation_pdf(engine):
    """
    Génère un PDF de la conversation pédagogique, organisé par exercice.
    """
    

    history = session.get("cconv", [])
    if not history:
        app.logger.warning("PDF : aucun historique dans cconv.")
        return None

    # Informations de contexte
    matiere = session.get("active_matiere", "").capitalize()
    scenario_id = session.get("active_scenario_id")
    scenario_name = "Scénario en cours"

    # Récupération du nom de la fiche
    with engine.connect() as cn:
        scenario_name = cn.scalar(text("""
            SELECT name FROM scenarios WHERE id = :sid
        """), {"sid": scenario_id}) or scenario_name

    # Tri des messages par bloc d'exercice
    sections = decouper_conversation_par_exercice(history)


    # Construction du LaTeX
    tex = r"""
    \documentclass{article}
    \usepackage[utf8]{inputenc}
    \usepackage[T1]{fontenc}
    \usepackage[french]{babel}
    \usepackage{geometry}
    \usepackage{xcolor}
    \usepackage{listings}
    \usepackage{fancyvrb}
    \usepackage{amsmath}
    \usepackage{amssymb}
    \geometry{a4paper, margin=1in}
    \definecolor{lightgray}{gray}{0.95}
    \lstset{
        backgroundcolor=\color{lightgray},
        basicstyle=\ttfamily\small,
        breaklines=true,
        frame=single
    }
    \title{Conversation pédagogique}
    \date{}
    \begin{document}
    """  # C'est une raw-string, donc OK pour le préambule

    tex += f"""
    \\maketitle

    \\textbf{{Matière}} : {sanitize_tex(matiere)}\\\\
    \\textbf{{Nom de la fiche}} : {sanitize_tex(scenario_name)}

    \\bigskip
    """

    meta_seen = False
    
    for section, messages in sections.items():
        titre = sanitize_tex_preserving_math(normaliser_titre_exo(section))
        tex += f"\\section*{{{titre}}}\n\n"

        # Injection automatique de l'énoncé si section = "Exercice X"
        ref = extract_ref_from_section_title(section)
        if ref and ref in session.get("MAP_JSON", {}): # si cest un exo de la fiche
            enonce = session["MAP_JSON"][ref].strip()
            enonce = retirer_premiere_ligne_si_titre(enonce)
            tex += format_content_latex(enonce) + "\n\n"


        for role, subtype, content in messages:
            if role == "meta":
                role_title = {
                    "intro": "Note d’introduction",
                    "feedback": "Bilan final"
                }.get(subtype, "Note système")
            else:
                role_title = {
                    "user": "Élève",
                    "assistant": "Assistant IA"
                }.get(role, role.capitalize())

            # 🔍 Supprime le titre d’exercice dans la réponse assistant s’il est redondant
            if role == "assistant":
                lines = content.strip().splitlines()
                if lines and lines[0].strip().lower().startswith("🧩 exercice"):
                    content = "\n".join(lines[1:]).strip()
            
            
            tex += f"\\subsection*{{{role_title}}}\n"
            
            tex += format_content_latex(content) + "\n\n"

    tex += r"\end{document}"



    # Compilation LaTeX
    tmpdirname = tempfile.mkdtemp()
    try:
        tex_path = os.path.join(tmpdirname, "conversation.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            safe_tex = normalize_quotes(tex)
            f.write(safe_tex)

        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "conversation.tex"],
            cwd=tmpdirname,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        app.logger.info(f"PDF généré avec succès : {result.stdout}")

        pdf_path = os.path.join(tmpdirname, "conversation.pdf")
        return pdf_path

    except subprocess.CalledProcessError as e:
        app.logger.error("❌ Erreur compilation pdflatex :")
        app.logger.error(e.stdout)
        app.logger.error(e.stderr)
        return None
    except Exception as e:
        app.logger.error(f"Erreur inattendue : {e}")
        return None


    finally:
        try:
            clean_temp_folder()
        except Exception as e:
            app.logger.warning(f"Erreur nettoyage : {e}")


