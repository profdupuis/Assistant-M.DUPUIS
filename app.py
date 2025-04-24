import os, re, json, time, pathlib
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_session import Session
from markupsafe import Markup
from openai import OpenAI
from sqlalchemy import create_engine, text
from sqlalchemy.exc import NoResultFound
from dotenv import load_dotenv
from datetime import timedelta
from flask import request, abort, render_template
from sqlalchemy import text, bindparam

# ─────────── init ────────────────────────────────────────────────────
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev")
app.config.update(SESSION_PERMANENT=False, SESSION_TYPE="filesystem")
Session(app)

engine = create_engine(os.getenv("DATABASE_URL"), future=True)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def extract_niveau(prompt: str) -> int:
    m = re.search(r'\[niveau\s*(\d+)\]', prompt, re.IGNORECASE)
    return int(m.group(1)) if m else 1

def clean_prompt(prompt: str) -> str:
    lines = prompt.splitlines()
    lines = [line for line in lines if not re.search(r'\[niveau\s*\d+\]', line, re.IGNORECASE)]
    lines = [line for line in lines if not re.match(r'^exo_\d+', line.strip(), re.IGNORECASE)]
    return "\n".join(lines).strip()

def load_json_from_db(class_name: str):
    map_json, ans_json, cat_json = {}, {}, {}
    with engine.connect() as cn:
        rows = cn.execute(text("""
            SELECT e.ordinal, e.prompt, e.answer, c.name AS category
            FROM exercises e
            JOIN exercise_sets s ON s.set_id = e.set_id
            JOIN scenarios sc ON sc.id = s.scenario_id
            LEFT JOIN categories c ON c.category_id = e.category_id
            WHERE s.is_active = true AND sc.class_name = :cls
            ORDER BY e.ordinal
        """), {"cls": class_name}).mappings().all()

    for row in rows:
        ref = f"exo_{row['ordinal']}"
        map_json[ref] = f"🧩 EXERCICE {row['ordinal']} [niveau {extract_niveau(row['prompt'])}]\n\n{clean_prompt(row['prompt'])}"
        ans_json[ref] = row["answer"]
        cat_json[ref] = row["category"] or "Sans catégorie"



    return map_json, ans_json, cat_json


# ─────────── helpers DB ──────────────────────────────────────────────
def exo_row(conn, ordinal: int):
    row = conn.execute(text("""
        SELECT exercise_id
        FROM exercises
        JOIN exercise_sets USING(set_id)
        WHERE is_active=true AND ordinal=:o
    """), {"o": ordinal}).mappings().first()
    if not row:
        raise NoResultFound
    return row

# ─────────── login ──────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def login():
    err = None
    if request.method == "POST":
        sid = request.form.get("id", "").strip().upper()
        if sid:
            with engine.connect() as cn:
                ok = cn.scalar(text(
                    "SELECT 1 FROM students WHERE student_id=:sid"), {"sid": sid})
            if ok:
                session.clear()
                session["student_id"] = sid
                return redirect(url_for("interface_ia"))
            err = "Identifiant inconnu"
        else:
            err = "Identifiant manquant"
    return render_template("login.html", error=err)



def load_done_refs(student_id: str) -> list[str]:
    # charge les exercices deja faits de la fiche
    class_name = student_id.split("-")[0]
    with engine.connect() as cn:
        scenario_id = cn.scalar(text("""
            SELECT id FROM scenarios
            WHERE class_name = :cls AND is_active = true
        """), {"cls": class_name})

        row = cn.execute(text("""
            SELECT refs FROM done_refs
            WHERE student_id = :sid AND scenario_id = :scid
            LIMIT 1
        """), {"sid": student_id, "scid": scenario_id}).mappings().first()

        return row["refs"] if row else []

def get_next_exercise_ref(map_json: dict, done_refs: list[str]) -> str:
    """
    Renvoie l'ID du prochain exercice à faire (ex: 'exo_2')
    ou le premier de la fiche si tous sont faits.
    """
    all_refs = sorted(map_json.keys(), key=lambda r: int(r.split("_")[1]))
    pending = [ref for ref in all_refs if ref not in done_refs]
    return pending[0] if pending else all_refs[0]


