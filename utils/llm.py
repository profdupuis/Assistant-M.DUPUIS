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
import tiktoken


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))



MODEL_CORRECTION = "gpt-4.1"
TEMPERATURE_CORRECTION=0.2
MODEL_FEEDBACK = "gpt-4.1"
TEMPERATURE_FEEDBACK=0.3
MODEL_RESUME = "gpt-4.1"
TEMPERATURE_RESUME=0
# parametre temperature = 0.3 ou  0.5 ?

MAX_RESUME_TOKENS = 40000
TOKEN_USAGE_RATIO_BEFORE_SUMMARIZE = 0.5  # 50% de la limite
MAX_TOKENS_BY_MODEL = {
    "gpt-4": 8192,
    "gpt-4-0613": 8192,
    "gpt-4-0125-preview": 128000,
    "gpt-4-1106-preview": 128000,
    "gpt-4.1": 128000,
    "gpt-4o": 128000,
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-16k": 16384
}




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
    return call_llm(messages, user_id=user_id, model=MODEL_CORRECTION,temperature=TEMPERATURE_CORRECTION)

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
    return call_llm(messages, user_id=user_id, model=MODEL_FEEDBACK,temperature=TEMPERATURE_FEEDBACK)


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


def estimate_tokens(messages: list[dict], model: str = MODEL_CORRECTION) -> int:
    """
    Estime le nombre de tokens utilisés par une liste de messages pour un modèle donné.

    Utilise la bibliothèque `tiktoken` si disponible pour un calcul précis,
    sinon effectue une estimation simple en divisant la longueur du texte par 4.

    Args:
        messages (list[dict]): Historique de la conversation (messages OpenAI).
        model (str): Nom du modèle utilisé (ex: "gpt-4.1").

    Returns:
        int: Nombre estimé de tokens utilisés.
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    total = 0
    for msg in messages:
        total += 4  # overhead par message
        for key, value in msg.items():
            total += len(encoding.encode(value))
            if key == "name":
                total += 1
    total += 2  # overhead final
    return total


def should_summarize(history: list[dict], model: str = MODEL_CORRECTION) -> bool:
    """
    Détermine si l'historique est suffisamment long pour justifier un résumé.

    La fonction compare le nombre de tokens estimés à la moitié de la limite maximale
    autorisée par le modèle. Au-delà, un résumé est recommandé pour ne pas saturer le contexte.

    Args:
        history (list[dict]): Historique actuel de la conversation.
        model (str): Modèle utilisé pour la correction (définit la limite de tokens).

    Returns:
        bool: True si un résumé est nécessaire, False sinon.
    """
    max_tokens = MAX_TOKENS_BY_MODEL.get(model, 8192)
    seuil = min(max_tokens * TOKEN_USAGE_RATIO_BEFORE_SUMMARIZE,MAX_RESUME_TOKENS)
    return estimate_tokens(history, model=model) > seuil



def summarize_history(history: list[dict]) -> str:
    """
    Résume une conversation sous forme de 5 lignes concises maximum.

    Injecte un prompt système et utilise `call_llm()` avec le modèle spécifié
    pour obtenir un résumé utile à réinjecter dans l'historique condensé.

    Args:
        history (list[dict]): Liste complète des échanges à résumer.

    Returns:
        str: Résumé généré à insérer dans une nouvelle session condensée.
    """
    prompt = [
        {"role": "system", "content": "Tu es un assistant qui résume efficacement."},
        *history,
        {"role": "user", "content": "Fais un résumé concis de cette conversation en 5 lignes max."}
    ]
    return call_llm(prompt, model=MODEL_RESUME,temperature=TEMPERATURE_RESUME).strip()


