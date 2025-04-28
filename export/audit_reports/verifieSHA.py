import os
import hashlib

def verifier_sha256(sha_file):
    with open(sha_file, 'r', encoding='utf-8') as f:
        ligne = f.readline().strip()
    expected_hash, filename = ligne.split(maxsplit=1)

    if not os.path.exists(filename):
        print(f"⚠️ Fichier manquant : {filename}")
        return

    with open(filename, 'rb') as f:
        contenu = f.read()
    actual_hash = hashlib.sha256(contenu).hexdigest()

    if expected_hash == actual_hash:
        print(f"✅ Intégrité OK pour {filename}")
    else:
        print(f"❌ ERREUR d'intégrité pour {filename}")

if __name__ == "__main__":
    dossier = os.path.dirname(os.path.abspath(__file__))
    fichiers_sha = [f for f in os.listdir(dossier) if f.endswith(".sha256")]

    if not fichiers_sha:
        print("❌ Aucun fichier .sha256 trouvé.")
    else:
        for sha_file in fichiers_sha:
            verifier_sha256(os.path.join(dossier, sha_file))

    input("\nAppuie sur Entrée pour quitter...")
