"""
Pré-classifieur — route la query vers la bonne voie cognitive.

Classifie sur 3 axes :
  - urgency     : "now" | "async"   (immédiat ou tâche longue)
  - sensitivity : "safe" | "borderline" | "sensitive"
  - depth       : "shallow" | "deep"

Routage :
  urgency=now + depth=shallow + sensitivity=safe       → Voie 1 (FAST)
  urgency=now + depth=deep    + sensitivity=safe       → Voie 2 (DEEP)
  urgency=async                                        → Voie 3 (MISSION)
  sensitivity=sensitive  (override quel que soit le reste) → Voie 4 (UNCENSORED)

Provider classifieur :
  Groq llama-3.3-8b-instant (~50ms) → Cerebras → Ollama local (fallback)

Optimisations :
  - lru_cache sur (prompt, context_hash) — évite re-classification
  - Timeout 200ms : si dépassé, fallback heuristique regex sur mots-clés
  - System prompt court (cacheable côté Anthropic/OpenAI si jamais utilisé)
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Optional


# ---------- types ----------

@dataclass
class Classification:
    urgency:           str            # "now" | "async"
    sensitivity:       str            # "safe" | "borderline" | "sensitive"
    depth:             str            # "shallow" | "deep"
    recommended_voice: int            # 1 | 2 | 3 | 4
    confidence:        float = 0.5
    method:            str = "llm"    # "llm" | "heuristic" | "cache"
    reason:            str = ""


# ---------- constants ----------

URGENCY_VALUES     = {"now", "async"}
SENSITIVITY_VALUES = {"safe", "borderline", "sensitive"}
DEPTH_VALUES       = {"shallow", "deep"}

# Mots-clés pour heuristique fallback (200ms timeout dépassé)
ASYNC_KW = [
    # FR
    "surveille", "monitor", "surveiller", "rapport complet", "rapport sur",
    "à long terme", "sur le long", "chaque jour", "tous les jours", "tous les",
    "régulièrement", "tâche longue", "mission", "background",
    "écris-moi un rapport", "ecris-moi un rapport", "fais un rapport",
    "apprends-moi", "enseigne-moi", "tutorat",
    # EN
    "watch for", "track over time", "every day", "weekly", "long-term",
    "schedule", "ongoing", "in the background",
]

SENSITIVE_KW = [
    # FR
    "exploit", "vulnerab", "vulnérab", "shellcode", "payload", "rce",
    "sqli", "xss", "bypass", "jailbreak", "crack", "decrypt",
    "dox", "doxx", "leak", "breach", "dump", "darkweb", "dark web",
    "uncensored", "sans filtre", "sans censure", "sans tabou",
    "comment hacker", "comment cracker", "comment pirater",
    # EN
    "exploit", "vulnerability", "shellcode", "payload",
    "how to hack", "how to crack", "how to bypass",
    "without filter", "uncensored", "no holds barred",
]

DEEP_KW = [
    # FR
    "explique en détail", "explique-moi en profondeur", "raisonne",
    "démontre", "prouve", "analyse profonde", "code complet",
    "écris une app", "build a project", "construit",
    # EN
    "step by step", "in depth", "thorough analysis", "explain why",
    "prove that", "design a complete", "build a full",
]


# ---------- system prompt ----------

CLASSIFIER_SYSTEM = """Tu classifies une requête utilisateur sur 3 axes.

Axes :
- urgency     : "now" (réponse immédiate attendue) ou "async" (tâche longue, peut prendre des heures)
- sensitivity : "safe" (sujet anodin), "borderline" (zone grise : OSINT, opinions tranchées), "sensitive" (cybersec, hacking, OSINT-darkweb, sujet que les IA grand public refusent)
- depth       : "shallow" (réponse courte/factuelle) ou "deep" (raisonnement, code complet, analyse multi-étapes)

