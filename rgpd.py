import os
import hashlib
import json
from datetime import datetime, timedelta, timezone
from flask import flash, send_file, redirect, url_for, Response, send_from_directory, session, jsonify, request
import csv
from io import StringIO
from sqlalchemy import text
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from utils.session_utils import init_session_context

"""
🔐 Module de Gestion RGPD & WORM - rgpd.py

Ce module gère toutes les opérations critiques RGPD du projet :
- Export et archivage WORM scellé
- Purge des logs anciens et anonymisation des réponses
- Suppression d'élèves RGPD
- Gestion du consentement explicite des élèves
- Vérification de la continuité du chaînage WORM (prev_hash ➔ this_hash)
- Génération systématique de rapports texte horodatés et scellés SHA256
- Organisation rigoureuse des rapports dans /export/audit_reports/

Fonctionnalités principales :
- Génération automatique de fichiers TXT pour chaque action RGPD.
- Ajout du hash SHA256 du contenu directement à la fin du rapport.
- Création automatique de fichier .sha256 pour validation externe.
- Archivage organisé par sous-dossier :
    - consentements/
    - integrite_worm/
    - purges/
    - moderations/
    - Deleted_students/

Objectif :
- Assurer une traçabilité complète et vérifiable des actions sensibles.
- Être conforme aux exigences RGPD, CNIL, et aux standards WORM (Write Once, Read Many).
"""



WORM_EXPORT_DAYS = 7  # Export worm tous les logs de moins de WORM_EXPORT_DAYS jours
PURGE_DAYS = 15



# 📁 Initialisation des dossiers

EXPORT_DIR = "export"
worm_dir = os.path.join(EXPORT_DIR, "worm")
audit_packs_dir = os.path.join(EXPORT_DIR, "audit_packs")
audit_reports_dir = os.path.join(EXPORT_DIR, "audit_reports")
temp_dir = os.path.join(EXPORT_DIR, "temp")

def init_export_directories():
    """
    Vérifie que les sous-dossiers de /export existent et les crée si besoin.
    """
    subfolders = ["worm", "audit_packs", "audit_reports", "temp"]

    for folder in subfolders:
        path = os.path.join(EXPORT_DIR, folder)
        os.makedirs(path, exist_ok=True)


# 🧹 Nettoyage des anciens fichiers

def clean_export_folder():
    """
    Nettoie les fichiers des dossiers export dépassant leur date de conservation.
    """
    now = datetime.now(timezone.utc)
    folders = {
        "worm": 365,
        "audit_packs": 365,
        "audit_reports": 365,
        "temp": 90
    }

    for subfolder, retention_days in folders.items():
        path = os.path.join(EXPORT_DIR, subfolder)
        if not os.path.exists(path):
            continue
        
        cutoff = now - timedelta(days=retention_days)
        for filename in os.listdir(path):
            filepath = os.path.join(path, filename)
            if os.path.isfile(filepath):
                file_mtime = datetime.fromtimestamp(os.path.getmtime(filepath), tz=timezone.utc)
                if file_mtime < cutoff:
                    try:
                        os.remove(filepath)
                    except Exception as e:
                        print(f"Erreur suppression fichier {filepath}: {e}")


def generate_sha256(filepath):
    """
    Génère un fichier .sha256 à partir du fichier donné.
    
    Le fichier SHA256 est créé dans le même dossier que le fichier d'origine,
    avec un contenu au format : [hash]  [nom_fichier]
    """
    sha_path = filepath + ".sha256"
    with open(filepath, "rb") as f:
        contenu = f.read()
    hash_value = hashlib.sha256(contenu).hexdigest()

    with open(sha_path, "w", encoding="utf-8") as f:
        f.write(f"{hash_value}  {os.path.basename(filepath)}\n")


