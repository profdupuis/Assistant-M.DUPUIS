# Standard libraries
import os
import re
import json
import time
import shutil
import pathlib
import hashlib
import csv
from datetime import timedelta , datetime, timezone
from io import StringIO, BytesIO
import smtplib
from email.mime.text import MIMEText
from zipfile import ZipFile, ZIP_DEFLATED
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from collections import defaultdict

# Flask
from flask import (
    Flask, render_template, request, redirect, send_from_directory,
    Response, url_for, jsonify, session, abort, flash, send_file 
)
 
from flask_session import Session
from markupsafe import Markup

# SQLAlchemy
from sqlalchemy import create_engine, text, bindparam
from sqlalchemy.exc import NoResultFound

# App-specific modules
from config import DevelopmentConfig, ProductionConfig
from utils.llm import (
    moderation_par_llm,
    feedback_final,
    correction_et_explication,
    should_summarize,
    summarize_history
)
from utils.session_utils import (
    extract_niveau,
    clean_prompt,
    has_feedback,
    load_json_from_db,
    load_done_refs,
    init_session_context,
    clean_temp_folder,
    latest_scenarios_without_feedback_matiere
)


from rgpd import (
    clean_export_folder, verifier_integrite_worm, init_export_directories, handle_consent,
    delete_student, download_latest_worm, download_worm, export_flags_graves,archive_and_purge,
    export_worm, purge_old_logs, prepare_audit, PURGE_DAYS, export_logs_eleve_csv
)

from aut import (
    login_required_admin,
    login_required
)



    
# ─────────── init ────────────────────────────────────────────────────



app = Flask(__name__)

if os.getenv("FLASK_ENV") == "production":
    app.config.from_object(ProductionConfig)
else:
    app.config.from_object(DevelopmentConfig)


Session(app)

engine = create_engine(app.config["DATABASE_URL"], future=True, pool_pre_ping=True)
engine_log = create_engine(app.config["DATABASE_URL_LOG"], future=True, pool_pre_ping=True) # 🔒 moteur dédié au logging (app_log)
engine_rgpd = create_engine(app.config["DATABASE_URL_RGPD"], future=True, pool_pre_ping=True) # 🔐 moteur dédié aux exports RGPD et vérifications WORM (lecture seule, utilisateur rgpd_bot)




def is_pdflatex_available() -> bool:
    """
    Vérifie si pdflatex est disponible sur le serveur.
    """
    return shutil.which("pdflatex") is not None


app.jinja_env.globals.update(is_pdflatex_available=is_pdflatex_available)


# ─────────── helpers DB ──────────────────────────────────────────────


def exo_row(conn, ordinal: int):
    scenario_id = session["active_scenario_id"]
    row = conn.execute(text("""
        SELECT exercise_id
        FROM exercises
        JOIN exercise_sets es ON es.set_id = exercises.set_id
        WHERE es.scenario_id = :scid AND ordinal = :o
    """), {"scid": scenario_id, "o": ordinal}).mappings().first()
    if not row:
        raise NoResultFound
    return row

# ─────────── WPA ──────────────────────────────────────────────────
@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/apple-touch-icon.png')
def apple_touch_icon():
    return send_from_directory('static/img', 'icon_ios_180.png')

@app.route('/login')
def login_redirect():
    return redirect(url_for('login'))


# ─────────── login ──────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def login():
    session.clear()
    err = None
    consent_pending = False  # Par défaut
    if request.method == "POST":
        sid = request.form.get("id", "").strip().upper()
        consent_given = request.form.get("consent")  # Vérifier si la case de consentement est cochée
        
        if sid:
            with engine.connect() as cn:
                # Vérifier si l'identifiant existe dans la base
                ok = cn.scalar(text(
                    "SELECT 1 FROM students WHERE student_id=:sid"), {"sid": sid})
            
            if ok:
                # Si l'identifiant est correct, vérifier si le consentement RGPD est déjà donné
                with engine.connect() as cn:
                    consent_date = cn.scalar(text("""
                        SELECT rgpd_consent_date FROM students WHERE student_id = :sid
                    """), {"sid": sid})
                
                if consent_date:
                    # Si le consentement RGPD a déjà été donné, on passe à l'interface IA
                    session.clear()
                    session["student_id"] = sid
                    init_session_context(engine,sid)
                    return redirect(url_for("interface_ia"))
                else:
                    # Sinon, on garde l'identifiant dans la session et on affiche la modale RGPD
                    session["student_id"] = sid  # On conserve l'identifiant dans la session
                    consent_pending = True
                
            else:
                app.logger.warning(f"Tentative de connexion échouée pour l'identifiant : {sid}")
                err = "Identifiant inconnu"
        else:
            err = "Identifiant manquant"
    
    # Toujours retourner login.html en précisant si consent_pending ou non
    return render_template("login.html", error=err, consent_pending=consent_pending)

# ─────────── consentement rgpd ──────────────────────────────────────────
@app.route("/handle_consent", methods=["POST"])
def handle_consent_route():
    """
    Gère l'acceptation du consentement RGPD par l'élève lors de la connexion.
    """
    return handle_consent(engine)



def get_next_exercise_ref(map_json: dict, done_refs: list[str]) -> str:
    """
    Renvoie l'ID du prochain exercice à faire (ex: 'exo_2')
    ou le premier de la fiche si tous sont faits.
    """
    all_refs = sorted(map_json.keys(), key=lambda r: int(r.split("_")[1]))
    pending = [ref for ref in all_refs if ref not in done_refs]
    return pending[0] if pending else all_refs[0]




    
# ─────────── page IA (intro + exo 1) ────────────────────────────────
@app.route("/ia")
@login_required
def interface_ia():
    student_id = session["student_id"]
    class_name = student_id.split("-")[0]
    scenario_id=session["active_scenario_id"]

        
    if "MAP_JSON" not in session:
        map_json, ans_json, cat_json = load_json_from_db(engine,class_name,scenario_id)
        session["MAP_JSON"] = map_json
        session["ANS_JSON"] = ans_json
        session["CAT_JSON"] = cat_json

    MAP_JSON = session["MAP_JSON"]
    ANS_JSON = session["ANS_JSON"]
    CAT_JSON = session["CAT_JSON"]




    with engine.connect() as cn:
        # 1. Récupérer le scénario actif de l'eleve
        scenario_id = session["active_scenario_id"]
        row = cn.execute(text("""
            SELECT name, matiere, content
            FROM scenarios
            WHERE class_name = :cls AND id = :scid
            LIMIT 1
        """), {"cls": class_name, "scid": scenario_id}).mappings().first()

        if not row:
            return "❌ Aucun scénario actif pour cette classe."

        content = row["content"]
        scenario_nom = row["name"]
        scenario_matiere = row["matiere"]

        # 2. Extraire l’intro élève

        match = re.search(r"⏱️ DEBUT_PROMPT_ELEVE(.*?)⏹️ FIN_PROMPT_ELEVE", content, flags=re.DOTALL)
        intro = match.group(1).strip() if match else "👋 Bienvenue !"

        # 3. Récupérer l'exercice 1
        exo = cn.execute(text("""
            SELECT exercise_id, prompt
            FROM exercises e
            JOIN exercise_sets s ON s.set_id = e.set_id
            WHERE s.is_active = true AND e.ordinal = 1
            LIMIT 1
        """)).mappings().first()

        if not exo:
            return "❌ Aucun exercice trouvé."

    # déterminer le prochain exercice à faire
    next_ref = get_next_exercise_ref(MAP_JSON, session["exo_valide"])
    exo_num = int(next_ref.split("_")[1])

    with engine.connect() as cn:
        exo = exo_row(cn, exo_num)

    session.update(
        exo_courant = exo_num,
        exo_id      = exo["exercise_id"],
        start       = time.time()
    )
    
    # enregistrement en conv
    session["cconv"].append({
        "role": "exo",
        "content": f"Exercice {session['exo_courant']}"
    })
    
    next_ref = get_next_exercise_ref(MAP_JSON, session["exo_valide"])
    exo_num = int(next_ref.split("_")[1])

    all_refs = sorted(MAP_JSON.keys(), key=lambda r: int(r.split("_")[1]))
    done_refs = session["exo_valide"]

    if len(done_refs) == len(all_refs):
        if session["has_feedback"]:
            session["exo_valide"]=[]
        reprise_msg = "🎉 Tu as déjà terminé tous les exercices de cette fiche. Tu peux les refaire si tu veux t'entraîner."
    elif len(done_refs) == 0:
        reprise_msg = "Voici ton premier exercice de la fiche."
    else:
        reprise_msg = "🔁 On reprend là où tu t’étais arrêté. Voici l’exercice suivant :"


    texte = f"{intro}\n\n{reprise_msg}\n\n{MAP_JSON[next_ref]}".strip()
    html = Markup("<br>".join(texte.splitlines()))

    last_scenarios = latest_scenarios_without_feedback_matiere(
        engine,
        class_name=session["student_id"].split("-")[0],
        student_id=session["student_id"]
    )

    active_scenario_id = session.get("active_scenario_id")
    
    return render_template(
        "ia_interface.html",
        initial_message=html,
        initial_message_text=texte,  # ← ✅ texte brut non transformé
        scenario_nom=scenario_nom,
        scenario_matiere=scenario_matiere,
        fiche_terminee=session.get("has_feedback", False),  # ✅ ICI
        last_scenarios=last_scenarios,  # ✅ ici !
        active_scenario_id=active_scenario_id
    )

# ─────────── scénario complet envoyé à GPT ──────────────────────────
def scenario_prompt() -> str:
    student_id = session.get("student_id", "")
    class_name = student_id.split("-")[0]
    with engine.connect() as cn:
        scenario_id = session["active_scenario_id"]
        row = cn.execute(text("""
            SELECT content
            FROM scenarios
            WHERE class_name = :cls AND id = :scid
            LIMIT 1
        """), {"cls": class_name, "scid": scenario_id}).mappings().first()

    if not row:
        return "❌ Aucun scénario actif trouvé pour cette classe."
    content = row["content"]
    return content

# ─────────── Sauvegarde des exercices faits ──────────────────────────
def update_done_refs(student_id: str, exo_ref: str):
    """
    Ajoute un exercice validé à la table done_refs pour un élève donné.
    """
    class_name = student_id.split("-")[0]
    with engine.begin() as cn:
        scenario_id = session["active_scenario_id"]

        row = cn.execute(text("""
            SELECT refs FROM done_refs
            WHERE student_id = :sid AND scenario_id = :scid
            LIMIT 1
        """), {"sid": student_id, "scid": scenario_id}).mappings().first()

        if row:
            if exo_ref not in row["refs"]:
                new_refs = row["refs"] + [exo_ref]
                cn.execute(text("""
                    UPDATE done_refs SET refs = :r WHERE student_id = :sid AND scenario_id = :scid
                """), {"r": json.dumps(new_refs), "sid": student_id, "scid": scenario_id})
        else:
            cn.execute(text("""
                INSERT INTO done_refs(student_id, scenario_id, refs)
                VALUES (:sid, :scid, :r)
            """), {"sid": student_id, "scid": scenario_id, "r": json.dumps([exo_ref])})