def has_feedback(student_id: str) -> bool:
    """
    Renvoie True si un feedback final existe déjà pour l'élève et le scénario actif et donc si la fiche a déja été terminée
    """
    class_name = student_id.split("-")[0]
    with engine.connect() as cn:
        scenario_id = cn.scalar(text("""
            SELECT id FROM scenarios WHERE class_name = :cls AND is_active = true
        """), {"cls": class_name})

        result = cn.scalar(text("""
            SELECT 1 FROM feedbacks
            WHERE student_id = :sid AND scenario_id = :scid
            LIMIT 1
        """), {"sid": student_id, "scid": scenario_id})

    return result is not None



    
# ─────────── page IA (intro + exo 1) ────────────────────────────────
@app.route("/ia")
def interface_ia():
    if "student_id" not in session:
        return redirect(url_for("login"))
    student_id = session["student_id"]
    class_name = student_id.split("-")[0]
    
    session["exo_valide"] = load_done_refs(student_id)
    session["has_feedback"] = has_feedback(student_id)

        
    if "MAP_JSON" not in session:
        map_json, ans_json, cat_json = load_json_from_db(class_name)
        session["MAP_JSON"] = map_json
        session["ANS_JSON"] = ans_json
        session["CAT_JSON"] = cat_json

    MAP_JSON = session["MAP_JSON"]
    ANS_JSON = session["ANS_JSON"]
    CAT_JSON = session["CAT_JSON"]




    with engine.connect() as cn:
        # 1. Récupérer le scénario actif de la classe
        row = cn.execute(text("""
            SELECT s.id, s.content
            FROM scenarios s
            WHERE s.class_name = :cls AND s.is_active = true
            LIMIT 1
        """), {"cls": class_name}).mappings().first()

        if not row:
            return "❌ Aucun scénario actif pour cette classe."

        content = row["content"]

        # 2. Extraire l’intro élève
        import re
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

    next_ref = get_next_exercise_ref(MAP_JSON, session["exo_valide"])
    exo_num = int(next_ref.split("_")[1])

    all_refs = sorted(MAP_JSON.keys(), key=lambda r: int(r.split("_")[1]))
    done_refs = session["exo_valide"]

    if len(done_refs) == len(all_refs):
        if session["has_feedback"]:
            session["exo_valide"]=[]
        reprise_msg = "🎉 Tu as déjà terminé tous les exercices de cette fiche. Tu peux les refaire si tu veux t'entraîner."
    elif len(done_refs) == 0:
        reprise_msg = "🚀 C’est parti ! Voici ton premier exercice de la fiche."
    else:
        reprise_msg = "🔁 On reprend là où tu t’étais arrêté. Voici l’exercice suivant :"


    texte = f"{intro}\n\n{reprise_msg}\n\n{MAP_JSON[next_ref]}".strip()
    html = Markup("<br>".join(texte.splitlines()))



    return render_template("ia_interface.html", initial_message=html)

# ─────────── scénario complet envoyé à GPT ──────────────────────────
def scenario_prompt() -> str:
    student_id = session.get("student_id", "")
    class_name = student_id.split("-")[0]
    with engine.connect() as cn:
        row = cn.execute(text("""
            SELECT content
            FROM scenarios
            WHERE class_name = :cls AND is_active = true
            LIMIT 1
        """), {"cls": class_name}).mappings().first()

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
        scenario_id = cn.scalar(text("""
            SELECT id FROM scenarios WHERE class_name = :cls AND is_active = true
        """), {"cls": class_name})

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





# ─────────── Enregistrement des logs  ───────────────────────────────────────
import hashlib

# moteur dédié au logging (app_log)
engine_log = create_engine(os.getenv("DATABASE_URL_LOG"), future=True)

def save_log(user_id, prompt, completion, flags, model, prev_hash):
    # chaînage hash
    raw = f"{time.time()}{user_id}{prompt}{completion}{json.dumps(flags)}{model}{prev_hash or ''}"
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
    return this_hash

# ─────────── Moderation des logs  ───────────────────────────────────────

