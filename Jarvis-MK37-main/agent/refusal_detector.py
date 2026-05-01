"""
Refusal detector — détecte si un LLM a refusé de répondre.

Patterns multilangues (FR/EN/ES) couvrant :
  - Refus durs    : "I can't", "Je ne peux pas"
  - Refus mous    : "this might not be appropriate"
  - Excuses IA    : "as an AI", "en tant qu'IA"
  - Disclaimers   : "I'm not able to help with that"

Usage :
    if is_refusal(response):
        # re-route vers Voie 4 uncensored
"""

from __future__ import annotations

import re

# ---------- patterns ----------

# Cas où le LLM annonce explicitement qu'il refuse
HARD_REFUSAL_PATTERNS = [
    # EN
    r"\bi (?:can('?| no)?t|cannot|won'?t)\b",
    r"\bi(?:'?m| am) not able to\b",
    r"\bi(?:'?m| am) unable to\b",
    r"\bi(?:'?m| am) sorry,?\s+(?:but\s+)?i\b",
    r"\bi must (?:respectfully\s+)?decline\b",
    r"\bi don'?t feel comfortable\b",
    r"\bi'?ll have to (?:pass|decline)\b",
    r"\bas an? (?:ai|llm|language model|assistant)\b",
    r"\bi(?:'?m| am) not (?:able|allowed|permitted|programmed) to\b",
    r"\bagainst my (?:guidelines|programming|principles|values|policies)\b",
    r"\bi (?:do not|don'?t) (?:condone|support|provide)\b",
    r"\bcan'?t help (?:you )?with (?:that|this)\b",
    # FR
    r"\bje (?:ne )?peux (?:pas|malheureusement pas)\b",
    r"\bje (?:n'?ai pas|n'?suis pas) (?:capable|en mesure|autorisé)\b",
    r"\bil (?:m'?est )?(?:impossible|interdit) de\b",
    r"\bdésolé,?\s+(?:mais\s+)?je\b",
    r"\bje (?:dois|doit) (?:décliner|refuser)\b",
    r"\ben tant qu'?(?:ia|intelligence artificielle|assistant)\b",
    r"\bcontraire à (?:mes\s+)?(?:principes|valeurs|directives|règles)\b",
    r"\bà l'?encontre de (?:mes\s+)?(?:principes|valeurs|directives|règles)\b",
    r"\bje ne (?:cautionne|soutiens|approuve) pas\b",
    # ES
    r"\bno puedo\b",
    r"\bcomo (?:una )?ia\b",
    r"\blo siento,?\s+pero\b",
]

# Cas plus subtils (refus camouflé en "je préfère pas" / hedging)
SOFT_REFUSAL_PATTERNS = [
    # EN
    r"\bthis (?:might not be|may not be|isn'?t) (?:appropriate|something I should)\b",
    r"\bi'?d (?:rather|prefer) not\b",
    r"\bi (?:would )?(?:strongly )?(?:advise|recommend) against\b",
    r"\bit'?s not (?:appropriate|safe|ethical) (?:to|for me)\b",
    r"\bi(?:'?m| am) hesitant to\b",
    r"\binstead,?\s+(?:i suggest|let me suggest|consider)\b",
    # FR
    r"\bje préfère(?:rais)? (?:ne pas|éviter)\b",
    r"\bil (?:vaut mieux|serait préférable) (?:que|de)\b",
    r"\bje (?:vous )?(?:déconseille|recommande de ne pas)\b",
]

# Sujet typique des disclaimers qui prefacent un refus
PREAMBLE_PATTERNS = [
    r"\b(?:please note|disclaimer|important|caution)[\s,:]\s*",
    r"\b(?:veuillez|à noter|attention)[\s,:]\s*",
]


_HARD_RE     = re.compile("|".join(HARD_REFUSAL_PATTERNS), re.IGNORECASE)
_SOFT_RE     = re.compile("|".join(SOFT_REFUSAL_PATTERNS), re.IGNORECASE)
_PREAMBLE_RE = re.compile("|".join(PREAMBLE_PATTERNS), re.IGNORECASE)


# ---------- public API ----------

def is_refusal(text: str, soft: bool = True) -> bool:
    """
    True si le texte ressemble à un refus.

    soft=True (default) : détecte aussi les refus camouflés.
    soft=False : seulement les refus francs.
    """
    if not text or not text.strip():
        return False

    # Refus dur dans les 200 premiers caractères = vrai refus
    head = text[:300]
    if _HARD_RE.search(head):
        return True

    if soft:
        # Refus mou = soft refusal + courte réponse globale (pas de vrai contenu après)
        if _SOFT_RE.search(head) and len(text) < 600:
            return True

    return False


def refusal_score(text: str) -> float:
    """
    Score 0.0-1.0. > 0.5 = probable refus.

    Useful pour classifier en granularité plus fine que True/False.
    """
    if not text or not text.strip():
        return 0.0

    head = text[:400]
    score = 0.0

    if _HARD_RE.search(head):
        score += 0.7
    if _SOFT_RE.search(head):
        score += 0.3
    if _PREAMBLE_RE.search(head):
        score += 0.1

    # Réponse très courte + mot "sorry/désolé" en début = refus probable
    if len(text) < 150 and re.match(
        r"\s*(i'?m sorry|sorry|désolé|lo siento)", text, re.IGNORECASE
    ):
        score += 0.2

    # Longueur très courte (< 30 chars) avec mots de refus = refus
    if len(text.strip()) < 30 and re.search(
        r"\b(can'?t|cannot|won'?t|peux pas|impossible)\b", text, re.IGNORECASE
    ):
        score += 0.5

    return min(1.0, score)


def find_refusal_phrase(text: str) -> str:
    """Retourne la première phrase de refus trouvée (debug)."""
    for rx in (_HARD_RE, _SOFT_RE):
        m = rx.search(text or "")
        if m:
            return m.group(0)
    return ""