def generate_feedback():
    """
    Génère un feedback final basé sur les exercices de l'élève et les compétences travaillées.
    """
    # Ajoute un message dans l'historique pour guider l'IA dans la génération du feedback
    session["history"].append({
        "role": "system",
        "content": (
            "Tu dois maintenant féliciter l'élève d'avoir terminé tous les exercices, "
            "et encore plus le féliciter s’il a réussi après des erreurs et qu’il s’est accroché. "
            "Résume en 2-3 phrases les compétences travaillées dans la fiche. "
            "Reste bref, positif, et ne répète pas toutes les réponses."
        )
    })

    # Appel à l'API pour générer le feedback final
    feedback = feedback_final(session["history"], user_id=session["student_id"])

    # Marquer que l'élève a reçu un feedback
    session["has_feedback"] = True

    # Sauvegarder le feedback dans la base de données
    with engine.begin() as cn:
        class_name = session["student_id"].split("-")[0]
        scenario_id = session["active_scenario_id"]

        cn.execute(text("""
            INSERT INTO feedbacks(student_id, scenario_id, feedback)
            VALUES (:sid, :scid, :fb)
        """), {
            "sid": session["student_id"],
            "scid": scenario_id,
            "fb": feedback
        })

    # Ajouter le feedback généré à l'historique pour qu'il soit envoyé à l'élève
    session["history"].append({"role": "assistant", "content": feedback})
    
    # Remettre l'exercice courant à -1 pour indiquer que tous les exercices sont terminés
    session["exo_courant"] = -1

    return feedback




# ─────────── Enregistrement des logs  ───────────────────────────────────────



def save_log(user_id, prompt, completion, flags, model, prev_hash):
    """
    Sauvegarde un échange élève → IA dans chat_logs.
    Utilise le dernier hash connu pour assurer le chaînage WORM RGPD.
    Met à jour students.last_this_hash et session["last_this_hash"].
    """
    # chaînage hash global
    now = datetime.now(timezone.utc)
    prev_hash = session.get("last_this_hash") or "0" * 64

    raw = f"{now.isoformat()}{user_id}{prompt}{completion}{json.dumps(flags)}{model}{prev_hash}"
    this_hash = hashlib.sha256(raw.encode()).hexdigest()

    with engine_log.begin() as cn:
        cn.execute(text("""
            INSERT INTO chat_logs(user_id,prompt,completion,flags,model,prev_hash,this_hash)
            VALUES (:u,:p,:c,(:f)::jsonb,:m,:ph,:th)
        """), {
            "u": user_id,
            "p": prompt,
            "c": completion,
            "f": json.dumps(flags),
            "m": model,
            "ph": prev_hash or "",
            "th": this_hash
        })
    # Mettre à jour last_this_hash dans students
    with engine.begin() as cn:
        cn.execute(text("""
            UPDATE students
            SET last_this_hash = :th
            WHERE student_id = :sid
        """), {"th": this_hash, "sid": user_id})

    # Mettre à jour aussi la session
    session["last_this_hash"] = this_hash
    return this_hash

# ─────────── Moderation des logs  ───────────────────────────────────────



def moderate_API(conversation: str) -> dict:
    """
    Appelle l'API OpenAI pour modérer la conversation et renvoyer un dict des flags.
    """
    try:
        return moderation_par_llm(conversation)  # Conversion en dict des catégories
    except Exception as e:
        app.logger.error(f"Modération échouée pour la conversation : {e}")
        return {"error": True}


def send_mod_alert_via_email(content: str):
    """
    Envoie un email d'alerte lorsqu'un contenu est modéré pour des raisons de sécurité RGPD.
    """
    # Paramètres de l'email
    msg = MIMEText(f"Contenu modéré pour raisons RGPD : {content}")
    msg["Subject"] = "Alerte RGPD - Contenu Modéré"
    msg["From"] = "no-reply@tonsite.com"
    msg["To"] = "sdupuis.prof@gmail.com"  # Email de l'administrateur

    # Connexion au serveur SMTP
    with smtplib.SMTP("smtp.tonsite.com") as server:
        server.sendmail(msg["From"], [msg["To"]], msg.as_string())
        app.logger.warning(f"Alerte envoyée : Contenu modéré, message : {content[:50]}...")

def moderation(user_msg, reply: str) -> dict:
    """
    Appelle l’endpoint OpenAI Moderation, sauvegarde des logs et renvoie un boolean
    indiquant si la conversation doit être bloquée.
    """
    return {"blocked": False}  # Contenu autorisé (pas de moderation en test)
    full_conversation = user_msg+reply
    flags = moderate_API(full_conversation)
    # Vérification de l'erreur d'API
    if flags.get("error"):
        app.logger.warning(f"Erreur lors de la modération pour l'élève {session.get('student_id')}")
        return flags # ✅ retour cohérent  # Bloquer si l'API échoue

    # Vérification des flags de modération
    blocked = any(flag for key, flag in flags.items() if key != "error" and flag is True)

    if blocked:
        prev_hash = session.get("last_hash", None)
        session["last_hash"] = save_log(
            session["student_id"],
            user_msg,
            completion=reply, 
            flags=flags,
            model="moderation-latest",
            prev_hash=prev_hash
        )

        # Envoi de l'alerte par email
        # send_mod_alert_via_email(f"Message élève : {user_msg}\nRéponse IA : {reply}")

        app.logger.warning(f"Conversation bloquée pour l'élève {session.get('student_id')}: {flags}")

        return {"blocked": True, "reason": flags} # Bloquer la conversation si un flag est présent
    return {"blocked": False}  # Contenu autorisé

    
@app.route('/api/report', methods=['POST'])
@login_required
def api_report():
    """report en clic sur l'app de discussion"""
    data = request.get_json()
    message_id = data.get('message_id')
    # pour l'instant on se contente d'un print
    print(f"[FLAG] signalement reçu pour message id = {message_id}")
    return ('', 204)




