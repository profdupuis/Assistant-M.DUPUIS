# 🧠 Assistant pédagogique 

Assistant intelligent pour l'entraînement aux équations différentielles du premier ordre, avec suivi individualisé, feedback final IA, export CSV, et tableau de bord enseignant.

![Licence MIT](https://img.shields.io/badge/Licence-MIT-blue)


## 🛡️ Respect du RGPD & modération

- L’assistant utilise l’API OpenAI (GPT-4.1) avec modération automatique des prompts (via l’endpoint `text-moderation-latest`).
- Chaque élève est identifié uniquement par un identifiant pseudonyme (ex : `TSTI2A-84FZ`).
- Les messages sont enregistrés pendant 30 jours maximum, puis purgés automatiquement.
- Les échanges sont exportés toutes les 2 semaines dans un fichier RGPD scellé (WORM).
- Chaque élève peut demander l’effacement de ses données (script dédié + journalisation locale).


## 🌐 Interface élève

Les élèves accèdent simplement à l’adresse `/ia` avec leur identifiant personnel (anonyme, type `TSTI2A-12CL`). L’interface leur propose une fiche interactive avec :

- 📌 Entraînement guidé sur les équations différentielles (fiches scénarisées)
- ✅ Correction automatique et reconnaissance des bonnes réponses
- ⏱️ Analyse du temps de réponse et adaptation du rythme
- 📘 Feedback final généré automatiquement (GPT-4) à la fin de la fiche

---

## 🧑‍🏫 Tableau de bord enseignant (`/dashboard`)

Accessible uniquement via un code enseignant (`?token=XXXXX` ou via authentification admin), le tableau de bord permet de :

### 🔧 Gestion des scénarios

- Activer un scénario pour une classe
- Importer un nouveau scénario au format `.txt`
- Supprimer un scénario (⚠️ icône de sécurité si actif)
- Changer le scénario actif par classe

### 📊 Analyse des performances

- Taux de réussite par exercice
- Temps moyen de résolution
- Nombre de tentatives
- Vue par classe ou par exercice

### 📘 Feedbacks finaux IA

- Générés automatiquement à la fin d’une fiche
- Liste des feedbacks reçus par élève (clic → fiche individuelle)

### 📤 Export des résultats CSV

- Résultats bruts des élèves pour le scénario actif
- Format : `nomScenario_rapport_nomClasse.csv`
- Inclut le feedback final IA (une seule fois par élève)

---

## 📁 Structure du dossier `site/`

site/
│
├── app.py                # Application Flask principale  
├── load_scenario.py      # Programme auxiliaire de chargement (ou manuel) d’un scénario `.txt` depuis n’importe quel chemin
├── .env                  # Variables d'environnement (API, DB, etc.)
├── LICENSE               # Licence MIT
├── README.md             # Description du projet web
│
├── templates/            # Pages HTML Jinja2
│   ├── login.html
│   ├── ia_interface.html
│   ├── dashboard.html
│   ├── dashboard_eleve.html
│   └── dashboard_exercice.html
│
├── static/
│   ├── style.css
│   ├── dashboard.css
│   └── img/
│       └── hydra.png
│├── scenarios/
│   ├── nomclasse-nomfiche.txt
│   └── ...
└── flask_session/        # Session persistante (si utilisée pour admin)
---

## ⚙️ Outils complémentaires (hors `site/`)

À placer dans un dossier `outils/` :

- `models.py` : modèle SQLAlchemy de la base (élèves, tentatives, logs RGPD, scénarios…)
- `resultats.py` : export CSV RGPD par classe et par scénario
- `merge_export_identifiants.py` : reconstruction de rapports nommés (via CSV local)
- `attestation_rgpd.md` : modèle RGPD administratif ou pédagogique
- `Base de données/` :
  - `roles_logger.sql` : création du rôle `logger_bot` sécurisé (RGPD)
  - `export_worm.py` : export sécurisé `.csv + .sha256 + .zip`
  - `purge_old_logs.py` : purge automatique des logs de +30 jours
  - `delete_student_data.py` : suppression immédiate d’un élève (RGPD)




## 🚀 Déploiement

Prévu pour Render ou autre hébergeur Flask (clé OpenAI via `.env`).

---

## 📄 Licence

Ce projet est sous licence **MIT** – voir le fichier `LICENSE`.

---

Développé par **M. DUPUIS** © 2025 – Interface pédagogique innovante