def generate_report_sha256(filename, lines, subfolder=None):
    """
    Génère un rapport texte dans /export/audit_reports/subfolder/ et :
    - Ajoute le hash SHA256 du contenu directement en fin de fichier.
    - Crée aussi un fichier .sha256 associé.

    Paramètres :
    - filename : nom du fichier sans chemin (ex: 'rapport_delete_...')
    - lines : liste des lignes de texte à écrire
    - subfolder : sous-dossier facultatif (ex: 'consentements')

    Retour :
    - Chemin complet du fichier généré
    """
    base_dir = audit_reports_dir # tous les report sont dans ce dossier
    if subfolder:
        base_dir = os.path.join(audit_reports_dir, subfolder)
        os.makedirs(base_dir, exist_ok=True)
        
    report_path = os.path.join(base_dir, filename)

    # Écrire le fichier .txt
    with open(report_path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
            
    # Lire le contenu brut
    with open(report_path, "rb") as f:
        contenu = f.read()
    hash_value = hashlib.sha256(contenu).hexdigest()

    # Réécrire en ajoutant le hash scellé
    with open(report_path, "a", encoding="utf-8") as f:
        f.write("\n---\n")
        f.write(f"Hash SHA256 du contenu du rapport : {hash_value}\n")
        
    # Générer automatiquement le .sha256
    generate_sha256(report_path)

    return report_path



# Conssentement RGPD à la signature (premier login et initialisation du hash)
def handle_consent(engine):
    """
    Gère l'acceptation du consentement RGPD par l'élève lors de la connexion.

    Fonctionnement :
    - Vérifie si l'élève a coché la case de consentement RGPD.
    - Si oui :
        - Enregistre la date du consentement dans la base (`students.rgpd_consent_date`).
        - Génère un premier `last_this_hash` pour initialiser le chaînage RGPD.
        - Enregistre le consentement dans un rapport scellé sha 256 avec le first hash stocké dans /audit_reports/consentements/
        - Met à jour la session avec l'identifiant de l'élève.
        - Redirige vers l'interface IA après consentement.
    - Si non :
        - Vide la session.
        - Redirige vers la page de login.

    Paramètres :
    - engine : SQLAlchemy Engine connecté à la base de données principale.

    Sécurité :
    - Ne modifie rien sans consentement explicite.
    - Nettoie systématiquement la session pour éviter tout contournement.

    Retour :
    - Redirige vers `/ia` si le consentement est validé.
    - Redirige vers `/login` si l'acceptation échoue ou manque.
    """
    sid = session.get("student_id")  # Récupère l'identifiant de l'élève
    consent_given = request.form.get("consent")  # Vérifier si la case de consentement est cochée

    if consent_given and sid:  # Vérifier que l'ID et le consentement sont présents
        try:
            # Si consentement donné, on enregistre la date du consentement
            now = datetime.now(timezone.utc)

            # 🆕 Générer un premier last_this_hash
            first_hash = hashlib.sha256(f"{sid}{now.isoformat()}".encode()).hexdigest()

            with engine.begin() as cn:
                result = cn.execute(text("""
                    UPDATE students
                    SET rgpd_consent_date = :now,
                        last_this_hash = :first_hash
                    WHERE student_id = :sid
                """), {"now": now, "first_hash": first_hash, "sid": sid})
                
            if result.rowcount == 1:
                # generation rapport sha256
                now = datetime.now(timezone.utc)
                now_str = now.strftime("%Y-%m-%d_%H-%M-%S")
                filename = f"rapport_consentement_{sid}_{now_str}.txt"

                lines = [
                    f"Date de consentement : {now.strftime('%Y-%m-%d %H:%M UTC')}",
                    f"Élève : {sid}",
                    f"Premier hash RGPD : {first_hash}"
                ]

                generate_report_sha256(filename, lines,  subfolder="consentements")

                print(f"Consentement RGPD enregistré pour {sid}")
            else:
                print(f"Aucun élève trouvé pour {sid} lors du consentement RGPD")

            # ✅ Préparer la session correctement
            session.clear()
            session["student_id"] = sid
            init_session_context(engine, sid)
            return redirect(url_for("interface_ia"))
        except Exception as e:
            # En cas d'erreur lors de l'enregistrement
            print(f"Erreur lors de l'enregistrement du consentement pour {sid}: {e}")
            return jsonify({"error": "Erreur lors de l'enregistrement. Veuillez réessayer."}), 500
    else:
        # Si le consentement n'est pas donné, déconnexion et retour à la page de login
        session.clear()  # Vider la session pour éviter toute tentative de contournement
        return redirect(url_for("login"))



# 🔍 Vérification intégrité WORM

def verifier_integrite_worm(engine, generate_report=True):
    """
    Vérifie la continuité du chaînage prev_hash / this_hash dans chat_logs.
    Génère un rapport uniquement en cas d'anomalies nouvelles depuis le dernier rapport existant.
    Enregistre un rapport scellé sha 256
    Les rapports sont stockés dans /audit_reports/integrite_worm/
    """
    with engine.connect() as cn:
        logs = cn.execute(text("""
            SELECT user_id, ts, prev_hash, this_hash
            FROM chat_logs
            ORDER  BY user_id ASC, ts ASC     -- 🔑  reset automatique
        """)).mappings().all()

    previous_user = None
    previous_this_hash = None
    anomalies = []

    for log in logs:
        # on change d'élève → on remet les compteurs à zéro
        if log["user_id"] != previous_user:
            previous_user = log["user_id"]
            previous_this_hash = None

        if previous_this_hash and log["prev_hash"] != previous_this_hash:
            anomalies.append((
                log["ts"], log["user_id"],
                previous_this_hash, log["prev_hash"]
            ))

        previous_this_hash = log["this_hash"]

    if anomalies and generate_report:
        # Trouver la date du dernier rapport WORM existant par recherche dans le sous-dossier integrite_worm
        
        integrite_dir = os.path.join(audit_reports_dir, "integrite_worm")
        os.makedirs(integrite_dir, exist_ok=True)  # au cas où le dossier n'existe pas encore
        
        existing_reports = [f for f in os.listdir(integrite_dir) if f.startswith("rapport_integrite_WORM_") and f.endswith(".txt")]
        existing_reports = sorted(existing_reports, reverse=True)

        latest_report_time = None
        if existing_reports:
            latest_report = existing_reports[0]
            try:
                # Extraire la date depuis le nom du fichier et la mettre en UTC
                date_str = latest_report.replace("rapport_integrite_WORM_", "").replace(".txt", "")
                latest_report_time = datetime.strptime(date_str, "%Y-%m-%d_%H-%M-%S").replace(tzinfo=timezone.utc)
            except Exception as e:
                print(f"Erreur lecture date dernier rapport WORM: {e}")

        # Vérifier si une des anomalies est plus récente que le dernier rapport
        need_new_report = True
        if latest_report_time:
            need_new_report = any(anomaly[0] > latest_report_time for anomaly in anomalies)

        if need_new_report:
            now_utc = datetime.now(timezone.utc)
            now_str = now_utc.strftime("%Y-%m-%d_%H-%M-%S")
            
            filename = f"rapport_integrite_WORM_{now_str}.txt"

            # ✨ Utiliser directement generate_report_sha256
            lines = [
                f"Date de vérification : {now_utc.strftime('%d/%m/%Y à %H:%M UTC')}",
                f"Nombre d'anomalies détectées : {len(anomalies)}",
                ""
            ]
            for ts, uid, prev_exp, prev_found in anomalies:
                lines.append(
                    f"[{ts}] élève={uid} – prev attendu={prev_exp} – prev trouvé={prev_found}"
                )

            generate_report_sha256(filename, lines, "integrite_worm")
    return False if need_new_report else True


        
# 🗑️ Suppression élève RGPD

def anonymiser_logs_student(engine_log, student_id):
    """
    Anonymise tous les logs de chat_logs liés à un élève (RGPD - WORM safe).

    Moteur utilisé : engine_log (rôle app_log avec UPDATE(user_id)).
    """
    with engine_log.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE chat_logs
                SET user_id = 'ANONYMISED'
                WHERE user_id = :sid
            """), {"sid": student_id}
        )
    return result.rowcount  # nombre de lignes anonymisées


def delete_student_record(engine, student_id):
    """
    Supprime un élève de la base students.

    Moteur utilisé : engine (rôle principal).
    """
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                DELETE FROM students
                WHERE student_id = :sid
            """), {"sid": student_id}
        )
    return result.rowcount

    