def moderate(text: str) -> dict:
    """
    Appelle l’endpoint OpenAI Moderation et renvoie un dict de flags.
    Clés : hate, harassment, self_harm, …
    Valeurs : bool
    """
    try:
        resp = client.moderations.create(
            model="text-moderation-latest",
            input=text
        )
        # resp.results est une liste de ModerationResult
        # chaque ModerationResult.categories est déjà un dict {cat: bool}
        return resp.results[0].categories.to_dict()
    except Exception as e:
        app.logger.error(f"Modération échouée : {e}")
        # on renvoie un flag d’erreur pour bloquer — ou à vous de décider
        return {"error": True}

BANNED = {"porn", "fuck", "xxx"}

def contains_banned(text: str) -> bool:
    t = text.lower()
    return any(word in t for word in BANNED)




# ─────────── API conversation ───────────────────────────────────────
@app.route("/api/message", methods=["POST"])
def api_message():
    if "student_id" not in session:
        return jsonify({"reply": "Session expirée, reconnecte‑toi."})

    user_msg = request.json.get("message", "")

    # 1) Modération du prompt élève
    
    # Moderation par mots clé avant moderation open AI eventuellement à ajouter
    #if contains_banned(user_msg):
        #save_log(...............):
        #return jsonify({"reply": "Désolé, je ne peux pas répondre à cette demande."})
    

    flags = moderate(user_msg)
    # on distingue l'erreur d'API du vrai blocage
    error = flags.get("error", False)
    # on cherche un flag métier à True
    blocked = any(v is True for k,v in flags.items() if k != "error")
    # 2) Si un flag True ou erreur → on bloque
    # bloquer si un flag à True ou si on a retourné {"error":True}
    if error or blocked:
        # (Optionnel) on enregistre quand même ce prompt bloqué
        prev_hash = session.get("last_hash")  # ou None si c’est la 1ʳᵉ requête
        session["last_hash"] = save_log(
            session["student_id"],
            user_msg,
            completion="",      # pas de réponse GPT
            flags=flags,
            model="moderation-latest",
            prev_hash=prev_hash
        )
        return jsonify({"reply": "Désolé, je ne peux pas répondre à cette demande."})    
    
    
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
    if "history" not in session:
        session["history"] = [{"role": "system", "content": scenario_prompt()}]

    # ── navigation « exercice N »  ##################################  PATCH
    nav = re.search(r'exercice\s+(\d+)', user_msg, re.I)
    if nav:
        session["exo_courant"] = int(nav.group(1))
        with engine.connect() as cn:
            exo = exo_row(cn, session["exo_courant"])
        session.update(exo_id=exo["exercise_id"], start=time.time())

        next_ref   = f"exo_{session['exo_courant']}"
        nav_enonce = "\n\n---\n" + MAP_JSON.get(next_ref,
                                               "_Énoncé introuvable_")
    else:
        nav_enonce = ""
    # -----------------------------------------------------------------

    # temps écoulé
    elapsed = int(time.time() - session.get("start", time.time()))
    info    = f"[INFO] exo_courant={session['exo_courant']}; elapsed_s={elapsed}"

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
    
    
    # appel GPT
    ai = client.chat.completions.create(
        model="gpt-4.1",
        messages=session["history"],
        user=session["student_id"]
    )
    reply = ai.choices[0].message.content
    session["history"].append({"role": "assistant", "content": reply})



    # 3) Et on enregistre la réponse GPT en log
    prev_hash = session.get("last_hash")
    session["last_hash"] = save_log(
        session["student_id"],
        user_msg,
        completion=reply,
        flags={k: False for k in flags},  # aucun flag levé ici
        model="gpt-4.1",
        prev_hash=prev_hash
    )
    
    # tentative (ne compte pas la simple navigation)
    if not nav:
        is_ok = "EXERCICE TERMINE : ✅" in reply.upper()
        with engine.begin() as cn:
            cn.execute(text("""
                INSERT INTO attempts(student_id,exercise_id,started_at,ended_at,
                                     elapsed_s,given_answer,is_correct)
                VALUES (:sid,:eid,to_timestamp(:s),now(),:e,:ans,:ok)
            """), {"sid": session["student_id"], "eid": session["exo_id"],
                   "s": session.get("start", time.time()), "e": elapsed,
                   "ans": user_msg[:500], "ok": is_ok})

        if is_ok:
            ref = f"exo_{session['exo_courant']}"
            if ref not in session.get("exo_valide", []):
                session.setdefault("exo_valide", []).append(ref)

            
            ####################### enregistrement done ref en bdd ##############################
            update_done_refs(session["student_id"], ref)








            step = 1  # ou 2 si on veut sauter selon le temps
            # Liste des exos restants
            # all_refs = sorted(MAP_JSON.keys(), key=lambda x: int(x.split("_")[1]))
            done_refs = session.get("exo_valide", [])
            pending_refs = [ref for ref in all_refs if ref not in done_refs]
            

            if pending_refs == [] and not session.get("has_feedback"):
                # 🎉 Tous les exos faits → générer feedback
                session["history"].append({
                    "role": "system",
                    "content": (
                        "Tu dois maintenant féliciter l'élève d'avoir terminé tous les exercices, "
                        "et encore plus le féliciter s’il a réussi après des erreurs et qu’il s’est accroché. "
                        "Résume en 2-3 phrases les compétences travaillées dans la fiche. "
                        "Reste bref, positif, et ne répète pas toutes les réponses."
                    )
                })

                final_feedback = client.chat.completions.create(
                    model="gpt-4.1",
                    messages=session["history"],
                    user=session["student_id"]
                )
                feedback = final_feedback.choices[0].message.content
                session["has_feedback"] = True
                with engine.begin() as cn:
                    class_name = session["student_id"].split("-")[0]
                    scenario_id = cn.scalar(text("""
                        SELECT id FROM scenarios WHERE class_name = :cls AND is_active = true
                    """), {"cls": class_name})

                    cn.execute(text("""
                        INSERT INTO feedbacks(student_id, scenario_id, feedback)
                        VALUES (:sid, :scid, :fb)
                    """), {
                        "sid": session["student_id"],
                        "scid": scenario_id,
                        "fb": feedback
                    })
                reply += "\n\n📘 " + feedback
                session["history"].append({"role": "assistant", "content": feedback})
                session["exo_courant"] = -1
                nav_enonce = ""
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

                    reply += f"\n\n{badge} On continue avec l’exercice {session['exo_courant']} :\n\n"

                    reply += MAP_JSON[prochain]

    # renvoi : réponse GPT + éventuel énoncé demandé
    return jsonify({"reply": reply + nav_enonce})

