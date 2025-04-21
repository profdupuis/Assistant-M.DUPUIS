import os, re, json, time, pathlib
from flask import Flask, render_template, request, redirect, url_for, jsonify, session
from flask_session import Session
from markupsafe import Markup
from openai import OpenAI
from sqlalchemy import create_engine, text
from sqlalchemy.exc import NoResultFound
from dotenv import load_dotenv

# ─────────── init ────────────────────────────────────────────────────
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev")
app.config.update(SESSION_PERMANENT=False, SESSION_TYPE="filesystem")
Session(app)

engine = create_engine(os.getenv("DATABASE_URL"), future=True)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

INIT_PROMPT   = pathlib.Path("scenarios/initial_prompt.txt")
SCENARIO_TXT  = pathlib.Path("scenarios/scenario.txt")
MAP_JSON      = json.loads(pathlib.Path("scenarios/serie_active.json")
                           .read_text(encoding="utf-8"))
ANS_JSON      = json.loads(pathlib.Path("scenarios/answers_active.json")
                           .read_text(encoding="utf-8"))

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

# ─────────── page IA (intro + exo 1) ────────────────────────────────
@app.route("/ia")
def interface_ia():
    if "student_id" not in session:
        return redirect(url_for("login"))

    html = Markup("<br>".join(INIT_PROMPT.read_text(encoding="utf-8").splitlines()))

    with engine.connect() as cn:
        exo = exo_row(cn, 1)

    session.update(
        exo_courant=1,
        exo_id     = exo["exercise_id"],
        start      = time.time()
    )
    return render_template("ia_interface.html", initial_message=html)

# ─────────── scénario complet envoyé à GPT ──────────────────────────
def scenario_prompt() -> str:
    return SCENARIO_TXT.read_text(encoding="utf-8")

# ─────────── API conversation ───────────────────────────────────────
@app.route("/api/message", methods=["POST"])
def api_message():
    if "student_id" not in session:
        return jsonify({"reply": "Session expirée, reconnecte‑toi."})

    user_msg = request.json.get("message", "")

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

        next_ref   = f"EDiff_exo_{session['exo_courant']}"
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

    # appel GPT
    ai = client.chat.completions.create(
        model="gpt-4.1",
        messages=session["history"],
        user=session["student_id"]
    )
    reply = ai.choices[0].message.content
    session["history"].append({"role": "assistant", "content": reply})

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
            step = 2 if elapsed < 120 else 1
            session["exo_courant"] += step
            next_ref = f"EDiff_exo_{session['exo_courant']}"

            if next_ref in MAP_JSON:
                session["start"] = time.time()
                with engine.connect() as cn:
                    exo = exo_row(cn, session["exo_courant"])
                session["exo_id"] = exo["exercise_id"]

                badge = "⏩" if step == 2 else "➡️"
                reply += (f"\n\n{badge} Passage à l’exercice {session['exo_courant']} "
                          f"(réponse en {elapsed}s)\n\n---\n{MAP_JSON[next_ref]}")
            else:
                reply += "\n\n🎉 Entraînement terminé."

    # renvoi : réponse GPT + éventuel énoncé demandé
    return jsonify({"reply": reply + nav_enonce})

# ─────────── reset session ─────────────────────────────────────────
@app.route("/reset")
def reset():
    session.clear()
    return redirect(url_for("login"))

# ─────────── run ───────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