def delete_student(engine, engine_log,student_id):
    """
    Supprime l'élève et ses données associées pour respect du RGPD.

    - Anonymise les logs liés dans chat_logs.
    - Supprime l'entrée correspondante dans students.
    - Génère un rapport scellé SHA256 dans /audit_reports/Deleted_students/

    Paramètres :
    - engine : moteur principal (exercices, students)
    - engine_log : moteur logs sécurisé (chat_logs)
    - student_id : identifiant de l'élève
    """

    try:

        # Anonymiser les logs

        # 🛡️ RGPD x WORM : anonymisation au lieu de suppression des logs
        #
        # Lors de la suppression d'un élève, nous ne supprimons pas les anciens logs de chat_logs
        # afin de respecter le principe WORM (Write Once, Read Many) : aucun effacement, aucune altération historique.
        #
        # Pour respecter le RGPD (droit à l'effacement), nous anonymisons le champ user_id
        # en le passant à 'ANONYMISED' . Cela coupe tout lien identifiable entre l'élève et ses anciens messages,
        # tout en maintenant l'intégrité de la chaîne prev_hash / this_hash.
        #
        # Ce choix garantit :
        # - La conformité RGPD (plus de données personnelles stockées après suppression de l'élève)
        # - Le respect de la continuité WORM (pas de rupture du chaînage historique)
        #
        # Remarque : aucune modification n'est faite sur les champs utilisés pour calculer les hash,
        # donc l'intégrité du scellage est strictement préservée.


        nb_anonymised = anonymiser_logs_student(engine_log, student_id)
        nb_deleted = delete_student_record(engine, student_id)
            
        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        
        filename = f"rapport_delete_{student_id}_{now_str}.txt"

        lines = [
            f"Date de suppression : {now.strftime('%Y-%m-%d %H:%M UTC')}",
            f"Élève : {student_id}",
            f"Nombre de logs anonymisés : {nb_anonymised}",
            f"Suppression de la fiche élève : {'Oui' if nb_deleted > 0 else 'Non (inexistant)'}"
        ]
        # Générer le rapport scellé SHA256
        generate_report_sha256(filename, lines, "Deleted_students")
        
        if nb_deleted > 0:
            flash(f"✅ Élève {student_id} supprimé avec succès. {nb_anonymised} logs anonymisés.", "success")
        else:
            flash(f"❌ Aucun élève trouvé avec cet identifiant.", "error")

    except Exception as e:
        print(e)
        flash(f"❌ Erreur lors de la suppression de l'élève : {e}", "error")

    return redirect(url_for('dashboard_rgpd'))