# ─────────── reset session ─────────────────────────────────────────
@app.route("/reset")
def reset():
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

def get_evolution_par_scenario(classe=None, student_id=None):
    where = []
    params = {}

    if classe:
        where.append("s.class = :classe")
        params["classe"] = classe
    if student_id:
        where.append("a.student_id = :sid")
        params["sid"] = student_id

    filter_clause = "WHERE " + " AND ".join(where) if where else ""

    sql = text(f"""
        SELECT
          sc.name,
          COUNT(*) FILTER (WHERE a.is_correct) AS nb_bonnes,
          COUNT(*) AS nb_total
        FROM attempts a
        JOIN students s       ON s.student_id = a.student_id
        JOIN exercises e      ON e.exercise_id = a.exercise_id
        JOIN exercise_sets es ON es.set_id = e.set_id
        JOIN scenarios sc     ON sc.id = es.scenario_id
        {filter_clause}
        GROUP BY sc.id, sc.name, sc.created_at
        ORDER BY sc.created_at
    """)

    with engine.connect() as cn:
        rows = cn.execute(sql, params).fetchall()

    return [
        {
            "scenario": r[0],
            "nb_bonnes": r[1],
            "nb_total": r[2],
            "pourcentage": round(100 * r[1] / r[2], 1) if r[2] > 0 else 0
        }
        for r in rows
    ]