# ─────────── API conversation ───────────────────────────────────────
@app.route("/api/message", methods=["POST"])
@login_required
def api_message():
    user_msg = request.json.get("message", "")

    # enregistrement en discussion 
    session["cconv"].append({
        "role": "user",
        "content": user_msg.strip()
    })
    
    scenario_id = session["active_scenario_id"]
    if "MAP_JSON" not in session:
        student_id = session["student_id"]
        class_name = student_id.split("-")[0]
        map_json, ans_json, cat_json = load_json_from_db(class_name)
        session["MAP_JSON"] = map_json
        session["ANS_JSON"] = ans_json
        session["CAT_JSON"] = cat_json

    MAP_JSON = session["MAP_JSON"]
    ANS_JSON = session["ANS_JSON"]
    CAT_JSON = session["CAT_JSON"]
    # 1ʳᵉ requête
    if session.get("history") and session.get("history_scenario") != session["active_scenario_id"]:
        session.pop("history", None)

    if "history" not in session:
        session["cconv"] = []
        session["history"] = [
            {"role": "system", "content": scenario_prompt()}
        ]
        session["history_scenario"] = session["active_scenario_id"]
        
    # 🔁 Résumer si nécessaire
    if should_summarize(session["history"]):
        try:
            summary = summarize_history(session["history"])
            session["history"] = [
                {"role": "system", "content": scenario_prompt()},
                {"role": "assistant", "content": summary}
            ]
            app.logger.info("✅ Historique résumé pour éviter surcharge.")
            print(summary)
        except Exception as e:
            app.logger.warning(f"❌ Échec résumé conversation : {e}")

    nav_enonce = ""        # ← défaut pour éviter UnboundLocalError

    # ── navigation « exercice N »  ##################################  PATCH
    # accepte : « ex2 », « ex 2 », « exercice 2 », «   EXERCICE  12  », « exo2 », « exo 2 »,
    nav = re.fullmatch(r'\s*ex(?:o|ercice)?\s*(\d+)\s*', user_msg, re.I)
    if nav:
        session["exo_courant"] = int(nav.group(1))

        try:
            with engine.connect() as cn:
                exo = exo_row(cn, session["exo_courant"])
            session.update(exo_id=exo["exercise_id"], start=time.time())
        except NoResultFound:
            return jsonify({"reply": "⚠️ Cet exercice n'existe pas dans cette fiche. Merci de vérifier le numéro."})


        next_ref   = f"exo_{session['exo_courant']}"
        nav_enonce = "\n\n---\n" + MAP_JSON.get(next_ref,
                                               "_Énoncé introuvable_")
        #   juste l’énoncé, pas de GPT
        ref   = f"exo_{session['exo_courant']}"
        texte = MAP_JSON.get(ref, "_Énoncé introuvable_")
        
        # **MAJ conversastion et  l'historique**
        
        
        session["history"].append({"role":"user", 
                                   "content": user_msg})
        
        session["history"].append({"role":"assistant", 
                                   "content": f"⏩ On passe à l’exercice {session['exo_courant']} :\n\n{texte}"})
        session["cconv"].append({
            "role": "exo",
            "content": f"Exercice {session['exo_courant']} :\n\n{texte}"
        })   

        return jsonify({"reply": f"⏩  On passe à l’exercice {session['exo_courant']} :\n\n{texte}"})

    # -----------------------------------------------------------------

    ## ICI ON MODERE USER_MSG avant requete
    moderation_result=moderation(user_msg,"")
    if moderation_result.get("error"):
        return jsonify({"reply": "🚫 Impossible d’analyser le message (modération indisponible)."})

    elif moderation_result.get("blocked"):
        return jsonify({"reply": "Conversation modérée. Veuillez reformuler."})
    
    
    # temps écoulé
    elapsed = int(time.time() - session.get("start", time.time()))
    info    = f"[INFO] exo_courant={session['exo_courant']}; elapsed_s={elapsed}"
    
    session["cconv"].append({
        "role": "exo",
        "content": f"Exercice {session['exo_courant']}"
    })  

    session["history"].append({"role": "user", "content": info})
    session["history"].append({"role": "user", "content": user_msg})
    
    
    # Categorie
    current_ref = f"exo_{session['exo_courant']}"
    current_cat = CAT_JSON.get(current_ref, "Sans catégorie")
    session["history"].append({"role": "system","content": f"# Catégorie de l'exercice : {current_cat}"})

    # Ajouter la liste des exercices non encore faits
    all_refs = sorted(MAP_JSON.keys(), key=lambda x: int(x.split("_")[1]))
    done_refs = session.get("exo_valide", [])
    pending_refs = [ref for ref in all_refs if ref not in done_refs]

    if pending_refs:
        exo_nums = [ref.split("_")[1] for ref in pending_refs]
        msg = (
            f"⚠️ Attention : l’élève n’a pas encore terminé la fiche. "
            f"Il reste à faire les exercices : {', '.join(exo_nums)}. "
            f"Adapte ta réponse pour l’encourager à les compléter, "
            f"et évite de dire que tout est fini."
        )
        session["history"].append({"role": "system", "content": msg})
    else:
        session["history"].append({
            "role": "system",
            "content": (
                "✅ L’élève a terminé tous les exercices de la fiche. "
                "Tu peux lui proposer d'utiliser la fonctionnalité proposant des exercices similaires ou l'encourager à consulter une autre activité."
            )
        })    # test mode libre

    # appel LLM
    reply = correction_et_explication(session["history"], user_id=session["student_id"])
    session["history"].append({"role": "assistant", "content": reply})
    session["cconv"].append({"role": "assistant", "content": reply})
    
    ## ICI ON MODERE USER_MSG+REPLY
    moderation_result=moderation(user_msg,reply)
    if moderation_result.get("error"):
        return jsonify({"reply": "🚫 Impossible d’analyser le message (modération indisponible)."})

    elif moderation_result.get("blocked"):
        return jsonify({"reply": "Conversation modérée. Veuillez reformuler."})
    
    # 3) Et on enregistre la réponse GPT en log meme si non flag
    prev_hash = session.get("last_hash")
    session["last_hash"] = save_log(
        session["student_id"],
        user_msg,
        completion=reply,
        flags={},  # aucun flag levé ici normalement
        model="gpt-4.1",
        prev_hash=prev_hash
    )
    
    # tentative (ne compte pas la simple navigation)
    if not nav:
        
        # ✅ On considère l'exercice terminé uniquement si la phrase attendue apparaît
        is_finished = "EXERCICE TERMINE : ✅" in reply.upper()

        # ✅ On détecte au moins un succès partiel pour is_correct
        is_ok = "✅" in reply and "❌" not in reply
        # ou peut etre plutot si on veut pas compter les aides is_ok = "✅" in reply re "❌" not in reply

        # 🔁 Enregistrement dans attempts, même si partiel
        with engine.begin() as cn:
            cn.execute(text("""
                INSERT INTO attempts(student_id,exercise_id,started_at,ended_at,
                                     elapsed_s,given_answer,is_correct)
                VALUES (:sid,:eid,to_timestamp(:s),now(),:e,:ans,:ok)
            """), {"sid": session["student_id"], "eid": session["exo_id"],
                   "s": session.get("start", time.time()), "e": elapsed,
                   "ans": user_msg[:500], "ok": is_ok})
            
        # ✅ Si le message de fin apparaît → on valide l'exercice
        if is_finished:
            ref = f"exo_{session['exo_courant']}"
            if ref not in session.get("exo_valide", []):
                session.setdefault("exo_valide", []).append(ref)

            
            ####################### enregistrement done ref en bdd ##############################
            update_done_refs(session["student_id"], ref)

            step = 1  # ou 2 si on veut sauter selon le temps
            
            # Liste des exos restants
            done_refs = session.get("exo_valide", [])
            pending_refs = [ref for ref in all_refs if ref not in done_refs]
            

            if pending_refs == [] and not session.get("has_feedback"):
                # 🎉 Tous les exos faits → générer feedback
                
                
                feedback=generate_feedback()
                session["cconv"].append({"role": "assistant", "content": feedback})
                
                ############# oubli moderation ici a ajouter et a mettre dans logs ###############
                
                
                nav_enonce = ""
                reply += "\n\n📘 " + feedback
                return jsonify({"reply": reply })
            else:
                # 🔁 Avancer vers le prochain exo non fait après le courant, ou revenir au premier non fait
                prochain = None
                exo_actuel = session["exo_courant"]

                for ref in pending_refs:
                    n = int(ref.split("_")[1])
                    if n > exo_actuel:
                        prochain = ref
                        break
                badge = "⏩" if prochain else "↩️"
                    
                    
                # Si aucun exo non fait après l’actuel, on reprend au début
                if not prochain and pending_refs:
                    prochain = pending_refs[0]

                if prochain:
                    session["exo_courant"] = int(prochain.split("_")[1])
                    session["start"] = time.time()
                    with engine.connect() as cn:
                        exo = exo_row(cn, session["exo_courant"])
                    session["exo_id"] = exo["exercise_id"]
                    
                    # enregistrement en conv
                    session["cconv"].append({
                        "role": "exo",
                        "content": f"Exercice {session['exo_courant']}"
                    })                      

                    reply += f"\n\n{badge} On continue avec l’exercice {session['exo_courant']} :\n\n"

                    reply += MAP_JSON[prochain]

    # renvoi : réponse GPT + éventuel énoncé demandé
    return jsonify({"reply": reply + nav_enonce})



# ─────────── reset session ─────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))




@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    err = None
    if request.method == "POST":
        login = request.form.get("login", "").strip()
        password = request.form.get("password", "").strip()
        if login == "admin" and password == os.getenv("ADMIN_PASSWORD", "admin123"):
            session["is_admin"] = True
            return redirect(url_for("dashboard"))
        err = "Identifiants invalides"
    return render_template("admin_login.html", error=err)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))



# ─────────── Analise evolution ─────────────────────────────────────────

