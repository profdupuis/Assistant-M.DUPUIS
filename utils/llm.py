"""
llm.py — Interface centralisée pour l'utilisation des modèles OpenAI dans le projet pédagogique.

Ce module fournit des fonctions pour interagir avec l'API OpenAI :
- Génération de corrections et explications avec une température basse (réponses fiables et rigoureuses)
- Génération de feedbacks finaux avec une température plus élevée (réponses nuancées et variées)
- Modération des messages entrants pour vérifier leur conformité

Paramètre important :
    temperature (float) — Contrôle la créativité des réponses générées :
        - 0.0 : réponses très déterministes et factuelles
        - 0.3 : bon pour la rigueur (corrections)
        - 0.5 : bon équilibre rigueur / naturel (feedback final)
        - 0.8+ : plus créatif, mais moins fiable (non utilisé ici)
"""


import os
from openai import OpenAI



client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL_CORRECTION = "gpt-4o"
MODEL_FEEDBACK   = "gpt-4o"

def call_llm(messages, user_id=None, model="gpt-4o", temperature=0.5):
    """
    Appel générique à l'API OpenAI ChatCompletion.

    Args:
        messages (list): Historique des messages au format [{"role": "user", "content": ...}, ...]
        user_id (str): ID de l'utilisateur, transmis pour le suivi par OpenAI
        model (str): Nom du modèle à utiliser (ex: "gpt-4o")
        temperature (float): Contrôle la créativité de la réponse (voir docstring du module)

    Returns:
        str: Contenu textuel de la réponse générée par l'IA
    """
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        user=user_id,
        temperature=temperature
    )
    return response.choices[0].message.content


def correction_et_explication(messages, user_id):
    """
    Génère une réponse rigoureuse à une question d'élève, avec explication et correction éventuelle.

    Température basse (0.3) pour favoriser la précision.

    Args:
        messages (list): Historique des échanges avec l'élève
        user_id (str): Identifiant unique de l'élève

    Returns:
        str: Réponse générée par l'IA
    """
    return call_llm(messages, user_id=user_id, model=MODEL_CORRECTION, temperature=0.3)

def feedback_final(messages, user_id):
    """
    Génère un feedback final synthétique pour l'élève à la fin d'un exercice.

    Température modérée (0.5) pour plus de naturel et de variété.

    Args:
        messages (list): Historique de l'exercice
        user_id (str): Identifiant unique de l'élève

    Returns:
        str: Feedback final
    """
    return call_llm(messages, user_id=user_id, model=MODEL_FEEDBACK, temperature=0.5)


def moderation_par_llm(user_input):
    """
    Analyse un message (provenant d’un utilisateur ou de l’IA) pour détecter des contenus sensibles ou inappropriés.

    Utilise l’API de modération d’OpenAI pour identifier les catégories problématiques telles que la haine,
    la violence, le harcèlement ou la sexualité.

    Args:
        user_input (str): Contenu du message à analyser (peut être rédigé par l’élève ou généré par l’IA).

    Returns:
        dict: Dictionnaire booléen indiquant les catégories identifiées comme potentiellement problématiques.
        Exemple :
            {
                "hate": False,
                "sexual": False,
                "violence": False,
                "self-harm": False,
                "harassment": True,
                "sexual/minors": False,
                "hate/threatening": False,
                "self-harm/intent": False,
                "violence/graphic": False,
                "harassment/threatening": False,
                "self-harm/instructions": False
            }

    Notes:
        - Ce dictionnaire correspond à `response.results[0].categories` de l’API OpenAI Moderation.
        - La structure peut évoluer si OpenAI modifie ou ajoute des catégories.
        - Ce système peut être utilisé pour filtrer les messages entrants et sortants.
    """
    try:
        response = client.moderations.create(
            model="text-moderation-latest",
            input=user_input
        )
        return response.results[0].categories.to_dict()

    except Exception as e:
        return {"error": True}