# 📥 Export dernier WORM
def export_worm(engine):
    """
    Déclenche l'export des logs WORM des 7 derniers jours sous forme d'archive sécurisée (.zip).

    Fonctionnement :
    - Vérifie que l'utilisateur est connecté en tant qu'administrateur.
    - Appelle la fonction `export_worm(engine)` (définie dans rgpd.py).
    - Génère automatiquement :
        - Un fichier CSV des logs récents (7 jours).
        - Un fichier SHA256 associé pour vérification d'intégrité.
        - Un fichier ZIP regroupant les deux fichiers précédents.
    - Insère un enregistrement dans la table `worm_exports` (historique des exports WORM).
    - Envoie un message flash pour informer du succès ou de l'échec de l'opération.

    Sécurité :
    - L'accès est protégé par `@login_required_admin` pour éviter toute exportation non autorisée.

    Retour :
    - Redirige l'administrateur vers le tableau de bord RGPD après l'export.

    Utilité :
    - Permet d'assurer la conservation à moyen terme des logs dans un format conforme RGPD (WORM : Write Once, Read Many).
    - Facilite les contrôles et audits en créant des archives chaînées et vérifiables.

    Remarques :
    - Seuls les échanges des 7 derniers jours sont inclus dans chaque export (paramètre configurable via WORM_EXPORT_DAYS).
    - Les fichiers sont stockés dans le dossier `/export/worm/` du serveur.
    """
    try:
        now = datetime.now(timezone.utc).date()
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        csv_file = f"chatlogs_worm_{timestamp}.csv"
        sha_file = csv_file + ".sha256"
        zip_file = f"chatlogs_worm_{timestamp}.zip"

        csv_path = os.path.join(worm_dir, csv_file)
        sha_path = os.path.join(worm_dir, sha_file)
        zip_path = os.path.join(worm_dir, zip_file)
        
        interval_days = f"{WORM_EXPORT_DAYS} days"
        
        query = text(f"""
        SELECT id, ts, user_id, prompt, completion, flags, model, prev_hash, this_hash
        FROM chat_logs
        WHERE ts >= (now() - interval '{interval_days}')
        ORDER BY ts ASC
        """)

        

        with engine.connect() as conn, open(csv_path, "w", newline='', encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "ts", "user_id", "prompt", "completion", "flags", "model", "prev_hash", "this_hash"])
            rows = list(conn.execute(query))
            for row in rows:
                writer.writerow(row)

        # SHA256
        with open(csv_path, "rb") as f:
            sha256 = hashlib.sha256(f.read()).hexdigest()
        with open(sha_path, "w") as f:
            f.write(f"{sha256}  {csv_file}\n")

        # ZIP
        with ZipFile(zip_path, "w") as z:
            z.write(csv_path, arcname=csv_file)
            z.write(sha_path, arcname=sha_file)

        # Insérer dans worm_exports avec filename
        with engine.begin() as cn:
            cn.execute(text("""
                INSERT INTO worm_exports (nb_logs, size_bytes, filename)
                VALUES (:nb, :sz, :fn)
            """), {
                "nb": len(rows),
                "sz": os.path.getsize(zip_path),
                "fn": zip_file
            })
        print("ok")
        flash(f"✅ Export WORM réussi : {len(rows)} logs exportés.", "success")
    except Exception as e:
        flash(f"❌ Erreur lors de l'export WORM : {e}", "error")
        print("error")

    return redirect(url_for('dashboard_rgpd'))