# non utilisé ................
def get_statistiques_scenario(student_id, scenario_id):
    """
    Retourne le nombre de bonnes réponses et le total de tentatives
    pour un élève donné et un scénario donné.
    
    - student_id : identifiant de l'élève
    - scenario_id : identifiant du scénario

    Retour : dictionnaire {"nb_bonnes": int, "nb_total": int}
             ou None si aucune tentative
    """
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT
              COUNT(*) FILTER (WHERE a.is_correct) AS nb_bonnes,
              COUNT(*) AS nb_total
            FROM attempts a
            JOIN exercises e      ON e.exercise_id = a.exercise_id
            JOIN exercise_sets es ON es.set_id = e.set_id
            WHERE a.student_id = :sid AND es.scenario_id = :scid
        """), {"sid": student_id, "scid": scenario_id}).first()

    if result and result.nb_total > 0:
        return {"nb_bonnes": result.nb_bonnes or 0, "nb_total": result.nb_total}
    else:
        return None
#############################################


def get_evolution_par_scenario(classe=None, student_id=None):
    where = []
    params = {}

    if classe:
        where.append("sc.class_name = :classe")
        params["classe"] = classe
    if student_id:
        where.append("a.student_id = :sid")
        params["sid"] = student_id

    filter_clause = "WHERE " + " AND ".join(where) if where else ""

    sql = text(f"""
        SELECT
          sc.id AS scenario_id,
          sc.name AS scenario_title,
          COUNT(a.*) FILTER (WHERE a.is_correct) AS nb_bonnes,
          COUNT(a.*) AS nb_total,
          sc.created_at
        FROM scenarios sc
        JOIN exercise_sets es ON es.scenario_id = sc.id
        JOIN exercises e      ON e.set_id = es.set_id
        LEFT JOIN attempts a  ON a.exercise_id = e.exercise_id
        {filter_clause}
        GROUP BY sc.id, sc.name, sc.created_at
        ORDER BY sc.created_at
    """)

    with engine.connect() as cn:
        rows = cn.execute(sql, params).fetchall()

    return [
        {
            "scenario": r[1],
            "nb_bonnes": r[2],
            "nb_total": r[3],
            "pourcentage": round(100 * r[2] / r[3], 1) if r[3] > 0 else 0
        }
        for r in rows if r[3] > 0
    ]


def get_evolution_par_scenario2(student_id, matiere: str | None = None):
    sql = """
        SELECT sc.id,
               sc.name,
               COUNT(a.*)                         AS nb_total,
               COUNT(a.*) FILTER (WHERE a.is_correct) AS nb_ok
        FROM scenarios sc
        JOIN exercise_sets es ON es.scenario_id = sc.id
        JOIN exercises     ex ON ex.set_id      = es.set_id
        JOIN attempts       a ON a.exercise_id  = ex.exercise_id
        WHERE a.student_id = :stu
        {mat_filter}
        GROUP BY sc.id, sc.name, sc.created_at
        ORDER BY sc.created_at
    """
    params = {"stu": student_id}
    mat_filter = ""
    if matiere:
        mat_filter = "AND sc.matiere = :mat"
        params["mat"] = matiere

    with engine.connect() as cn:
        rows = cn.execute(
            text(sql.format(mat_filter=mat_filter)), params
        ).mappings().all()

    return [
        {"scenario": r["name"],          # ← ancienne clé
         "pourcentage": round(100 * r["nb_ok"] / r["nb_total"], 1)}
        for r in rows if r["nb_total"]
    ]


@app.route("/dashboard")
@login_required_admin
def dashboard():
    with engine.connect() as conn:
        all_classes = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT class FROM students ORDER BY class"
        ))]
        all_scenarios = conn.execute(text("""
            SELECT id, name, class_name, is_active
            FROM scenarios
            ORDER BY class_name, name
        """)).mappings().all()

    return render_template(
        "dashboard.html",
        all_classes=all_classes,
        all_scenarios=all_scenarios
    )

# ─────────── Gestion Scenarios  ─────────────────────────────────


@app.route("/dashboard/activate_scenario", methods=["POST"])
@login_required_admin
def activate_scenario():
    scenario_id = request.form.get("scenario_id", type=int)
    class_name = request.form.get("class_name", type=str)

    if not scenario_id or not class_name:
        abort(400)

    with engine.begin() as conn:
        # 🔹 Désactiver tous les scénarios de la classe
        conn.execute(text("""
            UPDATE scenarios
            SET is_active = FALSE
            WHERE class_name = :cls
        """), {"cls": class_name})

        # 🔥 Activer le scénario choisi
        conn.execute(text("""
            UPDATE scenarios
            SET is_active = TRUE
            WHERE id = :sid
        """), {"sid": scenario_id})

        # 🔹 Désactiver les séries de tous les autres scénarios de cette classe
        conn.execute(text("""
            UPDATE exercise_sets
            SET is_active = FALSE
            WHERE scenario_id IN (
                SELECT id FROM scenarios
                WHERE class_name = :cls AND id != :sid
            )
        """), {"cls": class_name, "sid": scenario_id})

        # 🔥 Activer uniquement les séries du scénario actif
        conn.execute(text("""
            UPDATE exercise_sets
            SET is_active = TRUE
            WHERE scenario_id = :sid
        """), {"sid": scenario_id})

    return redirect(url_for("dashboard"))




@app.route("/dashboard/delete_scenario", methods=["POST"])
@login_required_admin
def delete_scenario():
    """Supprime un scenario de la base de données"""
    scenario_id = request.form.get("scenario_id", type=int)
    if not scenario_id:
        abort(400)

    with engine.begin() as cn:
        # Étape 1 : Trouver les exercise_id liés au scénario
        exercise_ids = cn.execute(text("""
            SELECT e.exercise_id
            FROM exercises e
            JOIN exercise_sets es ON e.set_id = es.set_id
            WHERE es.scenario_id = :id
        """), {"id": scenario_id}).scalars().all()

        # Étape 2 : Supprimer les tentatives liées à ces exercices
        if exercise_ids:
            cn.execute(text("""
                DELETE FROM attempts
                WHERE exercise_id = ANY(:ids)
            """), {"ids": exercise_ids})

        # Étape 3 : Supprimer les exercices liés au scénario
        cn.execute(text("""
            DELETE FROM exercises
            USING exercise_sets es
            WHERE exercises.set_id = es.set_id AND es.scenario_id = :id
        """), {"id": scenario_id})

        # Étape 4 : Supprimer les sets d’exercices
        cn.execute(text("DELETE FROM exercise_sets WHERE scenario_id = :id"), {"id": scenario_id})

        # Étape 5 : Supprimer le scénario lui-même
        cn.execute(text("DELETE FROM scenarios WHERE id = :id"), {"id": scenario_id})

    return redirect(url_for("dashboard"))






def parse_filename_and_subject(filename: str, file_content: str):
    """
    Parse le nom du fichier et extrait :
    - Classe
    - Professeur
    - Nom de la fiche
    - Matière (depuis contenu)
    
    Le format du filename doit être : CLASSE-PROF-NOMFICHE.txt
    """
    filename = Path(filename).stem  # Enlève .txt
    parts = filename.split("-", 2)

    if len(parts) != 3:
        raise ValueError("Nom de fichier invalide. Format attendu : CLASSE-PROF-NOMFICHE.txt")

    class_name, nom_prof, nom_fiche = parts
    class_name = class_name.strip()
    nom_prof = nom_prof.strip()
    nom_fiche = nom_fiche.strip()

    # 🔥 Matière dans le contenu
    matiere_match = re.search(r"\*\*\s*Mati[eè]re\s*:\s*\*\*\s*(.+)", file_content, flags=re.I)
    if not matiere_match:
        raise ValueError("Matière non trouvée dans le fichier scénario.")

    matiere = matiere_match.group(1).strip()

    return class_name, nom_prof, nom_fiche, matiere

def extract_resume(txt: str) -> str:
    """
    Extrait automatiquement le résumé d’un fichier scénario texte.

    Le résumé est repéré par une ligne contenant :
        ** Résumé :** Texte du résumé

    Exemple :
        ** Résumé :** Fiche d'exercices sur les équations différentielles du premier ordre

    Paramètres :
        txt (str) : contenu brut du fichier texte (.txt) du scénario.

    Retour :
        str | None : le résumé extrait (sans les étoiles), ou None si non trouvé.
    """
    match = re.search(r"\*\*\s*Résumé\s*:\s*\*\*\s*(.+)", txt)
    return match.group(1).strip() if match else None


def parse_blocks(txt: str):
    """
    Découpe le texte du scénario en blocs d'exercices individuels,
    et extrait énoncé, réponse, niveau, catégorie, compétence.
    """
    raw = re.split(r'🧩\s*EXERCICE\s*\d+', txt, flags=re.I)[1:]
    for bloc in raw:
        diff_match = re.search(r'niveau\s*(\d+)', bloc, flags=re.I)
        diff = int(diff_match.group(1)) if diff_match else 1
        ans_m = re.search(r'\*\*Bonne réponse attendue\s*:\s*\*\*(.*)', bloc)
        ans = ans_m.group(1).strip() if ans_m else None
        cat_m = re.search(r'\*\*Catégorie\s*:\s*(.*)', bloc)
        cat = cat_m.group(1).strip().lstrip("* ").strip() if cat_m else "Autre"
        comp_m = re.search(r'\*\*Compétence\s*:\s*(.*)', bloc)
        comp = comp_m.group(1).strip().lstrip("* ").strip() if comp_m else None
        enonce = re.split(r'\*Fin de l’énoncé\*|\*Fin de l\'énoncé\*', bloc)[0].strip()
        enonce = '\n'.join(line for line in enonce.splitlines() if line.strip())
        yield enonce, ans, diff, cat, comp



@app.route("/dashboard/upload_scenario", methods=["POST"])
@login_required_admin
def upload_scenario():
    file = request.files.get("fichier")
    if not file or not (file.filename.endswith(".txt") and re.match(r'^[A-Za-z0-9_-]+-[A-Za-z0-9_-]+-[A-Za-z0-9_-]+\.txt$', file.filename)):
        return "❌ Nom ou extension de fichier invalide", 400

    path = pathlib.Path("scenarios") / file.filename
    file.save(path)

    full_txt = path.read_text(encoding="utf-8")
    
    resume = extract_resume(full_txt) # extraire le résumé

    # ✅ Utilisation de ta fonction pour extraire les éléments
    try:
        class_name, nom_prof, nom_fiche, matiere = parse_filename_and_subject(file.filename, full_txt)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("dashboard"))

    # ✅ Découper en blocs exercices
    try:
        blocks = list(parse_blocks(full_txt))
    except Exception as e:
        flash(f"❌ Erreur lors du découpage des exercices : {e}", "error")
        return redirect(url_for("dashboard"))

    with engine.begin() as cn:
        # ✅ Vérifier si le prof existe déjà
        prof_id = cn.scalar(text("""
            SELECT id FROM profs WHERE nom = :nom
        """), {"nom": nom_prof})

        if not prof_id:
            # ✅ Sinon créer
            prof_id = cn.scalar(text("""
                INSERT INTO profs (nom)
                VALUES (:nom)
                RETURNING id
            """), {"nom": nom_prof})


        # ✅ Créer scénario
        scenario_id = cn.scalar(text("""
            INSERT INTO scenarios (name, class_name, content, resume, is_active, matiere, prof_id)
            VALUES (:name, :cls, :content, :resume, true, :mat, :pid)
            RETURNING id
        """), {
            "name": nom_fiche,
            "cls": class_name,
            "content": full_txt,
            "resume": resume,
            "mat": matiere,
            "pid": prof_id
        })

        # ✅ Désactiver les anciens scénarios de cette classe
        cn.execute(text("""
            UPDATE scenarios SET is_active = false
            WHERE class_name = :cls AND id != :id
        """), {"cls": class_name, "id": scenario_id})
        
        # 🔥 DÉSACTIVER tous les exercise_sets de la classe (sauf celui du nouveau scénario)
        cn.execute(text("""
            UPDATE exercise_sets
            SET is_active = FALSE
            WHERE scenario_id IN (
                SELECT id FROM scenarios
                WHERE class_name = :cls
                  AND id != :sid
            )
        """), {"cls": class_name, "sid": scenario_id})

        # ✅ Créer série exercices
        set_id = cn.scalar(text("""
            INSERT INTO exercise_sets (title, start_date, is_active, scenario_id)
            VALUES (:title, :date, true, :sid)
            RETURNING set_id
        """), {
            "title": nom_fiche,
            "date": datetime.now(timezone.utc).date(),
            "sid": scenario_id
        })

        # ✅ Ajouter exercices
        for i, (enonce, ans, diff, cat, comp) in enumerate(blocks, 1):
            ref = f"exo_{i}"
            cat_id = cn.scalar(text("""
                INSERT INTO categories (name)
                VALUES (:cat)
                ON CONFLICT(name) DO UPDATE SET name = EXCLUDED.name
                RETURNING category_id
            """), {"cat": cat})

            cn.execute(text("""
                INSERT INTO exercises (set_id, ordinal, prompt, answer, difficulty, category_id, competence)
                VALUES (:sid, :ord, :prompt, :ans, :diff, :cat_id, :comp)
            """), {
                "sid": set_id,
                "ord": i,
                "prompt": ref + "\n" + enonce,
                "ans": ans,
                "diff": diff,
                "cat_id": cat_id,
                "comp": comp
            })

        # ✅ Mettre à jour profs.scenarios si besoin (on pourrait stocker les IDs dans un tableau plus tard si besoin)

    flash(f"✅ Scénario '{nom_fiche}' importé avec succès !", "success")
    return redirect(url_for("dashboard"))




@app.route("/dashboard/export", methods=["POST"])
@login_required_admin
def export_csv():
    classe = request.form.get("classe", "").strip()
    scenario = request.form.get("scenario", type=int)
    student_id = request.form.get("student_id", "").strip()

    if not classe or not scenario:
        return "❌ Classe ou scénario manquant", 400

    with engine.connect() as cn:
        # 1. Récupérer les données
        params = {"cls": classe, "scid": scenario}
        where = "st.class = :cls AND s.scenario_id = :scid"

        if student_id:
            where += " AND st.student_id = :sid"
            params["sid"] = student_id

        rows = cn.execute(text(f"""
            SELECT st.student_id, e.ordinal, a.is_correct, a.elapsed_s, a.ended_at
            FROM attempts a
            JOIN exercises e     ON e.exercise_id = a.exercise_id
            JOIN exercise_sets s ON s.set_id      = e.set_id
            JOIN students st     ON st.student_id = a.student_id
            WHERE {where}
            ORDER BY st.student_id, e.ordinal
        """), params).mappings().all()

    # 2. Générer CSV
    f = StringIO()
    writer = csv.writer(f)
    writer.writerow(["student_id", "exo", "correct", "temps(s)", "date"])

    for r in rows:
        writer.writerow([
            r["student_id"],
            r["ordinal"],
            int(r["is_correct"]),
            r["elapsed_s"],
            r["ended_at"].isoformat()
        ])

    filename = f"export_{classe}_scenario{scenario}"
    if student_id:
        filename += f"_{student_id}"
    filename += ".csv"

    return Response(
        f.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


                        

        


##########################  RGPD   ############################
@app.route("/dashboard/rgpd")
@login_required_admin
def dashboard_rgpd():
    """
    Route principale du tableau de bord RGPD administrateur.

    Fonctionnalités :
    - Vérifie que l'utilisateur est authentifié en tant qu'administrateur.
    - Nettoie automatiquement le dossier /export/ en supprimant les fichiers WORM (.zip) vieux de plus de 90 jours.
    - Récupère et affiche :
        - Liste des élèves inscrits et consentements RGPD
        - Historique des exports WORM récents
        - Historique des purges RGPD
        - Historique des incidents de modération graves (flags)
    - Détecte automatiquement :
        - Si une purge récente a eu lieu (moins de PURGE_DAYS)
        - Si des incidents critiques récents sont présents (ex: self-harm)
    - Affiche les alertes RGPD correspondantes (purge / flags graves) dans le dashboard.

    Sécurité :
    - Accessible uniquement aux utilisateurs connectés avec les droits administrateur (@login_required_admin).

    Retour :
    - Rend la page dashboard_rgpd.html avec toutes les données pré-remplies.
    """
    init_export_directories()
    clean_export_folder()  # 🔥 Nettoyage automatique au chargement
    
    # verification de la non rupture d'intégrité du chainage 
    if not verifier_integrite_worm(engine_rgpd):
        flash("⚠️ Nouveau Problème détecté dans l'intégrité WORM.", "error")
    selected_class = request.args.get("classe")

    with engine.connect() as cn:
        classes = cn.execute(text("SELECT DISTINCT class FROM students ORDER BY class")).scalars().all()

        if selected_class:
            students = cn.execute(text("""
                SELECT student_id, class, rgpd_consent_date
                FROM students
                WHERE class = :cls
                ORDER BY student_id
            """), {"cls": selected_class}).mappings().all()
        else:
            students = cn.execute(text("""
                SELECT student_id, class, rgpd_consent_date
                FROM students
                ORDER BY class, student_id
            """)).mappings().all()

        worm_history = cn.execute(text("""
            SELECT export_date, nb_logs, size_bytes, filename
            FROM worm_exports
            ORDER BY export_date DESC
            LIMIT 10
        """)).mappings().all()

        purge_history = cn.execute(text("""
            SELECT purge_date, nb_logs_deleted, nb_attempts_anonymized
            FROM logs_purges
            ORDER BY purge_date DESC
            LIMIT 10
        """)).mappings().all()

        last_purge = cn.execute(text("""
            SELECT purge_date
            FROM logs_purges
            ORDER BY purge_date DESC
            LIMIT 1
        """)).scalar()
        
        now = datetime.now(timezone.utc)
        purge_recent = last_purge and (now - last_purge) <= timedelta(days=PURGE_DAYS)
      
        flag_history = cn.execute(text("""
            SELECT id, ts, user_id, prompt, flags
            FROM chat_logs
            WHERE flags IS NOT NULL AND flags != '{}'::jsonb
            ORDER BY ts DESC
            LIMIT 20
        """)).mappings().all()
        
    # 🔥 Récupérer la date du dernier export flags graves
    last_flag_export = get_last_flag_export_time()

    # ✅ Déclencher l’alerte uniquement si un flag self-harm est plus récent
    flag_grave_detected = any(
        ('self-harm' in (record.flags or {}) or 'self-harm/intent' in (record.flags or {}))
        and (last_flag_export is None or record.ts > last_flag_export)
        for record in flag_history
    )
    return render_template("dashboard_rgpd.html",
                           students=students,
                           classes=classes,
                           selected_class=selected_class,
                           worm_history=worm_history,
                           purge_history=purge_history,
                           flag_history=flag_history,
                           last_purge=last_purge,
                           last_flag_export=last_flag_export,
                           purge_recent=purge_recent,
                           flag_grave_detected=flag_grave_detected,
                           purge_days=PURGE_DAYS)





def get_last_flag_export_time():
    """
    Analyse les fichiers d’export RGPD liés aux incidents critiques (flags graves)
    pour déterminer la date du dernier export effectué.

    Fonctionnement :
    - Cherche dans le dossier : export/audit_reports/moderations/
    - Repère le fichier le plus récent nommé :
        rapport_flags_graves_YYYY-MM-DD_HH-MM-SS.txt
    - Extrait et convertit cette date en datetime UTC

    Utilité :
    - Permet de savoir si de nouveaux incidents ont été détectés
      depuis le dernier export manuel par l’admin.
    - Sert à conditionner l’affichage de l’alerte 🚨 dans le dashboard RGPD.

    Retour :
    - datetime (UTC) de l’export le plus récent
    - ou None si aucun fichier trouvé ou erreur de parsing
    """
    folder = Path("export/audit_reports/moderations")
    if not folder.exists():
        return None
    reports = sorted(
        [f for f in folder.iterdir() if f.name.startswith("rapport_flags_graves_") and f.name.endswith(".txt")],
        reverse=True
    )
    if not reports:
        return None

    try:
        name = reports[0].stem  # ex: rapport_flags_graves_2025-04-30_17-41-22
        date_str = name.replace("rapport_flags_graves_", "")
        return datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S").replace(tzinfo=timezone.utc)
    except Exception as e:
        app.logger.warning(f"Erreur lecture date rapport flags : {e}")
        return None




@app.route("/dashboard/export_flags_graves", methods=["POST"])
@login_required_admin
def export_flags_graves_route():
    """
    Exporte les échanges détectés comme critiques (self-harm) en fichier CSV.

    - Sélectionne tous les logs de la table `chat_logs`
      où un problème de type `self-harm` ou `self-harm/intent` a été détecté.
    - Génère un fichier CSV avec les colonnes :
      Date de l'échange, Identifiant de l'élève, Prompt envoyé, Problèmes détectés.
    - Renvoie le fichier en téléchargement direct avec le nom `flags_graves.csv`.
    
    Sécurité :
    - Route protégée par @login_required_admin pour éviter tout accès non autorisé.

    Utilité :
    - Permet au responsable de la plateforme de conserver une trace
      des incidents critiques détectés pour audit ou suivi RGPD.
    """
    return export_flags_graves(engine_rgpd)








@app.route("/dashboard/prepare_audit", methods=["POST"])
@login_required_admin
def prepare_audit_route():
    """
    Génère et télécharge un pack complet d'audit RGPD sous forme d'un fichier ZIP.

    Contenu du pack :
    - Dernier fichier WORM exporté (chatlogs_worm_DATE.zip)
    - Fichier CSV listant tous les incidents critiques (self-harm) détectés
    - Fichier texte contenant la date de dernière purge RGPD et la date de génération du pack

    Fonctionnement :
    - Génère tout à la demande au moment du clic.
    - Crée l'archive ZIP en mémoire (pas de fichier temporaire sur le serveur).
    - Protégé par @login_required_admin pour sécuriser l'accès.
    - Le pack est envoyé immédiatement en téléchargement.

    Objectif :
    - Permettre un export complet et prêt à présenter pour audit RGPD ou inspection.

    Sécurité :
    - Aucun fichier persistant n'est stocké sur le serveur après téléchargement.
    - Toujours basé sur les données les plus récentes disponibles.

    Retour :
    - Fichier ZIP nommé 'audit_pack_YYYY-MM-DD_HHMM.zip'
    """
    return prepare_audit(engine)


@app.route("/dashboard/delete_student/<student_id>", methods=["POST"])
@login_required_admin
def delete_student_route(student_id):
    '''
    Supprime l'élève et ses données associées pour respect du RGPD.

    - Anonymise les logs liés dans chat_logs.
    - Supprime l'entrée correspondante dans students.

    Méthode protégée par la session admin.
    '''
    # 🛡️ RGPD x WORM : anonymisation au lieu de suppression des logs

    # Lors de la suppression d'un élève, nous ne supprimons pas ses anciens logs dans la table `chat_logs`.
    # Cela garantit le respect du principe WORM (Write Once, Read Many), qui interdit toute suppression ou altération
    # rétroactive de l’historique horodaté.

    # Conformément au RGPD, nous anonymisons le champ `user_id` en le remplaçant par la valeur 'ANONYMISED'.
    # Cette opération supprime toute possibilité d'identification directe ou indirecte de l'élève,
    # tout en préservant la continuité du chaînage cryptographique (prev_hash / this_hash).

    # Ce choix garantit :
    # - ✅ Conformité RGPD : aucune donnée personnelle identifiable n’est conservée
    # - ✅ Intégrité WORM : le contenu signé reste inchangé, donc le scellage SHA256 est préservé

    # Remarque :
    # - Aucun champ utilisé pour calculer les hash WORM n'est modifié (prompt, completion, flags, prev_hash, this_hash)
    # - Cette anonymisation est contrôlée par un trigger SQL : toute modification autre que `user_id` est bloquée


    delete_student(engine,engine_log, student_id)
    return redirect(url_for("dashboard_rgpd"))



@app.route("/dashboard/rgpd/upload", methods=["POST"])
@login_required_admin
def upload_students():
    '''
    Importe un fichier CSV pour ajouter de nouveaux élèves (identifiants anonymes) à la base de données.

    - Vérifie d'abord que l'utilisateur est connecté en tant qu'administrateur.
    - Valide que le fichier envoyé est bien un fichier CSV.
    - Parse le fichier et extrait les colonnes student_id et class.
    - Insère les élèves extraits dans la base de données sans écraser les existants.
    - Affiche un message de succès ou d'erreur selon le résultat.
    - Redirige ensuite vers le dashboard RGPD.

    Méthode protégée par la session admin.
    '''
    file = request.files.get("fichier")
    if not file or not file.filename.endswith(".csv"):
        flash("❌ Format de fichier invalide (seuls les .csv sont acceptés)", "error")
        return redirect(url_for("dashboard_rgpd"))

    rows = []
    try:
        file_content = file.read().decode("utf-8").splitlines()
        reader = csv.DictReader(file_content)
        for row in reader:
            if "student_id" in row and "class" in row:
                rows.append({"sid": row["student_id"], "cls": row["class"]})
    except Exception as e:
        app.logger.error(f"Erreur de parsing CSV : {e}")
        flash(f"❌ Erreur lors de la lecture du fichier : {e}", "error")
        return redirect(url_for("dashboard_rgpd"))

    try:
        with engine.begin() as cn:
            cn.execute(text("""
                INSERT INTO students (student_id, class, created_at)
                VALUES (:sid, :cls, now())
                ON CONFLICT (student_id) DO NOTHING
            """), rows)
        flash(f"✅ Importation réussie : {len(rows)} élèves traités.", "success")
    except Exception as e:
        flash(f"❌ Erreur lors de l'insertion en base : {e}", "error")

    return redirect(url_for("dashboard_rgpd"))



# ─────────── Export WORM ──────────────────────────────────────────────
@app.route("/dashboard/export_worm", methods=["POST"])
@login_required_admin
def export_worm_route():
    """
    Déclenche l'export des logs WORM des 7 derniers jours sous forme d'archive sécurisée (.zip).
    """
    return export_worm(engine_rgpd)


@app.route("/dashboard/rgpd/export_worm_purge", methods=["POST"])
@login_required_admin
def archive_and_purge_route():
    return archive_and_purge(engine_rgpd)

# ─────────── Download latest WORM ──────────────────────────────────────────────




@app.route("/dashboard/download_latest_worm")
@login_required_admin
def download_latest_worm_route():
    """
    Permet de télécharger le dernier fichier WORM généré (archive ZIP).

    - Vérifie que l'utilisateur est connecté en tant qu'administrateur.
    - Vérifie que le fichier ZIP existe et contient au moins un fichier valide.
    - Si le fichier est valide, le propose en téléchargement.
    - Sinon, affiche un message flash d'erreur approprié.
    - Redirige vers le dashboard RGPD en cas d'erreur.

    Méthode protégée par la session admin.
    """
    return download_latest_worm()

@app.route("/dashboard/download_worm/<filename>")
@login_required_admin
def download_worm_route(filename):
    """
    Permet de télécharger un fichier WORM historique spécifique.

    - Vérifie que l'utilisateur est connecté en tant qu'administrateur.
    - Cherche le fichier ZIP dans le dossier 'export/worm/'.
    - Si le fichier existe, l'envoie en téléchargement au client.
    - Si le fichier est introuvable, affiche un message flash d'erreur et redirige vers le dashboard RGPD.

    Cette route sécurise l'accès aux fichiers archivés WORM par leur nom unique.
    """
    return download_worm(filename)



# ─────────── Purge anciens logs ────────────────────────────────────────
@app.route("/dashboard/purge_old_logs", methods=["POST"])
@login_required_admin
def purge_old_logs_route():
    """
    Purge les anciennes données de la base de données.

    - Vérifie que l'utilisateur est connecté en tant qu'administrateur.
    - Supprime les logs de chat datant de plus de PURGE_DAYS jours.
    - Anonymise également les réponses des tentatives d'exercices vieilles de plus de PURGE_DAYS jours.
    - Affiche un message flash indiquant le nombre de suppressions/anonymisations effectuées.
    - Redirige ensuite vers le dashboard RGPD.

    Méthode protégée par la session admin.
    """
    return purge_old_logs(engine_log)






@app.route("/dashboard/eleve")
@login_required_admin
def dashboard_eleve():
    selected_class = request.args.get("classe")
    selected_scenario = request.args.get("scenario", type=int)
    student_id = request.args.get("student_id")

    with engine.connect() as cn:
        all_classes = cn.execute(text("SELECT DISTINCT class FROM students ORDER BY class")).scalars().all()

        scenarios = []
        students = []
        evolution = []
        hist = []
        feedback = None
        stats = []

        if selected_class:
            # Charger tous les scénarios de la classe
            scenarios = cn.execute(text("""
                SELECT id, name FROM scenarios
                WHERE class_name = :cls
                ORDER BY created_at DESC
            """), {"cls": selected_class}).mappings().all()

            # Charger tous les élèves de la classe
            students = cn.execute(text("""
                SELECT student_id FROM students
                WHERE class = :cls
                ORDER BY student_id
            """), {"cls": selected_class}).scalars().all()

            # Cas 1 : élève sélectionné → stats individuelles
            if student_id and selected_scenario:
                evolution = get_evolution_par_scenario(student_id=student_id)

                hist = cn.execute(text("""
                    SELECT
                      exercises.ordinal,
                      exercise_sets.title AS serie,
                      attempts.started_at,
                      attempts.ended_at,
                      attempts.elapsed_s,
                      attempts.given_answer,
                      attempts.is_correct
                    FROM attempts
                    JOIN exercises ON attempts.exercise_id = exercises.exercise_id
                    JOIN exercise_sets ON exercises.set_id = exercise_sets.set_id
                    WHERE attempts.student_id = :sid
                      AND exercise_sets.scenario_id = :scenario_id
                    ORDER BY attempts.started_at
                """), {"sid": student_id, "scenario_id": selected_scenario}).mappings().all()

                feedback = cn.execute(text("""
                    SELECT feedback FROM feedbacks
                    WHERE student_id = :sid
                      AND scenario_id = :scenario_id
                """), {"sid": student_id, "scenario_id": selected_scenario}).mappings().first()

                stats = cn.execute(text("""
                    SELECT
                      exercises.ordinal,
                      COUNT(attempts.attempt_id) AS tentatives,
                      AVG(CASE WHEN attempts.is_correct THEN 1 ELSE 0 END) * 100 AS taux_reussite,
                      AVG(attempts.elapsed_s) AS temps_moyen
                    FROM attempts
                    JOIN exercises ON attempts.exercise_id = exercises.exercise_id
                    JOIN exercise_sets ON exercises.set_id = exercise_sets.set_id
                    WHERE attempts.student_id = :sid
                      AND exercise_sets.scenario_id = :scenario_id
                    GROUP BY exercises.ordinal
                    ORDER BY exercises.ordinal
                """), {"sid": student_id, "scenario_id": selected_scenario}).mappings().all()

            # Cas 2 : aucun élève sélectionné → moyennes de la classe
            elif selected_scenario:
                evolution = get_evolution_par_scenario(classe=selected_class)

                stats = cn.execute(text("""
                    SELECT
                      exercises.ordinal,
                      COUNT(attempts.attempt_id) AS tentatives,
                      AVG(CASE WHEN attempts.is_correct THEN 1 ELSE 0 END) * 100 AS taux_reussite,
                      AVG(attempts.elapsed_s) AS temps_moyen
                    FROM attempts
                    JOIN exercises ON attempts.exercise_id = exercises.exercise_id
                    JOIN exercise_sets ON exercises.set_id = exercise_sets.set_id
                    JOIN students ON students.student_id = attempts.student_id
                    WHERE students.class = :cls
                      AND exercise_sets.scenario_id = :scenario_id
                    GROUP BY exercises.ordinal
                    ORDER BY exercises.ordinal
                """), {"cls": selected_class, "scenario_id": selected_scenario}).mappings().all()

    return render_template("dashboard_eleve.html",
                           all_classes=all_classes,
                           selected_class=selected_class,
                           selected_scenario=selected_scenario,
                           student_id=student_id,
                           scenarios=scenarios,
                           students=students,
                           evolution=evolution,
                           hist=hist,
                           feedback=feedback,
                           stats=stats)



@app.route("/dashboard/export_rapport", methods=["POST"])
@login_required_admin
def export_rapport():
    """
    Permet d'exporter un rapport global pour une classe et un scénario donnés.

    Fonctionnement :
    - Reçoit en POST :
      - `classe` : le nom de la classe à traiter
      - `scenario` : l'identifiant du scénario sélectionné
      - `action` : le type d'export souhaité ("txt", "tex", "pdf")
    - Selon la valeur d'action :
      - "txt" ➔ génère un rapport brut au format texte (.txt)
      - "tex" ➔ génère un rapport au format LaTeX (.tex)
      - "pdf" ➔ génère un rapport compilé directement en PDF (.pdf)
    - Redirige vers une erreur 400 si l'action est invalide.

    Sécurité :
    - Route protégée par @login_required_admin pour éviter tout accès non autorisé.

    Objectif :
    - Faciliter l'exportation globale des résultats d'une classe entière
    - Supporter plusieurs formats pour différents usages (édition, présentation, archivage).

    Remarque :
    - L'action "pdf" nécessite que pdflatex soit installé sur le serveur.
    - En cas d'erreur lors de la compilation PDF, un message d'erreur sera flashé.
    """
    classe = request.form.get("classe")
    scenario = request.form.get("scenario")
    action = request.form.get("action")

    if action == "txt":
        return export_rapport_txt_internal(classe, scenario)
    elif action == "tex":
        return export_rapport_tex_internal(classe, scenario)
    elif action == "pdf":
        return export_rapport_pdf_internal(classe, scenario)  # 🔥 à ajouter
    else:
        abort(400)  # Requête incorrecte




def export_rapport_txt_internal(classe, scenario):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    if not classe or not scenario:
        return "❌ Classe ou scénario manquant", 400

    with engine.connect() as cn:
        # Récupérer les élèves
        students = cn.execute(text("""
            SELECT student_id FROM students
            WHERE class = :cls
            ORDER BY student_id
        """), {"cls": classe}).scalars().all()

        # Récupérer le nom du scénario
        scenario_name = cn.execute(text("""
            SELECT name FROM scenarios
            WHERE id = :scid
        """), {"scid": scenario}).scalar()

        rapport = ""

        for sid in students:
            rapport += f"Rapport élève : {sid}\n"
            rapport += f"Scénario : {scenario_name}\n\n"

            # Résultats par exercice
            exos = cn.execute(text("""
                SELECT e.ordinal, a.is_correct, a.given_answer
                FROM attempts a
                JOIN exercises e ON e.exercise_id = a.exercise_id
                JOIN exercise_sets s ON s.set_id = e.set_id
                WHERE a.student_id = :sid
                AND s.scenario_id = :scid
                ORDER BY e.ordinal
            """), {"sid": sid, "scid": scenario}).mappings().all()

            for exo in exos:
                status = "✅ Réussi" if exo["is_correct"] else "❌ Échec"
                answer = exo["given_answer"] or "(aucune réponse)"
                rapport += f"Exercice {exo['ordinal']} : {status} - Dernière réponse : \"{answer}\"\n"

            # Feedback éventuel
            fb = cn.execute(text("""
                SELECT feedback FROM feedbacks
                WHERE student_id = :sid
                AND scenario_id = :scid
            """), {"sid": sid, "scid": scenario}).scalar()

            if fb:
                rapport += "\n📘 Feedback IA :\n" + fb.strip() + "\n"

            rapport += "\n" + "-"*50 + "\n\n"

    filename = f"rapport_{classe}_scenario{scenario}.txt"

    return Response(
        rapport,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

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



def export_rapport_tex_internal(classe, scenario):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))


    if not classe or not scenario:
        return "Paramètres manquants", 400

    with engine.connect() as cn:
        # Récupérer tous les élèves de la classe
        students = [r[0] for r in cn.execute(text("""
            SELECT student_id FROM students
            WHERE class = :cls
            ORDER BY student_id
        """), {"cls": classe})]

        # Récupérer le nom du scénario
        scenario_name = cn.execute(text("""
            SELECT name FROM scenarios
            WHERE id = :scid
        """), {"scid": scenario}).scalar()

    rapport = r"""
