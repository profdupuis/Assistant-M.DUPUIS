

"""
auth.py — Module d'authentification et de sécurité pour l'application Flask

Ce module fournit deux décorateurs à utiliser pour protéger les routes :

- @login_required       : Vérifie qu'un élève est connecté (clé 'student_id' dans la session)
- @login_required_admin : Vérifie qu'un administrateur est connecté (clé 'is_admin' dans la session)

Utilisation typique dans app.py :
    from aut import login_required, login_required_admin

    @app.route("/mon_dashboard")
    @login_required
    def mon_dashboard():
        ...

Remarques :
- Les décorateurs redirigent vers la page appropriée si l'utilisateur n'est pas authentifié.
- Aucune dépendance à des bases externes, uniquement basé sur la session Flask.
"""

from functools import wraps

from flask import session
from flask import (
    session,
    redirect,
    url_for
)


def login_required_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "student_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function