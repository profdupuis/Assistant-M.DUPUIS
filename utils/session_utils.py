from flask import session
from sqlalchemy import text
import re

import os
import shutil
from flask import current_app



def clean_temp_folder():
    """
    Nettoie automatiquement les fichiers temporaires LaTeX (.aux, .log, .out, .toc, etc.)
    dans le dossier temporaire système.
    Logge dans app.logger.info() chaque fichier supprimé.
    """
    if not current_app:
        return  # Sécurité : ne fait rien si pas dans un contexte Flask

    temp_dir = os.getenv('TEMP') or '/tmp'
    extensions = ('.aux', '.log', '.out', '.toc', '.synctex.gz', '.tmp')

    freed_size = 0
    for root, dirs, files in os.walk(temp_dir):
        for file in files:
            if file.endswith(extensions):
                file_path = os.path.join(root, file)
                try:
                    size = os.path.getsize(file_path)
                    os.remove(file_path)
                    current_app.logger.info(f"🧹 Temp nettoyé : {file_path} ({size/1024:.2f} Ko)")
                    freed_size += size
                except Exception as e:
                    current_app.logger.warning(f"⚠️ Impossible de supprimer {file_path} : {e}")

    current_app.logger.info(f"✨ Espace libéré : {freed_size/1024/1024:.2f} Mo")



def extract_niveau(prompt: str) -> int:
    m = re.search(r'\[niveau\s*(\d+)\]', prompt, re.IGNORECASE)
    return int(m.group(1)) if m else 1

def clean_prompt(prompt: str) -> str:
    lines = prompt.splitlines()
    lines = [line for line in lines if not re.search(r'\[niveau\s*\d+\]', line, re.IGNORECASE)]
    lines = [line for line in lines if not re.match(r'^exo_\d+', line.strip(), re.IGNORECASE)]
    return "\n".join(lines).strip()


def has_feedback(engine, student_id: str, scenario_id=None) -> bool:
    """
    Vérifie si l'élève a déjà reçu un feedback final pour le scénario actif.
    Retourne True si oui, False sinon.
    """
    if scenario_id is None:
        scenario_id = session.get("active_scenario_id")
    with engine.connect() as cn:
        feedback = cn.scalar(text("""
            SELECT 1
            FROM feedbacks
            WHERE student_id = :sid
              AND scenario_id = :scid
            LIMIT 1
        """), {"sid": student_id, "scid": scenario_id})

    return bool(feedback)


def load_json_from_db(engine, class_name: str, scenario_id: str = None):
    """
    Charge depuis la base les exercices :
    - Soit du scénario actif de la classe (par défaut),
    - Soit d'un scénario spécifique si scenario_id est fourni.
    
    Retourne trois dictionnaires : 
    - map_json (énoncés),
    - ans_json (réponses attendues),
    - cat_json (catégories).
    """
    map_json, ans_json, cat_json = {}, {}, {}
    with engine.connect() as cn:
        if scenario_id:
            # 🔥 Chargement par ID scénario spécifique
            rows = cn.execute(text("""
                SELECT e.ordinal, e.prompt, e.answer, c.name AS category
                FROM exercises e
                JOIN exercise_sets s ON s.set_id = e.set_id
                JOIN scenarios sc ON sc.id = s.scenario_id
                LEFT JOIN categories c ON c.category_id = e.category_id
                WHERE sc.id = :scid
                ORDER BY e.ordinal
            """), {"scid": scenario_id}).mappings().all()
        else:
            # 🔥 Chargement normal par classe (actuel par défaut)
            rows = cn.execute(text("""
                SELECT e.ordinal, e.prompt, e.answer, c.name AS category
                FROM exercises e
                JOIN exercise_sets s ON s.set_id = e.set_id
                JOIN scenarios sc ON sc.id = s.scenario_id
                LEFT JOIN categories c ON c.category_id = e.category_id
                WHERE s.is_active = true
                  AND sc.class_name = :cls
                ORDER BY e.ordinal
            """), {"cls": class_name}).mappings().all()

    for row in rows:
        ref = f"exo_{row['ordinal']}"
        map_json[ref] = f"🧩 EXERCICE {row['ordinal']} [niveau {extract_niveau(row['prompt'])}]\n\n{clean_prompt(row['prompt'])}"
        ans_json[ref] = row["answer"]
        cat_json[ref] = row["category"] or "Sans catégorie"

    return map_json, ans_json, cat_json


