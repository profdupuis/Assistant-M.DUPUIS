import os
import hashlib

"""
🔍 Script de Vérification d'Intégrité RGPD - verifieSHA.py

Ce script parcourt tous les sous-dossiers de /export/audit_reports/ et vérifie l'intégrité SHA256
des rapports RGPD et WORM générés automatiquement par l'application.

Fonctionnement :
- Recherche tous les fichiers .sha256.
- Pour chaque fichier trouvé :
    - Relit le fichier cible mentionné.
    - Recalcule le SHA256 réel du fichier.
    - Compare le hash attendu avec le hash recalculé.

Résultat :
- ✅ "Intégrité OK" si le fichier est intact.
- ❌ "ERREUR d'intégrité" si le fichier a été modifié.
- ⚠️ "Fichier manquant" si le fichier mentionné n'existe pas.

Utilisation :
- Double-cliquer sur lancer_verification.bat pour lancer ce script automatiquement.
- Résultats affichés dans une fenêtre PowerShell.

Compatible avec l'organisation suivante :
/export/audit_reports/
    /consentements/
    /integrite_worm/
    /purges/
    /moderations/
    /Deleted_students/
    (et tout autre sous-dossier conforme)
"""

def verifier_sha256(sha_path):
    with open(sha_path, 'r', encoding='utf-8') as f:
        ligne = f.readline().strip()

    parts = ligne.split(maxsplit=1)
    if len(parts) != 2:
        print(f"❌ Format invalide dans {sha_path}")
        return

    expected_hash, target_filename = parts

    full_target_path = os.path.join(os.path.dirname(sha_path), target_filename)

    if not os.path.exists(full_target_path):
        print(f"⚠️ Fichier manquant : {full_target_path}")
        return

    with open(full_target_path, 'rb') as f:
        contenu = f.read()
    actual_hash = hashlib.sha256(contenu).hexdigest()

    if expected_hash == actual_hash:
        print(f"✅ Intégrité OK pour {target_filename}")
    else:
        print(f"❌ ERREUR d'intégrité pour {target_filename}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))

    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith(".sha256"):
                verifier_sha256(os.path.join(root, file))

    input("\nAppuie sur Entrée pour quitter...")