# 📥 Télécharger dernier WORM

def download_latest_worm():
    """
    Permet de télécharger le dernier fichier WORM généré (archive ZIP).

    - Vérifie que l'utilisateur est connecté en tant qu'administrateur.
    - Vérifie que le fichier ZIP existe et contient au moins un fichier valide.
    - Si le fichier est valide, le propose en téléchargement.
    - Sinon, affiche un message flash d'erreur approprié.
    - Redirige vers le dashboard RGPD en cas d'erreur.

    Méthode protégée par la session admin.
    """
    worm_files = [f for f in os.listdir(worm_dir) if f.startswith("chatlogs_worm_") and f.endswith(".zip")]

    if not worm_files:
        flash(f"❌ Aucun fichier WORM disponible.", "error")
        return redirect(url_for('dashboard_rgpd'))

    worm_files = sorted(worm_files, key=lambda x: os.path.getmtime(os.path.join(worm_dir, x)), reverse=True)
    filename = worm_files[0]
    file_path = os.path.join(worm_dir, filename)


    # Vérification 1 : fichier existe
    if not os.path.isfile(file_path):
        flash(f"❌ Aucun fichier WORM trouvé pour aujourd'hui ({filename}).", "error")
        return redirect(url_for('dashboard_rgpd'))

    # Vérification 2 : fichier lisible et non vide structurellement
    try:
        with ZipFile(file_path, 'r') as zipf:
            if len(zipf.namelist()) == 0:
                flash(f"❌ Le fichier WORM est vide ou corrompu ({filename}).", "error")
                return redirect(url_for('dashboard_rgpd'))
    except Exception as e:
        flash(f"❌ Erreur lors de l'ouverture du fichier ZIP : {e}", "error")
        return redirect(url_for('dashboard_rgpd'))

    # OK -> Téléchargement
    return send_from_directory(worm_dir, filename, as_attachment=True)