def load_done_refs(engine, student_id: str, scenario_id=None) -> list[str]:
    """
    Charge la liste des références d'exercices déjà validés (refs) pour un élève et un scénario donné.
    Retourne une liste de strings : ['exo_1', 'exo_2', ...]
    """
    if scenario_id is None:
        scenario_id = session.get("active_scenario_id")

    with engine.connect() as cn:
        row = cn.execute(text("""
            SELECT refs
            FROM done_refs
            WHERE student_id = :sid
              AND scenario_id = :scid
            LIMIT 1
        """), {"sid": student_id, "scid": scenario_id}).mappings().first()

    return row["refs"] if row else []
    
    
def get_last_hash(engine, student_id: str) -> str:
    """
    Récupère le dernier this_hash associé à l'élève depuis la table students.
    Retourne '0' * 64 si jamais il n'est pas encore défini.
    """
    with engine.connect() as cn:
        last_hash = cn.scalar(text("""
            SELECT last_this_hash
            FROM students
            WHERE student_id = :sid
        """), {"sid": student_id})

    return last_hash or "0" * 64

def get_active_scenario_id_for_class(engine, class_name):
    """
    Récupère le scénario actif de la classe.
    Si aucun scénario actif n'est trouvé, essaie de charger le dernier existant.
    Si aucun scénario du tout, retourne None.
    """
    with engine.connect() as cn:
        result = cn.scalar(text("""
            SELECT id
            FROM scenarios
            WHERE class_name = :cls
              AND is_active = true
            LIMIT 1
        """), {"cls": class_name})

        if result:
            return result

        # Aucun scénario actif trouvé, chercher n'importe quel scénario existant
        result = cn.scalar(text("""
            SELECT id
            FROM scenarios
            WHERE class_name = :cls
            ORDER BY id DESC
            LIMIT 1
        """), {"cls": class_name})

        return result  # Peut être None si aucun scénario du tout



def init_session_context(engine,student_id: str):
    """
    Initialise toutes les variables de session nécessaires pour l'élève :
    - MAP_JSON : énoncés
    - ANS_JSON : réponses attendues
    - CAT_JSON : catégories
    - exo_valide : exos déjà réussis
    - has_feedback : feedback final existant ou non
    - last_this_hash : dernier hash enregistré pour assurer le chaînage WORM
    """
    class_name = student_id.split("-")[0]
    session["class_name"] = class_name
    
    # Récupérer le scénario actif de la classe
    scenario_id = get_active_scenario_id_for_class(engine, class_name)

    if scenario_id is None:
        flash("❌ Erreur : Aucun scénario disponible pour cette classe.", "error")
        return redirect(url_for("login"))  # ou raise une Exception RGPD ?
    
    session["active_scenario_id"] = scenario_id
    session["cconv"] = []

    # ─── récupérer la matière du scénario actif ───────────────────────
    with engine.connect() as cn:
        matiere = cn.scalar(text(
            "SELECT matiere FROM scenarios WHERE id = :sid"
        ), {"sid": scenario_id})

    session["active_matiere"] = (
        matiere if matiere in ("MATHS", "SVT", "NSI") else ""
    )
        
    # Charger tous les exercices du scénario actif
    map_json, ans_json, cat_json = load_json_from_db(engine, class_name, scenario_id)
    

    
    # ─── charger les exercices du scénario ─────────────────────────────
    if not map_json:
        flash("❌ Erreur : Aucun exercice trouvé dans ce scénario.", "error")
        return redirect(url_for("login"))

    done_refs = load_done_refs(engine,student_id,scenario_id)
    feedback_exists = has_feedback(engine,student_id,scenario_id)
    last_hash = get_last_hash(engine, student_id)
    
    
    # ─── stocker en session ────────────────────────────────────────────
    session.update(
        MAP_JSON = map_json,
        ANS_JSON = ans_json,
        CAT_JSON = cat_json,
        active_scenario_id = scenario_id,   # ← ajouté
        last_this_hash = last_hash,
        exo_valide = done_refs,
        has_feedback = feedback_exists,
    )



