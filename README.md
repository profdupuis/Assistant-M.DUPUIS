# ARGOS – Plate‑forme d’exercices sur les équations différentielles

Assistant pédagogique basé sur GPT‑4 ; back‑end Flask + PostgreSQL.

---

## 1. Prérequis

| Outil | Version conseillée |
|-------|--------------------|
| Python | ≥ 3.10 |
| PostgreSQL | 15 + (Neon ou local) |
| Git | – |
| OpenAI API key | GPT‑4.1 |
| *(facultatif)* Poetry | – |

---

## 2. Installation rapide

```bash
git clone https://github.com/mon‑org/argos-diffeq.git
cd argos-diffeq
python -m venv .venv && source .venv/bin/activate   # Win : .venv\Scripts\activate
pip install -r requirements.txt


---
Créer .env :
DATABASE_URL=postgresql+psycopg2://user:pass@host:port/db
OPENAI_API_KEY=sk-•••
FLASK_SECRET_KEY=change‑me

## 3. Préparer la base
psql "$DATABASE_URL" -f sql/schema.sql
python tools/import_students.py data/identifiants.csv   # CSV: student_id,class

## 4. Charger la fiche d’exercices
# Modifier si besoin scenarios/scenario.txt puis :
python load_scenario.py

(Active / remplit exercises et régénère
initial_prompt.txt, serie_active.json, answers_active.json.)


## 5. Lancer l’application
python app.py 


## 6. Fonctionnement

ARGOS écrit EXERCICE TERMINE : ✅ → tentative enregistrée, skip si < 2 min.

Commande exercice N → affichage direct de l’énoncé N.


## Arborescence clé

.
├─ app.py                  # serveur Flask
├─ load_scenario.py        # import fiche
├─ scenarios/
│   ├─ scenario.txt        # ⭐ prompt maître
│   ├─ initial_prompt.txt  # intro + exo1 (auto)
│   ├─ serie_active.json   # ref→énoncé   (auto)
│   └─ answers_active.json # ref→réponse  (auto)
├─ tools/import_students.py
├─ sql/schema.sql
└─ data/identifiants.csv

