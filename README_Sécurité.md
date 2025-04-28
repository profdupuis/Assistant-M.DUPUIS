# 🛡️ Fiche de sécurité – Assistant IA

Ce document présente les mesures de sécurité mises en place dans le projet **Assistant IA**, en conformité avec les recommandations de la CNIL et les référentiels ANSSI.

---

## 🧠 1. Finalité du traitement

- Application pédagogique interactive destinée à des élèves.
- Génération d’exercices, validation de réponses et suivi de progression.
- Aucune donnée personnelle directement identifiable n’est stockée.

---

## 🔐 2. Données traitées

| Type de donnée          | Exemple / Format     | Statut RGPD |
|-------------------------|----------------------|-------------|
| Identifiant élève       | `TSTI2A-4FZ1` (anonyme, aléatoire) | ✅ Pseudonymisé |
| Historique d’exercice   | Tentatives, temps, réponses | ✅ Traçable, non personnel |
| Logs de sécurité        | Tentatives de connexion, violations CSP | ✅ Conformité log minimale |

> 💡 Les identifiants élèves ne permettent pas une identification directe. Aucun nom, prénom, IP ou email n’est enregistré.

---

## 🧱 3. Mesures de sécurité techniques

### 3.1 Content Security Policy (CSP)

- ✅ Politique **stricte par défaut** sur toutes les pages
- ✅ Exception uniquement pour `/ia` (MathJax)
- ✅ Reporting actif (`/csp-report` + `Report-To`)
- ✅ Bloque `script-inline`, `eval`, styles inline sauf `/ia`

### 3.2 Authentification

- ✅ Identifiant unique aléatoire
- ✅ Pas de mot de passe
- ✅ Logs de tentative de connexion échouée (`app.logger.warning`)

### 3.3 Fichiers & contenu

- ❌ Aucun téléchargement utilisateur
- ❌ Aucune donnée saisie libre non filtrée
- ✅ Filtrage rigoureux (`.strip().upper()`)

---

## 🕵️ 4. Journalisation

- Tentatives de connexion échouées
- Violations de politique CSP (header `report-uri`)
- Logs visibles dans la console serveur ou Render

---

## ⚖️ 5. Conformité RGPD

- ✅ Pas de données personnelles traitées directement
- ✅ Données pseudonymisées dès la création (identifiants aléatoires)
- ✅ Conformité recommandée pour projet pédagogique en établissement scolaire

---

## 📅 Dernière mise à jour

Avril 2025