@app.route("/dashboard")
def dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    # 0) Récupérer toutes les classes et scenarios pour les menus déroulants
    with engine.connect() as conn:
        all_classes = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT class FROM students ORDER BY class"
        ))]
        all_scenarios = conn.execute(text("""
            SELECT id, name, class_name, is_active
            FROM scenarios
            ORDER BY class_name, name
        """)).mappings().all()

    # 1) Lire les filtres utilisateur
    exo    = request.args.get("exercice", type=int)
    classe = request.args.get("classe",    default="", type=str)
    since  = request.args.get("since",      type=int, default=0)

    # 2) Clause WHERE dynamique
    wheres = ["s.is_active = TRUE"]
    params = {}

    if exo:
        wheres.append("e.ordinal = :exo")
        params["exo"] = exo

    if classe:
        wheres.append("st.class = :classe")
        params["classe"] = classe

    if since > 0:
        wheres.append("a.ended_at >= now() - :days * interval '1 day'")
        params["days"] = since

    scenario_filter_clause = ""
    scenario_nom = None
    evolution = [] # suivi eleve - classe
    
    if classe:
        evolution = get_evolution_par_scenario(classe=classe)
        with engine.connect() as cn:
            scen = cn.execute(text("""
                SELECT id, name FROM scenarios
                WHERE class_name = :cls AND is_active = true
                LIMIT 1
            """), {"cls": classe}).mappings().first()
            if scen:
                scenario_filter_clause = " AND s.scenario_id = :scid"
                params["scid"] = scen["id"]
                scenario_nom = scen["name"]

    where_clause = " AND ".join(wheres)

    # 3) Requête statistiques par exercice
    sql_rate = text(f"""
        SELECT
          e.ordinal AS exercice,
          COUNT(*) FILTER (WHERE a.is_correct) AS n_success,
          COUNT(*) AS n_total,
          ROUND(AVG(a.elapsed_s), 1) AS avg_time
        FROM attempts a
          JOIN exercises e     ON e.exercise_id = a.exercise_id
          JOIN exercise_sets s ON s.set_id      = e.set_id
          JOIN students st     ON st.student_id = a.student_id
        WHERE {where_clause}{scenario_filter_clause}
        GROUP BY e.ordinal
        ORDER BY e.ordinal
    """)

    # 4) Requête statistiques par classe
    sql_class = text(f"""
        SELECT
          st.class,
          COUNT(*) FILTER (WHERE a.is_correct) AS n_success,
          COUNT(*) AS n_total
        FROM attempts a
          JOIN exercises e     ON e.exercise_id = a.exercise_id
          JOIN exercise_sets s ON s.set_id      = e.set_id
          JOIN students st     ON st.student_id = a.student_id
        WHERE {where_clause}{scenario_filter_clause}
        GROUP BY st.class
        ORDER BY st.class
    """)

    # 5) Feedbacks finaux (par classe / scénario actif)
    feedback_rows = []
    if classe:
        with engine.connect() as cn:
            res = cn.execute(text("""
                SELECT id FROM scenarios
                WHERE class_name = :cls AND is_active = true
                LIMIT 1
            """), {"cls": classe}).mappings().first()

            if res:
                scenario_id = res["id"]
                feedback_rows = cn.execute(text("""
                    SELECT f.student_id, s.class, f.feedback, f.created_at
                    FROM feedbacks f
                    JOIN students s ON s.student_id = f.student_id
                    WHERE f.scenario_id = :scid
                    ORDER BY f.created_at DESC
                """), {"scid": scenario_id}).mappings().all()
                
    # 6) Exécuter et afficher
    with engine.connect() as conn:
        stats    = conn.execute(sql_rate,  params).mappings().all()
        by_class = conn.execute(sql_class, params).mappings().all()

    return render_template(
        "dashboard.html",
        all_classes    = all_classes,
        all_scenarios  = all_scenarios,
        stats          = [dict(r) for r in stats],
        by_class       = [dict(r) for r in by_class],
        filter_exo     = exo,
        filter_classe  = classe,
        filter_since   = since,
        evolution=evolution,
        scenario_nom   = scenario_nom,
        feedback_rows=feedback_rows
    )


# ─────────── Gestion Scenarios  ─────────────────────────────────


@app.route("/dashboard/activate_scenario", methods=["POST"])
def activate_scenario():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

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
def delete_scenario():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    scenario_id = request.form.get("scenario_id", type=int)
    if not scenario_id:
        abort(400)

    with engine.begin() as cn:
        # Supprimer le scénario et ses liens éventuels
        cn.execute(text("DELETE FROM exercise_sets WHERE scenario_id = :id"), {"id": scenario_id})
        cn.execute(text("DELETE FROM scenarios WHERE id = :id"), {"id": scenario_id})

    return redirect(url_for("dashboard"))