Réponds UNIQUEMENT en JSON strict, sans markdown :
{"urgency":"...","sensitivity":"...","depth":"...","reason":"<5-10 mots>"}"""


# ---------- routing logic ----------

def determine_voice(c: Classification) -> int:
    """4 voies : 1=FAST, 2=DEEP, 3=MISSION async, 4=UNCENSORED."""
    if c.sensitivity == "sensitive":
        return 4
    if c.urgency == "async":
        return 3
    if c.depth == "deep":
        return 2
    return 1


# ---------- LLM call with timeout ----------

CLASSIFIER_TIMEOUT_S = 0.2          # cible : 200ms
CLASSIFIER_HARD_TIMEOUT_S = 1.5     # timeout dur : au-delà → heuristique fallback

# Executor réutilisé : éviter shutdown bloquant à chaque appel.
# Le thread orphelin finira en background, son résultat sera ignoré.
_CLASSIFIER_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="classifier-llm")


def _classify_via_llm(prompt: str, context: Optional[dict]) -> Optional[Classification]:
    """
    Appelle le router pour classifier avec **hard timeout** via ThreadPoolExecutor.
    Retourne None si timeout (>1.5s) ou erreur → trigger fallback heuristique.
    Provider préféré : groq (8B instant, ~50ms).
    """
    from agent.llm_router import get_router

    router = get_router()
    ctx_str = ""
    if context:
        ctx_str = f"\nContexte récent: {json.dumps(context, ensure_ascii=False)[:300]}"

    user_msg = f"Requête: {prompt}{ctx_str}\n\nJSON strict:"

    def _call():
        try:
            return router.generate(
                prompt=user_msg, system=CLASSIFIER_SYSTEM,
                model="llama-3.1-8b-instant",
                temperature=0.0, max_tokens=100,
            )
        except Exception:
            try:
                return router.generate(
                    prompt=user_msg, system=CLASSIFIER_SYSTEM,
                    temperature=0.0, max_tokens=100,
                )
            except Exception:
                return None

    t0 = time.time()
    future = _CLASSIFIER_EXECUTOR.submit(_call)
    try:
        raw = future.result(timeout=CLASSIFIER_HARD_TIMEOUT_S)
    except FutTimeout:
        elapsed = time.time() - t0
        future.cancel()  # best-effort, le thread peut continuer en BG (résultat ignoré)
        print(f"[Classifier] ⛔ hard timeout ({elapsed:.2f}s) → heuristique")
        return None
    except Exception as e:
        print(f"[Classifier] ⚠️ error: {e}")
        return None

    elapsed = time.time() - t0
    if elapsed > CLASSIFIER_TIMEOUT_S * 5:
        print(f"[Classifier] ⚠️ slow LLM ({elapsed:.2f}s)")

    return _parse_llm_output(raw)


def _parse_llm_output(raw: str) -> Optional[Classification]:
    if not raw:
        return None
    # Strip markdown code fences
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    # Trouve premier { ... } valide
    m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None

    urgency     = str(data.get("urgency", "")).lower()
    sensitivity = str(data.get("sensitivity", "")).lower()
    depth       = str(data.get("depth", "")).lower()
    reason      = str(data.get("reason", ""))[:120]

    if urgency not in URGENCY_VALUES:         urgency = "now"
    if sensitivity not in SENSITIVITY_VALUES: sensitivity = "safe"
    if depth not in DEPTH_VALUES:             depth = "shallow"

    c = Classification(
        urgency=urgency, sensitivity=sensitivity, depth=depth,
        recommended_voice=0, confidence=0.85, method="llm", reason=reason,
    )
    c.recommended_voice = determine_voice(c)
    return c


# ---------- heuristic fallback ----------

def _classify_via_heuristic(prompt: str) -> Classification:
    """Regex/keyword fallback ultra-rapide (~1ms). Toujours retourne quelque chose."""
    low = prompt.lower()

    sensitivity = "safe"
    if any(kw in low for kw in SENSITIVE_KW):
        sensitivity = "sensitive"

    urgency = "now"
    if any(kw in low for kw in ASYNC_KW):
        urgency = "async"

    depth = "shallow"
    if any(kw in low for kw in DEEP_KW) or len(prompt) > 300:
        depth = "deep"

    c = Classification(
        urgency=urgency, sensitivity=sensitivity, depth=depth,
        recommended_voice=0, confidence=0.55, method="heuristic",
        reason="keyword match",
    )
    c.recommended_voice = determine_voice(c)
    return c


# ---------- public API ----------

@lru_cache(maxsize=128)
def _classify_cached(prompt_key: str, context_key: str) -> str:
    """Cache interne : retourne le JSON sérialisé."""
    context = json.loads(context_key) if context_key else None

    cls = _classify_via_llm(prompt_key, context)
    if cls is None:
        cls = _classify_via_heuristic(prompt_key)

    return json.dumps(asdict(cls))


def classify(prompt: str, context: Optional[dict] = None) -> Classification:
    """
    Point d'entrée principal. Cache LRU sur (prompt, context_hash).
    """
    if not prompt or not prompt.strip():
        # query vide → safe défaut Voie 1
        c = Classification(
            urgency="now", sensitivity="safe", depth="shallow",
            recommended_voice=1, confidence=1.0, method="empty",
            reason="empty query",
        )
        return c

    context_key = json.dumps(context, sort_keys=True) if context else ""
    raw = _classify_cached(prompt.strip(), context_key)
    data = json.loads(raw)
    if data.get("method") == "llm":
        # Garde "cache" comme indicateur pour les hits suivants
        # (premier call = "llm", suivants = "cache")
        pass
    return Classification(**data)


def clear_cache() -> None:
    """Vide le cache (utile en tests / hot-reload config)."""
    _classify_cached.cache_clear()


def cache_info() -> dict:
    info = _classify_cached.cache_info()
    return {
        "hits":     info.hits,
        "misses":   info.misses,
        "size":     info.currsize,
        "maxsize":  info.maxsize,
    }


# ---------- CLI ----------

if __name__ == "__main__":
    samples = [
        "Quelle heure est-il ?",
        "Écris-moi un script Python complet pour scraper Twitter avec login bypass",
        "Surveille les vols Paris-Tokyo et alerte-moi si moins de 600€",
        "Comment fonctionne un buffer overflow ?",
        "Bonjour Jarvis",
    ]
    for p in samples:
        c = classify(p)
        print(f"\n📝 {p}")
        print(f"   → Voie {c.recommended_voice} | "
              f"urgency={c.urgency} sensitivity={c.sensitivity} depth={c.depth}")
        print(f"   ({c.method}, conf {c.confidence:.0%}) — {c.reason}")