\documentclass{article}
\usepackage[utf8]{inputenc}
\usepackage{amssymb}
\usepackage{pifont}
\usepackage{geometry}
\geometry{a4paper, margin=1in}
\begin{document}

\title{Résultats globaux \\ \textbf{Scénario : """ + scenario_name + r"""}}
\date{}
\maketitle
"""

    for sid in students:
        rapport += r"\section*{" + sid + "}\n\n"

        with engine.connect() as cn:
            exos = cn.execute(text("""
                SELECT e.ordinal, a.is_correct, a.given_answer
                FROM attempts a
                JOIN exercises e ON e.exercise_id = a.exercise_id
                JOIN exercise_sets s ON s.set_id = e.set_id
                WHERE a.student_id = :sid
                  AND s.scenario_id = :scid
                ORDER BY e.ordinal
            """), {"sid": sid, "scid": scenario}).mappings().all()

            for exo in exos:
                status = r"\ding{51} Réussi" if exo["is_correct"] else r"\ding{55} Échec"
                answer = sanitize_tex(exo["given_answer"]) or "(aucune réponse)"
                rapport += f"Exercice {exo['ordinal']} : {status} -- Réponse : \"{answer}\"\n\n"

            fb = cn.execute(text("""
                SELECT feedback FROM feedbacks
                WHERE student_id = :sid
                AND scenario_id = :scid
            """), {"sid": sid, "scid": scenario}).scalar()

            if fb:
                clean_feedback = sanitize_tex(fb.strip())
                rapport += r"\ding{41} \textbf{Feedback IA :}" + "\n\n" + clean_feedback + "\n\n"
                # ou variante bulle      rapport += r"\ding{102} \textbf{Feedback IA :}" + "\n\n" + fb.strip() + "\n\n"
                

        rapport += r"\bigskip\hrule\bigskip" + "\n\n"

    rapport += r"\end{document}"

    filename = f"rapport_{classe}_scenario{scenario}.tex"
    return Response(rapport, headers={
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Type": "application/x-tex"
    })



def export_rapport_pdf_internal(classe: str, scenario: str):
    """
    Génère un rapport PDF compilé à partir du LaTeX en mémoire,
    pour la classe et le scénario spécifiés.
    """
    # Récupérer les élèves et le scénario
    with engine.connect() as cn:
        students = [r[0] for r in cn.execute(text("""
            SELECT student_id FROM students
            WHERE class = :cls
            ORDER BY student_id
        """), {"cls": classe})]

        scenario_name = cn.execute(text("""
            SELECT name FROM scenarios
            WHERE id = :scid
        """), {"scid": scenario}).scalar()

    # Construire le contenu LaTeX
    tex_content = r"""