@app.route("/dashboard/upload_scenario", methods=["POST"])
def upload_scenario():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    file = request.files.get("fichier")
    if not file or not file.filename.endswith(".txt"):
        return "❌ Fichier invalide", 400

    path = pathlib.Path("scenarios") / file.filename
    file.save(path)

    import datetime, re, json

    title = path.stem
    if "-" not in title:
        return "❌ Le nom du fichier doit être au format nomClasse-nomScenario.txt", 400

    class_name, scenar_name = title.split("-", 1)
    full_txt = path.read_text(encoding="utf-8")

    # Découpage des blocs
    def parse_blocks(txt: str):
        raw = re.split(r'🧩\s*EXERCICE\s*\d+', txt, flags=re.I)[1:]
        for bloc in raw:
            diff_match = re.search(r'niveau\s*(\d+)', bloc, flags=re.I)
            diff = int(diff_match.group(1)) if diff_match else 1
            ans_m = re.search(r'\*\*Bonne réponse attendue\s*:\s*\*\*(.*)', bloc)
            ans = ans_m.group(1).strip() if ans_m else None
            cat_m = re.search(r'\*\*Catégorie\s*:\s*\*(.*)', bloc)
            cat = cat_m.group(1).strip() if cat_m else "Autre"
            enonce = re.split(r'\*Fin de l’énoncé\*|\*Fin de l\'énoncé\*', bloc)[0].strip()
            enonce = '\n'.join(line for line in enonce.splitlines() if line.strip())
            yield enonce, ans, diff, cat

    blocks = list(parse_blocks(full_txt))

    with engine.begin() as cn:
        # Nouveau scénario
        scenario_id = cn.scalar(text("""
            INSERT INTO scenarios (name, class_name, content, is_active)
            VALUES (:name, :cls, :content, true)
            RETURNING id
        """), {"name": scenar_name, "cls": class_name, "content": full_txt})

        # Désactiver anciens scénarios de cette classe
        cn.execute(text("""
            UPDATE scenarios SET is_active = false
            WHERE class_name = :cls AND id != :id
        """), {"cls": class_name, "id": scenario_id})

        # Créer la série d'exercices
        set_id = cn.scalar(text("""
            INSERT INTO exercise_sets(title, start_date, is_active, scenario_id)
            VALUES (:t, :d, true, :sid)
            RETURNING set_id
        """), {"t": scenar_name, "d": datetime.date.today(), "sid": scenario_id})

        # Exercices
        for i, (enonce, ans, diff, cat) in enumerate(blocks, 1):
            ref = f"exo_{i}"
            cat_id = cn.scalar(text("""
                INSERT INTO categories(name)
                VALUES (:theme)
                ON CONFLICT(name) DO UPDATE SET name = EXCLUDED.name
                RETURNING category_id
            """), {"theme": cat})
            cn.execute(text("""
                INSERT INTO exercises(set_id, ordinal, prompt, answer, difficulty, category_id)
                VALUES (:sid, :o, :prompt, :ans, :diff, :cid)
            """), {"sid": set_id, "o": i, "prompt": ref + "\n" + enonce,
                   "ans": ans, "diff": diff, "cid": cat_id})

        # 🔥 Assurer désactivation des autres séries
        cn.execute(text("""
            UPDATE exercise_sets
            SET is_active = FALSE
            WHERE scenario_id IN (
                SELECT id FROM scenarios
                WHERE class_name = :cls AND id != :sid
            )
        """), {"cls": class_name, "sid": scenario_id})

        cn.execute(text("""
            UPDATE exercise_sets
            SET is_active = TRUE
            WHERE scenario_id = :sid
        """), {"sid": scenario_id})

    return redirect(url_for("dashboard"))


