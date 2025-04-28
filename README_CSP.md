# 🔐 Politique de sécurité CSP – Assistant IA

Ce fichier résume la stratégie CSP (Content-Security-Policy) mise en place dans l’application Flask du projet Assistant IA.

---

## ✅ Objectifs

- Limiter les vecteurs XSS (scripts externes, styles inline, etc.)
- Sécuriser toutes les pages par défaut
- Maintenir une compatibilité avec MathJax (nécessite des permissions spécifiques sur /ia)
- Permettre le suivi des violations en production via reporting CSP

---

## 🎯 Politique CSP appliquée

### 🔒 Par défaut (toutes les pages sauf `/ia`)

```
Content-Security-Policy:
  default-src 'self';
  img-src 'self' data:;
  style-src 'self';
  script-src 'self';
  connect-src 'self';
  font-src 'self';
  report-uri /csp-report;
```

### 🔄 Exception pour `/ia`

```
Content-Security-Policy:
  default-src 'self';
  img-src 'self' data:;
  style-src 'self' 'unsafe-inline';
  script-src 'self' https://cdn.jsdelivr.net https://polyfill.io 'unsafe-eval' 'unsafe-inline';
  connect-src 'self';
  font-src 'self' https://cdn.jsdelivr.net;
  report-uri /csp-report;
```

---

## 🕵️ Reporting CSP actif

Les violations sont envoyées :
- via `report-uri` : `/csp-report` (classique)
- via `Report-To` : JSON moderne pour navigateurs récents

### Exemple de log :

```
[W] [CSP] Violation (raw CSP report): {
  "csp-report": {
    "document-uri": "http://...",
    "violated-directive": "style-src-attr",
    ...
  }
}
```

---

## 📌 Recommandations

- Utiliser des classes CSS au lieu de `.style.` dans le JS
- Éviter `unsafe-inline` hors `/ia`
- Éviter `unsafe-eval` si MathJax est rapatrié localement
- Consulter les logs de `/csp-report` régulièrement

---

Mise à jour : avril 2025