\documentclass{article}
\usepackage[utf8]{inputenc}
\usepackage{amssymb}
\usepackage{pifont}
\usepackage{geometry}
\geometry{a4paper, margin=1in}
\begin{document}

\title{Résultats globaux \\ \textbf{Scénario : """ + scenario_name + r"""}}
\date{}
\maketitle
"""

    for sid in students:
        tex_content += r"\section*{" + sid + "}\n\n"

        with engine.connect() as cn:
            exos = cn.execute(text("""
                SELECT e.ordinal, a.is_correct, a.given_answer
                FROM attempts a
                JOIN exercises e ON e.exercise_id = a.exercise_id
                JOIN exercise_sets s ON s.set_id = e.set_id
                WHERE a.student_id = :sid
                  AND s.scenario_id = :scid
                ORDER BY e.ordinal
            """), {"sid": sid, "scid": scenario}).mappings().all()

            for exo in exos:
                status = r"\ding{51} Réussi" if exo["is_correct"] else r"\ding{55} Échec"
                answer = sanitize_tex(exo["given_answer"]) or "(aucune réponse)"
                tex_content += f"Exercice {exo['ordinal']} : {status} -- Réponse : \"{answer}\"\n\n"

            fb = cn.execute(text("""
                SELECT feedback FROM feedbacks
                WHERE student_id = :sid
                AND scenario_id = :scid
            """), {"sid": sid, "scid": scenario}).scalar()

            if fb:
                tex_content += r"\ding{41} \textbf{Feedback IA :}" + "\n\n" + sanitize_tex(fb.strip()) + "\n\n"

        tex_content += r"\bigskip\hrule\bigskip" + "\n\n"

    tex_content += r"\end{document}"

    # Compiler en PDF
    tmpdirname = tempfile.mkdtemp()  # Pas de "with", on nettoiera après

    try:
        tex_path = os.path.join(tmpdirname, "rapport.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_content)

        # Lance pdflatex
        subprocess.run(["pdflatex", "-interaction=nonstopmode", "rapport.tex"], cwd=tmpdirname, check=True)

        pdf_path = os.path.join(tmpdirname, "rapport.pdf")

        # Envoie le fichier PDF (Flask va le lire puis fermer)
        return send_file(pdf_path, as_attachment=True, download_name=f"rapport_{classe}_scenario{scenario}.pdf")

    except Exception as e:
        app.logger.error(f"Erreur génération PDF : {e}")
        flash(f"❌ Impossible de générer le PDF sur ce serveur.", "error")
        return redirect(url_for('dashboard_eleve'))

    finally:
        try:
            clean_temp_folder()  # 🧹 Nettoyage auto après export
        except Exception as e:
            app.logger.warning(f"⚠️ Erreur nettoyage temporaire : {e}")

# --- 3 derniers scénarios de la classe, sans feedback de cet élève ----
def latest_scenarios_without_feedback(engine, class_name, student_id, limit=3):
    """
    Renvoie au plus <limit> scénarios (id, nom, matiere, created_at)
    créés le plus récemment dans la classe <class_name>, en excluant
    ceux pour lesquels <student_id> possède déjà un feedback. (pas de distinction de matiere)
    """
    sql = """
        WITH last AS (
          SELECT id, name, matiere, created_at, resume
          FROM   scenarios
          WHERE  class_name = :cls
          ORDER  BY created_at DESC
          LIMIT  :lim
        )
        SELECT l.*
        FROM   last l
        LEFT   JOIN feedbacks f
               ON f.scenario_id = l.id AND f.student_id = :stu
        WHERE  f.scenario_id IS NULL          -- pas de feedback pour cet élève
        ORDER  BY l.created_at DESC;
    """
    params = {"cls": class_name, "stu": student_id, "lim": limit}
    with engine.connect() as cn:
        return cn.execute(text(sql), params).mappings().all()




# ───────────  Telechargement Eleves────────────────────────────────────────


def build_conversation_txt():
    """
    Construit une version texte brute de la conversation, organisée par exercice.
    """
    from collections import defaultdict
    from textwrap import indent

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

    sections = defaultdict(list)
    current_exo = None

    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "").strip()
        if not content:
            continue

        if role == "exo":
            current_exo = content.split(":")[0].strip()
        else:
            sections[current_exo].append((role, content))

    # Génération du contenu brut
    output = StringIO()
    output.write(f"🧠 Conversation pédagogique\n")
    output.write(f"Matière : {matiere}\n")
    output.write(f"Fiche : {scenario_name}\n\n")

    for section, messages in sections.items():
        output.write(f"========== {section or 'Introduction'} ==========\n\n")
        for role, content in messages:
            label = {
                "user": "Élève",
                "assistant": "Assistant IA",
                "meta": "Note système"
            }.get(role, role.capitalize())

            output.write(f"--- {label} ---\n")
            output.write(indent(content.strip(), "    "))
            output.write("\n\n")

    return output.getvalue()


def filter_latex_macros(tex):
    # remplace uniquement les vraies commandes \cf isolées (suivies d’un espace, d’un point, etc.)
    tex = re.sub(r'\\cf\b', r'cf', tex)
    tex = re.sub(r'\\tg\b', r'tan', tex)
    tex = re.sub(r'\\ln\b', r'log', tex)
    return tex

def format_content_latex(content):
    """
    Formate le contenu Markdown simplifié pour LaTeX :
    - Texte brut → traité avec sanitize_tex_preserving_math()
    - Blocs → transformés en \begin{lstlisting}...end{lstlisting}
    - Nettoie les environnements mathématiques ...
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