@app.route("/dashboard/export", methods=["POST"])
def export_csv():
    if not session.get("is_admin"):
        return redirect("/admin")

    classe = request.form.get("classe", "").strip()
    if not classe:
        return "❌ Classe non spécifiée", 400

    with engine.connect() as cn:
        # 1. Identifier le scénario actif
        res = cn.execute(text("""
            SELECT id, name FROM scenarios
            WHERE class_name = :cls AND is_active = true
            LIMIT 1
        """), {"cls": classe}).mappings().first()

        if not res:
            return "❌ Aucun scénario actif pour cette classe", 400

        scenario_id = res["id"]
        scenario_nom = res["name"]

        # 2. Récupérer les tentatives
        rows = cn.execute(text("""
            SELECT st.student_id, e.ordinal, a.is_correct, a.elapsed_s, a.ended_at
            FROM attempts a
            JOIN exercises e     ON e.exercise_id = a.exercise_id
            JOIN exercise_sets s ON s.set_id      = e.set_id
            JOIN students st     ON st.student_id = a.student_id
            WHERE s.scenario_id = :sid AND st.class = :cls
            ORDER BY st.student_id, e.ordinal
        """), {"sid": scenario_id, "cls": classe}).mappings().all()

        # 3. Récupérer les feedbacks
        feedback_map = {
            row["student_id"]: row["feedback"]
            for row in cn.execute(text("""
                SELECT student_id, feedback
                FROM feedbacks
                WHERE scenario_id = :sid
            """), {"sid": scenario_id}).mappings()
        }

        # Génération du fichier CSV
        from io import StringIO
        import csv
        f = StringIO()
        writer = csv.writer(f)
        writer.writerow(["student_id", "exo", "correct", "temps(s)", "date", "feedback"])

        previous_id = None
        for i, r in enumerate(rows):
            current_id = r["student_id"]
            next_id = rows[i + 1]["student_id"] if i + 1 < len(rows) else None
            feedback = feedback_map.get(current_id, "") if current_id != next_id else ""

            writer.writerow([
                current_id,
                r["ordinal"],
                int(r["is_correct"]),
                r["elapsed_s"],
                r["ended_at"].isoformat(),
                feedback
            ])

        from flask import Response
        filename = f"{scenario_nom}_rapport_{classe}.csv".replace(" ", "_")
        return Response(
            f.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )




# ─────────── détail historique élèves ─────────────────────────────────
@app.route("/dashboard/eleve/<student_id>")
def dashboard_eleve(student_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    evolution = get_evolution_par_scenario(student_id=student_id)

    with engine.connect() as conn:
        # 💡 On place ici le bloc conn
        students = conn.execute(text(
            "SELECT student_id FROM students ORDER BY student_id"
        )).scalars().all()

        sql = text("""
        SELECT
          e.ordinal        AS exercice,
          s.title          AS serie,
          a.started_at,
          a.ended_at,
          a.elapsed_s,
          a.given_answer,
          a.is_correct
        FROM attempts a
        JOIN exercises e     ON e.exercise_id = a.exercise_id
        JOIN exercise_sets s ON s.set_id      = e.set_id
        WHERE a.student_id = :sid
          AND s.is_active = TRUE
        ORDER BY a.ended_at
        """)
        hist = conn.execute(sql, {"sid": student_id}).mappings().all()

        feedback_row = conn.execute(text("""
            SELECT feedback, created_at
            FROM feedbacks
            WHERE student_id = :sid
            ORDER BY created_at DESC
            LIMIT 1
        """), {"sid": student_id}).mappings().first()

    hist = [dict(r) for r in hist]
    return render_template("dashboard_eleve.html",
                           student_id=student_id,
                           hist=hist,
                           evolution=evolution,
                           students=students,
                           feedback=feedback_row
                           )


# ─────────── drill‑down exercice ──────────────────────────────────────
@app.route("/dashboard/exercice/<int:exo>")
def dashboard_exercice(exo):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    # Récupère les stats par élève pour cet exercice
    sql = text("""
    SELECT
      st.student_id,
      st.class,
      BOOL_OR(a.is_correct)    AS success,
      COUNT(*)                 AS attempts,
      ROUND(AVG(a.elapsed_s),1) AS avg_time,
      MAX(a.ended_at)          AS last_attempt
    FROM attempts a
    JOIN exercises e     ON e.exercise_id = a.exercise_id
    JOIN exercise_sets s ON s.set_id      = e.set_id
    JOIN students st     ON st.student_id = a.student_id
    WHERE s.is_active = TRUE
      AND e.ordinal = :exo
    GROUP BY st.student_id, st.class
    ORDER BY st.class, st.student_id
    """)

    with engine.connect() as conn:
        rows = conn.execute(sql, {"exo": exo}).mappings().all()
    rows = [dict(r) for r in rows]

    return render_template("dashboard_exercice.html",
                           exo=exo,
                           rows=rows
                           )






# ─────────── run ───────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