# 📥 Télécharger un WORM spécifique

def download_worm(filename):
    """
    Permet de télécharger un fichier WORM historique spécifique.

    - Vérifie que l'utilisateur est connecté en tant qu'administrateur.
    - Cherche le fichier ZIP dans le dossier 'export/worm'.
    - Si le fichier existe, l'envoie en téléchargement au client.
    - Si le fichier est introuvable, affiche un message flash d'erreur et redirige vers le dashboard RGPD.

    Cette route sécurise l'accès aux fichiers archivés WORM par leur nom unique.
    """

    file_path = os.path.join(worm_dir, filename)

    if not os.path.isfile(file_path):
        flash(f"❌ Fichier {filename} introuvable.", "error")
        return redirect(url_for('dashboard_rgpd'))

    try:
        with ZipFile(file_path, 'r') as zipf:
            if len(zipf.namelist()) == 0:
                flash(f"❌ Le fichier WORM est vide ou corrompu ({filename}).", "error")
                return redirect(url_for('dashboard_rgpd'))
    except Exception as e:
        flash(f"❌ Erreur lors de l'ouverture du fichier ZIP ({filename}) : {e}", "error")
        return redirect(url_for('dashboard_rgpd'))

    return send_from_directory(worm_dir, filename, as_attachment=True)


# 📤 Export flags graves

def export_flags_graves(engine):
    """
    Exporte les échanges détectés comme critiques (self-harm) en fichier CSV.

    - Sélectionne tous les logs de la table `chat_logs`
      où un problème de type `self-harm` ou `self-harm/intent` a été détecté.
    - Génère un fichier CSV avec les colonnes :
      Date de l'échange, Identifiant de l'élève, Prompt envoyé, Problèmes détectés.
    - Renvoie le fichier en téléchargement direct avec le nom `flags_graves.csv`.
    - Enregistre un rapport scellé sha 256 stocké dans /audit_reports/moderations/
    
    Sécurité :
    - Route protégée par @login_required_admin pour éviter tout accès non autorisé.

    Utilité :
    - Permet au responsable de la plateforme de conserver une trace
      des incidents critiques détectés pour audit ou suivi RGPD.
    """

    with engine.connect() as cn:
        results = cn.execute(text("""
            SELECT ts, user_id, prompt, flags
            FROM chat_logs
            WHERE (flags->>'self-harm' = 'true' OR flags->>'self-harm/intent' = 'true')
            ORDER BY ts DESC
        """)).mappings().all()

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["Date", "Élève", "Prompt", "Flags détectés"])
    for record in results:
        writer.writerow([
            record['ts'].strftime('%d/%m/%Y %H:%M'),
            record['user_id'],
            record['prompt'],
            ', '.join([k for k, v in (record['flags'] or {}).items() if v])
        ])
        
        
    now = datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"rapport_flags_graves_{now_str}.txt"

    lines = [
        f"Date de génération : {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"Nombre d'incidents critiques détectés : {len(results)}"
    ]

    generate_report_sha256(filename, lines, "moderations")
    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=flags_graves.csv"}
    )