def sanitize_tex_preserving_math(text: str) -> str:
    text = normalize_quotes(text)

    # 🔴 Supprime les emojis et autres caractères unicode problématiques
    text = re.sub(r'[^\x00-\xFF]', '', text)

    math_pattern = re.compile(r'(\\\(.+?\\\)|\\\[.+?\\\]|\$\$.+?\$\$)', re.DOTALL)
    parts = math_pattern.split(text)

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
                '^': r'\textasciicircum{}',
                '\\': r'\textbackslash{}',
            }
            for old, new in replacements.items():
                part = part.replace(old, new)

            part = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', part)
            part = re.sub(r'\n{2,}', '\n\n', part)
            sanitized_parts.append(part)

    return ''.join(sanitized_parts)




def clean_code_block_for_latex(code):
    code = code.replace(r"\cf", "cf")
    code = code.replace(r"\tg", "tan")
    code = code.replace(r"\ln", "log")
    code = re.sub(r'[^\x00-\x7F]+', '', code)
    return code

def normalize_quotes(text):
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



def build_conversation_pdf():
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
    sections = defaultdict(list)
    current_exo = None

    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "").strip()

        if not content:
            continue

        if role == "exo":
            current_exo = sanitize_tex(content.split(":")[0])  # Exercice 1, etc.
        else:
            sections[current_exo].append((role, content))  # on garde le Markdown brut ici


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

    for section, messages in sections.items():
        tex += f"\\section{{{section}}}\n\n"
        for role, content in messages:
            role_title = {
                "user": "Élève",
                "assistant": "Assistant IA",
                "meta": "Note système"
            }.get(role, role.capitalize())

            tex += f"\\subsection*{{{role_title}}}\n"
            print("==== CONTENU BRUT DU MESSAGE ====")
            print(repr(content))
            print("==== CONTENU FORMATÉ LATEX ====")
            print(repr(format_content_latex(content)))

            tex += format_content_latex(content) + "\n\n"

    tex += r"\end{document}"

    print("======== TEX START ========")
    print(tex)
    print("======== TEX END ==========")

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





@app.route("/telecharger_conversation")
@login_required
def telecharger_conversation():
    app.logger.info("→ Téléchargement de la conversation demandé")

    pdf_path = build_conversation_pdf()
    if pdf_path and os.path.exists(pdf_path):
        app.logger.info("✅ PDF conversation généré avec succès")
        return send_file(pdf_path, as_attachment=True, download_name="conversation.pdf")

    app.logger.warning("⚠️ PDF indisponible — fallback en .txt")

    txt = build_conversation_txt()
    return Response(
        txt,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=conversation.txt"}
    )



# ───────────  Dashboard Client Eleves────────────────────────────────────────