# 🧹 Purge des vieux logs
def purge_old_logs(engine):
    """    
    Purge partielle des données RGPD :

    - Anonymise les anciens logs de chat_logs (> PURGE_DAYS).
    - Supprime les réponses données par les élèves dans attempts (> PURGE_DAYS).
    - Ne supprime rien de WORM (respect de l'intégrité chaînée).
    - Génère un rapport SHA256 dans /audit_reports/purges/
    """
    try:
        now = datetime.now(timezone.utc)

        with engine.begin() as conn:
            # ✅ Anonymiser user_id des vieux logs WORM (> PURGE_DAYS)
            anonymized_logs = conn.execute(text(f"""
                UPDATE chat_logs
                SET user_id = 'ANONYMISED'
                WHERE ts < now() - interval '{PURGE_DAYS} days'
                AND user_id IS NOT NULL
            """))

            # ✅ Anonymiser les réponses dans attempts
            cleared = conn.execute(text(f"""
                UPDATE attempts
                SET given_answer = NULL
                WHERE ended_at < now() - interval '{PURGE_DAYS} days'
            """))

            # ✅ Enregistrer dans logs_purges
            conn.execute(text("""
                INSERT INTO logs_purges (nb_logs_deleted, nb_attempts_anonymized)
                VALUES (:logs, :ans)
            """), {
                "logs": anonymized_logs.rowcount,
                "ans": cleared.rowcount
            })

        now_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"rapport_purge_{now_str}.txt"

        lines = [
            f"Date de la purge : {now.strftime('%Y-%m-%d %H:%M UTC')}",
            f"Nombre de logs anonymisés : {anonymized_logs.rowcount}",
            f"Nombre d'attempts anonymisés : {cleared.rowcount}"
        ]

        generate_report_sha256(filename, lines, "purges")        

        flash(f"✅ Purge terminée : {anonymized_logs.rowcount} logs anonymisés, {cleared.rowcount} réponses anonymisées.", "success")

    except Exception as e:
        flash(f"❌ Erreur lors de la purge : {e}", "error")

    return redirect(url_for('dashboard_rgpd'))

# 🧹 Purge des vieux logs
def purge_old_logsv2(engine):
    """
    Purge les anciennes données de la base de données.

    - Vérifie que l'utilisateur est connecté en tant qu'administrateur.
    - Supprime les logs de chat datant de plus de PURGE_DAYS jours.
    - Anonymise également les réponses des tentatives d'exercices vieilles de plus de PURGE_DAYS jours.
    - Enregistre un rapport scellé sha 256 stocké dans /audit_reports/purges/
    - Affiche un message flash indiquant le nombre de suppressions/anonymisations effectuées.
    - Redirige ensuite vers le dashboard RGPD.

    Méthode protégée par la session admin.
    """
    try:
        now = datetime.now(timezone.utc)

        with engine.begin() as conn:
            deleted_logs = conn.execute(text(f"""
                DELETE FROM chat_logs
                WHERE ts < now() - interval '{PURGE_DAYS} days'
            """))

            cleared = conn.execute(text(f"""
                UPDATE attempts
                SET given_answer = NULL
                WHERE ended_at < now() - interval '{PURGE_DAYS} days'
            """))

            # Enregistrement dans logs_purges
            conn.execute(text("""
                INSERT INTO logs_purges (nb_logs_deleted, nb_attempts_anonymized)
                VALUES (:logs, :ans)
            """), {"logs": deleted_logs.rowcount, "ans": cleared.rowcount})

        now_str = now.strftime("%Y-%m-%d_%H-%M-%S")
        
        filename = f"rapport_purge_{now_str}.txt"

        lines = [
            f"Date de la purge : {now.strftime('%Y-%m-%d %H:%M UTC')}",
            f"Nombre de logs supprimés : {deleted_logs.rowcount}",
            f"Nombre d'attempts anonymisés : {cleared.rowcount}"
        ]

        generate_report_sha256(filename, lines, "purges")        
        
        flash(f"✅ Purge terminée : {deleted_logs.rowcount} logs supprimés, {cleared.rowcount} réponses anonymisées.", "success")
    except Exception as e:
        flash(f"❌ Erreur lors de la purge : {e}", "error")

    return redirect(url_for('dashboard_rgpd'))




# 📤 Export audits

def prepare_audit(engine):
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
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    zip_filename = f"audit_pack_{now}.zip"

    memory_file = BytesIO()

    if not os.path.exists(worm_dir):
        flash("❌ Aucun dossier d'exports WORM trouvé.", "error")
        return redirect(url_for('dashboard_rgpd'))

    worm_files = [f for f in os.listdir(worm_dir) if f.startswith("chatlogs_worm_") and f.endswith(".zip")]
    if not worm_files:
        flash("❌ Aucun fichier WORM disponible pour générer l'audit.", "error")
        return redirect(url_for('dashboard_rgpd'))

    with ZipFile(memory_file, 'w', ZIP_DEFLATED) as zipf:
        # Ajouter le dernier fichier WORM
        worm_files = sorted(worm_files, key=lambda x: os.path.getmtime(os.path.join(worm_dir, x)), reverse=True)
        latest_worm = worm_files[0]
        zipf.write(os.path.join(worm_dir, latest_worm), arcname=latest_worm)

        # Générer flags_graves.csv
        with engine.connect() as cn:
            results = cn.execute(text("""
                SELECT ts, user_id, prompt, flags
                FROM chat_logs
                WHERE (flags->>'self-harm' = 'true' OR flags->>'self-harm/intent' = 'true')
                ORDER BY ts DESC
            """)).mappings().all()

        si = StringIO()
        writer = csv.writer(si)
        writer.writerow(["Date", "Élève", "Prompt", "Problèmes détectés"])
        for record in results:
            detected_flags = [k for k, v in (record['flags'] or {}).items() if v]
            writer.writerow([
                record['ts'].strftime('%d/%m/%Y %H:%M'),
                record['user_id'],
                record['prompt'],
                ", ".join(detected_flags)
            ])
        content = si.getvalue()
        zipf.writestr("flags_graves.csv", content)

        # 🔥 Nouveau ➔ Vérifier si seulement l'en-tête
        nb_lignes = content.count('\n')
        if nb_lignes <= 1:
            flash("✅ Aucun incident grave détecté (aucun flag self-harm trouvé).", "info")

        # Ajouter audit_purge_info.txt
        with engine.connect() as cn:
            last_purge = cn.execute(text("""
                SELECT purge_date
                FROM logs_purges
                ORDER BY purge_date DESC
                LIMIT 1
            """)).scalar()
        if not last_purge:
            flash("⚠️ Attention : aucune purge RGPD n'a encore été réalisée.", "warning")
        purge_info = "Aucune purge trouvée." if not last_purge else f"Dernière purge RGPD effectuée le {last_purge.strftime('%d/%m/%Y à %H:%M')}."
        purge_info += f"\nPack généré le {datetime.now(timezone.utc).strftime('%d/%m/%Y à %H:%M')}."
        zipf.writestr("audit_purge_info.txt", purge_info)

    memory_file.seek(0)
    
    # 🔥 NOUVEAU : Enregistrer une copie du pack dans /export/audit_packs/
    audit_pack_path = os.path.join(audit_packs_dir, zip_filename)
    with open(audit_pack_path, "wb") as f:
        f.write(memory_file.getbuffer())
    
    # ✅ Tu pourrais même générer un .sha256 à côté si tu veux...
    generate_sha256(audit_pack_path)

    flash("✅ Audit RGPD généré avec succès.", "success")

    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=zip_filename
    )