@app.route("/mon_dashboard")
@login_required
def mon_dashboard():

    student_id = session["student_id"]
    class_name = student_id.split("-")[0]
    active_scenario_id = session.get("active_scenario_id")
    # matière passée en GET ?matiere=MATHS
    matiere = request.args.get("matiere")
    if matiere is not None and matiere in ("", "MATHS", "SVT", "NSI"):
        session["active_matiere"] = matiere

    active_matiere = session.get("active_matiere", "")
    # … requête SQL qui filtre les scénarios sur active_matiere …
    
    
    scenarios_disponibles = []
    evolution = []
    hist = []
    feedback_row = None
    matieres_disponibles = []

    with engine.connect() as conn:
        # 🔹 Charger toutes les matières disponibles pour la classe
        matieres_disponibles = conn.execute(text("""
            SELECT DISTINCT matiere
            FROM scenarios
            WHERE class_name = :cls AND matiere IS NOT NULL
            ORDER BY matiere
        """), {"cls": class_name}).scalars().all()

        if not active_matiere and matieres_disponibles:
            active_matiere = matieres_disponibles[0]  # fallback première matière

        session["active_matiere"] = active_matiere
        
        
        # 🔥 Charger TOUS les scénarios possibles pour la classe dans la matiere active
        results = conn.execute(text("""
            SELECT id, name, matiere, resume
            FROM scenarios
            WHERE class_name = :cls
              AND (:mat='' OR matiere = :mat)
            ORDER BY created_at DESC
        """), {"cls": class_name, "mat": active_matiere or ''}).mappings().all()

        if results:
            latest_id = max([r["id"] for r in results], key=int)
            
            for r in results:
                fid = r["id"]
                feedback_exists = has_feedback(engine, student_id, scenario_id=fid)
                is_latest = (fid == latest_id)
                scenarios_disponibles.append({
                    "id": fid,
                    "nom": r["name"],
                    "done": bool(feedback_exists),
                    "is_latest": is_latest,
                    "matiere": r["matiere"],  # ← ajoute cette ligne
                    "resume": r.get("resume", "")
                })

        # 🔥 Charger l'évolution : uniquement sur scenarios où il y a eu tentative
        evolution = get_evolution_par_scenario2(student_id,
                                       active_matiere or None)

        # 🔥 Charger le feedback pour le scénario actif
        if active_scenario_id:
            feedback_row = conn.execute(text("""
                SELECT feedback, created_at
                FROM feedbacks
                WHERE student_id = :sid
                  AND scenario_id = :scid
                ORDER BY created_at DESC
                LIMIT 1
            """), {"sid": student_id, "scid": active_scenario_id}).mappings().first()
            
    last_scenarios = latest_scenarios_without_feedback(
    engine,
    class_name=session["class_name"],
    student_id=session["student_id"],
    limit=3
    )
    courant = next(
        (sc for sc in scenarios_disponibles
         if str(sc["id"]) == str(active_scenario_id)), None)
    return render_template("mondashboard.html",
                           student_id=student_id,
                           hist=hist,
                           scenarios_disponibles=scenarios_disponibles,
                           evolution=evolution,
                           feedback=feedback_row,
                           courant=courant,
                           active_scenario_id=active_scenario_id,
                           matieres_disponibles=matieres_disponibles,
                           last_scenarios=last_scenarios,
                           active_matiere=active_matiere)



@app.route("/changer_scenario", methods=["POST"])
@login_required
def changer_scenario():
    """
    Permet à l'élève de changer de scénario actif depuis son "mondashboard."
    Recharge toutes les données nécessaires en session.
    """


    nouveau_scenario = request.form.get("nouveau_scenario")

    if not nouveau_scenario:
        flash("❌ Aucun scénario sélectionné.", "error")
        return redirect(url_for("mon_dashboard"))

    student_id = session["student_id"]
    class_name = student_id.split("-")[0]

    # Vérifier que ce scénario appartient bien à cette classe
    with engine.connect() as cn:
        scenario_existe = cn.scalar(text("""
            SELECT EXISTS(
                SELECT 1
                FROM scenarios
                WHERE id = :scid
                  AND class_name = :cls
            )
        """), {"scid": nouveau_scenario, "cls": class_name})

    if not scenario_existe:
        flash("❌ Scénario invalide ou non autorisé.", "error")
        return redirect(url_for("mon_dashboard"))
    
    # récupérer l’ID
    scid    = request.form.get("nouveau_scenario", type=int)
    
    # 🔑  synchroniser la matière affichée    
    # ① on essaie de lire le champ caché
    matiere = request.form.get("matiere", "").upper()


    # ② si le champ est vide ou invalide → on la déduit en SQL
    if matiere not in ("MATHS", "SVT", "NSI"):
        with engine.connect() as cn:
            matiere = cn.scalar(text(
                "SELECT matiere FROM scenarios WHERE id = :sid"
            ), {"sid": scid}) or ""

    session["active_matiere"] = matiere
    session["active_scenario_id"] = scid

    # Recharger MAP_JSON, ANS_JSON, CAT_JSON
    map_json, ans_json, cat_json = load_json_from_db(engine, class_name, nouveau_scenario)

    # Recharger exos déjà faits et feedback pour ce scénario
    done_refs = load_done_refs(engine, student_id, scenario_id=nouveau_scenario)
    feedback_exists = has_feedback(engine, student_id, scenario_id=nouveau_scenario)

    # 🔑  RAZ du fil de discussion et des compteurs
    session.pop("history",     None)
    session.pop("exo_courant", None)
    session.pop("exo_id",      None)
    session.pop("start",       None)
    
    # Mettre à jour la session
    session["MAP_JSON"] = map_json
    session["ANS_JSON"] = ans_json
    session["CAT_JSON"] = cat_json
    session["exo_valide"] = done_refs
    session["has_feedback"] = feedback_exists

    flash("✅ Activité sélectionnée.", "success")
    return redirect(url_for("mon_dashboard",
                        matiere=session["active_matiere"]))


@app.route("/changer_scenario_ia", methods=["POST"])
def changer_scenario_ia():
    """
    Permet à l'élève de changer de scénario actif depuis son "interface ia."
    Recharge toutes les données nécessaires en session.
    """


    nouveau_scenario = request.form.get("nouveau_scenario")

    if not nouveau_scenario:
        flash("❌ Aucun scénario sélectionné.", "error")
        return redirect(url_for("interface_ia"))

    student_id = session["student_id"]
    class_name = student_id.split("-")[0]

    # Vérifier que ce scénario appartient bien à cette classe
    with engine.connect() as cn:
        scenario_existe = cn.scalar(text("""
            SELECT EXISTS(
                SELECT 1
                FROM scenarios
                WHERE id = :scid
                  AND class_name = :cls
            )
        """), {"scid": nouveau_scenario, "cls": class_name})

    if not scenario_existe:
        flash("❌ Scénario invalide ou non autorisé.", "error")
        return redirect(url_for("interface_ia"))
    
    # récupérer l’ID
    scid    = request.form.get("nouveau_scenario", type=int)
    
    # 🔑  synchroniser la matière affichée    
    # ① on essaie de lire le champ caché
    matiere = request.form.get("matiere", "").upper()


    # ② si le champ est vide ou invalide → on la déduit en SQL
    if matiere not in ("MATHS", "SVT", "NSI"):
        with engine.connect() as cn:
            matiere = cn.scalar(text(
                "SELECT matiere FROM scenarios WHERE id = :sid"
            ), {"sid": scid}) or ""

    session["active_matiere"] = matiere
    session["active_scenario_id"] = scid

    # Recharger MAP_JSON, ANS_JSON, CAT_JSON
    map_json, ans_json, cat_json = load_json_from_db(engine, class_name, nouveau_scenario)

    # Recharger exos déjà faits et feedback pour ce scénario
    done_refs = load_done_refs(engine, student_id, scenario_id=nouveau_scenario)
    feedback_exists = has_feedback(engine, student_id, scenario_id=nouveau_scenario)

    # 🔑  RAZ du fil de discussion et des compteurs
    session.pop("history",     None)
    session.pop("exo_courant", None)
    session.pop("exo_id",      None)
    session.pop("start",       None)
    
    # Mettre à jour la session
    session["MAP_JSON"] = map_json
    session["ANS_JSON"] = ans_json
    session["CAT_JSON"] = cat_json
    session["exo_valide"] = done_refs
    session["has_feedback"] = feedback_exists

    return redirect(url_for("interface_ia",
                        matiere=session["active_matiere"]))



@app.route("/mesdonnees")
@login_required
def mes_donnees():
    return render_template("mesdonnees.html", student_id=session["student_id"])

@app.route("/telecharger_logs")
@login_required
def telecharger_logs():
    return export_logs_eleve_csv(engine_rgpd, session["student_id"])

# ─────────── Gestion Erreurs - Sécurité du Site ──────────────────────────────────────


@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500

@app.route("/csp-report", methods=["POST"])
def csp_report():
    if request.content_type == "application/csp-report":
        data = request.get_data(as_text=True)
        app.logger.warning(f"[CSP] Violation (raw CSP report): {data}")
    elif request.is_json:
        report = request.get_json()
        app.logger.warning(f"[CSP] Violation (JSON): {json.dumps(report)}")
    else:
        app.logger.warning(f"[CSP] Violation reçue avec content-type inconnu : {request.content_type}")
    return '', 204



@app.after_request
def secure_headers(response):
    # CSP par défaut (très stricte)
    csp_base = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "font-src 'self';"
    )

    # CSP pour /ia : autorise les styles inline, les scripts inline + eval, + polices MathJax
    csp_ia = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "script-src 'self' https://cdn.jsdelivr.net https://polyfill.io https://cdnjs.cloudflare.com 'unsafe-eval' 'unsafe-inline'; "
        "connect-src 'self'; "
        "font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com;"
    )


    # Application de la bonne politique selon l'URL
    if request.path.startswith("/ia") or request.path.startswith("/dashboard")  or request.path.startswith("/mon_dashboard"):
        response.headers['Content-Security-Policy'] = csp_ia
    else:
        response.headers['Content-Security-Policy'] = csp_base

    # Ajout du reporting CSP
    response.headers['Content-Security-Policy-Report-Only'] = response.headers['Content-Security-Policy']
    response.headers['Content-Security-Policy-Report-Only'] += "; report-uri /csp-report"

    response.headers['Report-To'] = json.dumps({
        "group": "csp-endpoint",
        "max_age": 10886400,
        "endpoints": [{"url": "/csp-report"}]
    })

    # Headers de sécurité standards
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'

    return response


'''
version prod 
@app.after_request
def secure_headers(response):
    # CSP stricte (pour tout sauf /ia)
    csp_base = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "report-uri /csp-report"
    )

    # CSP étendue pour /ia (autorise MathJax, styles dynamiques, scripts inline)
    csp_ia = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' https://cdn.jsdelivr.net https://polyfill.io 'unsafe-eval' 'unsafe-inline'; "
        "connect-src 'self'; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "report-uri /csp-report"
    )

    # Appliquer la bonne politique selon l'URL
    if request.path.startswith("/ia"):
        response.headers['Content-Security-Policy'] = csp_ia
    else:
        response.headers['Content-Security-Policy'] = csp_base

    # Reporting JSON compatible navigateurs modernes
    response.headers['Report-To'] = json.dumps({
        "group": "csp-endpoint",
        "max_age": 10886400,
        "endpoints": [{"url": "/csp-report"}]
    })

    # Headers HTTP classiques de sécurité
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'

    return response


'''
# ─────────── run ───────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
