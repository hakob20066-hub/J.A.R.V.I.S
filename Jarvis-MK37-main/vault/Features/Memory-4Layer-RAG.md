"""
# Système de Mémoire 4 Couches + RAG

## Architecture

Le système unifie 4 couches de mémoire complémentaires :

```
┌─────────────────────────────────────────────────────┐
│            UNIFIED MEMORY MANAGER (API)             │
├─────────────────────────────────────────────────────┤
│  • retrieve(query, k=5)     → RAG cross-layer        │
│  • format_for_prompt()      → contexte pour LLM     │
│  • decay_old_episodes()     → maintenance            │
└─────────────────────────────────────────────────────┘
        ↓              ↓              ↓            ↓
   ┌─────────┐   ┌──────────┐   ┌──────────┐  ┌─────────────┐
   │ WORKING │   │ EPISODIC │   │ SEMANTIC │  │ PROCEDURAL  │
   │ (FIFO)  │   │ (Events) │   │ (Facts)  │  │ (Recipes)   │
   │ 20 turn │   │ SQLite   │   │ JSON     │  │ JSON        │
   │ RAM     │   │ Persist  │   │ Persist  │  │ Persist     │
   └─────────┘   └──────────┘   └──────────┘  └─────────────┘
      volatile      persistent     permanent      permanent
      no decay      >30j digest    no decay       no decay
```

## 4 Couches

### 1. Working Memory (RAM volatile)

Stocke les 20 derniers tours de conversation. **FIFO** : quand dépassé 20, les plus vieux sont dropés.

**Utilisé pour :**
- Contexte immédiat du LLM
- Historique court-terme
- Pas persisté au redémarrage

**API :**
```python
mem = get_memory()

# Ajouter un tour
mem.add_turn("user", "Hello", intent="greeting", entities=["greeting"])
mem.add_turn("assistant", "Hi there!", intent="greeting")

# Récupérer contexte
ctx = mem.get_working_context(last_n=10)  # str formaté

# Stats
size = mem.working.size()  # 0..20

# Nettoyer
mem.clear_working_memory()
```

### 2. Episodic Memory (Timeline persistante)

Enregistre les **événements importants** dans l'ordre chronologique.
Base de données SQLite : `memory/episodic.db`

**Types d'événements :**
- `conversation`: échange user/assistant
- `tool_call`: action exécutée
- `mission`: mission async complétée
- `error`: erreur détectée
- `preference`: préférence exprimée par user
- `discovery`: info nouvelle apprise
- `milestone`: événement marquant

**Attributs :**
- timestamp (REAL)
- type (TEXT)
- summary (TEXT)
- details (JSON)
- emotional_valence (-1..1)
- related_entities (TEXT, array)
- voice_used (INT)

**API :**
```python
# Écrire un événement
ep_id = mem.write_episode(
    event_type="conversation",
    summary="User asked about memory system",
    details={"topic": "memory", "context": "..."},
    emotional_valence=0.5,  # -1 (sad) to 1 (happy)
    entities=["memory", "system"]
)

# Récupérer récents
recent = mem.get_recent_episodes(n=10)
recent_errors = mem.get_recent_episodes(n=5, event_type="error")

# Chercher
results = mem.search_episodes("memory", limit=10)

# Par entité
about_user = mem.get_episodes_by_entity("user", limit=20)

# Stats
stats = mem.episodic.stats()
# → {"total": 1234, "by_type": {"conversation": 850, ...}}

# Decay (supprime >30 jours)
removed = mem.decay_old_episodes(days_threshold=30)
```

### 3. Semantic Memory (Facts persistants)

Stocke les **vérités stables** : identité, préférences, connaissances.
JSON persistant : `memory/long_term.json`

**Catégories :**
- `identity`: qui es-tu? (name, age, job...)
- `preference`: que préfères-tu?
- `relationship`: tes liens avec les gens
- `knowledge`: facts sur le monde
- (custom categories acceptées)

**Attributs :**
- key (TEXT, unique)
- value (TEXT)
- category (TEXT)
- confidence (0..1)
- created (ISO timestamp)
- updated (ISO timestamp)
- embedding ([]float, optional)

**API :**
```python
# Ajouter/modifier un fact
fact = mem.update_fact(
    key="user_name",
    value="Alice",
    category="identity",
    confidence=1.0
)

# Récupérer
fact = mem.get_fact("user_name")
print(fact.value)  # "Alice"

# Par catégorie
identity_facts = mem.get_facts_by_category("identity")
prefs = mem.get_facts_by_category("preference")

# Chercher
results = mem.semantic.search("Alice")

# Supprimer
mem.delete_fact("user_name")

# Pas de décroissance (facts permanents)
```

### 4. Procedural Memory (Recettes apprises)

Stocke les **façons de faire** : procédures, workflows, tips.
JSON persistant : `config/procedures.json`

**Exemple :** "Pour exporter PDF: File > Export > PDF format > Save"

**Attributs :**
- name (TEXT, unique)
- description (TEXT)
- steps ([]TEXT)
- triggers ([]TEXT, keywords)
- success_count (INT)
- failure_count (INT)
- last_used (ISO)
- last_modified (ISO)
- reliability () = success / (success + failure)

**API :**
```python
# Ajouter recette
proc = mem.add_procedure(
    name="export_pdf",
    description="Export document to PDF",
    steps=[
        "Click File menu",
        "Select Export",
        "Choose PDF format",
        "Click Save"
    ],
    triggers=["export", "pdf", "save as"]
)

# Récupérer
proc = mem.get_procedure("export_pdf")

# Chercher par trigger
matches = mem.find_procedures_by_trigger("pdf")  # mots-clés

# Enregistrer résultat
mem.record_procedure_success("export_pdf")
mem.record_procedure_failure("export_pdf")

# Stats
reliability = proc.reliability()  # 0..1

# Pas de décroissance (recettes permanentes)
```

## RAG (Retrieval-Augmented Generation)

Combine les 4 couches via **embeddings sémantiques** pour un retrieval pertinent.

### Technologie

- **Embeddings :** `sentence-transformers/all-MiniLM-L6-v2` (384 dims, local)
- **Similarité :** cosine similarity
- **Cache :** persistant (JSON) pour éviter recalculs
- **Pondération :** pertinence (cosine) + récence (time decay)

### Pondération

Chaque résultat a un score final = f(pertinence, récence, source)

- **Working memory** : boost de récence fort (decay après 30 min)
- **Episodic** : boost de récence moyen (decay après 30 jours)
- **Semantic** : pas de boost (facts stables)
- **Procedural** : boost de fiabilité (success rate)

### API

```python
# RAG retrieve - top k résultats pertinents
results = mem.retrieve(
    query="Quel est mon nom?",
    k=5,  # top-5
    include_working=True,
    include_episodic=True,
    include_semantic=True,
    include_procedural=False,
)

# results = [
#   RetrievalResult(
#     text="Alice",
#     source="semantic",
#     score=0.98,
#     metadata={"category": "identity", "key": "user_name"},
#     timestamp=0
#   ),
#   ...
# ]

# Formatter pour LLM
context = mem.get_retrieval_context(
    query="Quel est mon nom?",
    k=5,
    separator="\n---\n"
)

print(context)
# [Retrieved context for: Quel est mon nom?]
# 
# [1. SEMANTIC - score 0.98]
# Alice
# 
# ---
# 
# [2. EPISODIC - score 0.87]
# User asked about identity
```

## API Principale : MemoryManager

```python
from memory import get_memory

mem = get_memory()  # Singleton global

# ===== WORKING MEMORY =====
mem.add_turn(role, content, **metadata)
ctx = mem.get_working_context(last_n=10)
mem.clear_working_memory()

# ===== EPISODIC MEMORY =====
ep_id = mem.write_episode(type, summary, details, entities)
recent = mem.get_recent_episodes(n=10, event_type="conversation")
results = mem.search_episodes(query, limit=10)
about = mem.get_episodes_by_entity(name, limit=20)

# ===== SEMANTIC MEMORY =====
fact = mem.update_fact(key, value, category, confidence)
fact = mem.get_fact(key)
facts = mem.get_facts_by_category(category)
mem.delete_fact(key)

# ===== PROCEDURAL MEMORY =====
proc = mem.add_procedure(name, description, steps, triggers)
proc = mem.get_procedure(name)
matches = mem.find_procedures_by_trigger(query)
mem.record_procedure_success(name)
mem.record_procedure_failure(name)

# ===== RAG RETRIEVAL =====
results = mem.retrieve(query, k=5)
context = mem.get_retrieval_context(query, k=5)

# ===== MAINTENANCE =====
removed = mem.decay_old_episodes(days_threshold=30)
mem.flush_caches()

# ===== EXPORT =====
stats = mem.stats()
export = mem.export_all()
prompt_ctx = mem.format_for_prompt()
```

## Décroissance

Mécanisme pour éviter le débordement mémoire :

### Episodic
- **>30 jours** : digest (non implémenté, just delete for now)
- Cutoff via `decay_old_episodes()`

### Working
- **>20 tours** : auto-drop des plus anciens (FIFO native)

### Semantic
- **Pas de décroissance** (facts permanents)

### Procedural
- **Pas de décroissance** (recettes permanentes)

## Backward Compatibility

Ancien code peut utiliser les fonctions compatibilité :

```python
# Ancien code
from memory import load_memory, save_memory, update_memory

memory = load_memory()
update_memory({"identity": {"name": {"value": "Alice"}}})
memory = load_memory()
```

Fonctionne via le nouveau système (internally).

## Cas d'Usage

### 1. Prompt LLM

```python
mem = get_memory()

# Contexte court-terme (working)
recent_turns = mem.get_working_context(last_n=5)

# Contexte sémantique (RAG)
retrieved = mem.get_retrieval_context(user_query, k=5)

system_prompt = f'''
Tu es un assistant personnel.

{recent_turns}

Known facts:
{retrieved}
'''
```

### 2. Logging d'Actions

```python
# Action exécutée
mem.add_turn("action", "opened_browser", tool="browser_control")

# Événement important
mem.write_episode(
    "tool_call",
    "Opened browser to search.google.com",
    details={"url": "search.google.com"},
    entities=["browser", "google"]
)
```

### 3. Apprentissage de Recettes

```python
# User montre comment faire quelque chose
mem.add_turn("user", "To export PDF: File > Export > PDF > Save")

# Bot apprend la recette
mem.add_procedure(
    name="export_pdf",
    description="How to export to PDF",
    steps=["File menu", "Export", "PDF format", "Save"],
    triggers=["export", "pdf"]
)
```

### 4. RAG pour Contextualisation

```python
user_question = "Remind me what we talked about yesterday"

# Retrieve tous les contextes pertinents
context = mem.get_retrieval_context(
    query=user_question,
    k=10
)

response = llm(f"User: {user_question}\n\nContext: {context}")
```

## Configuration

### Embeddings

Modèle fixé : `sentence-transformers/all-MiniLM-L6-v2`

**Pourquoi :**
- 80 MB (petit, local)
- 384 dimensions
- Performant pour retrieval cross-couches
- Pas d'API externe

**Cache :** `memory/embeddings_cache.json`

### Stockage

- Working : RAM uniquement (pas de persistence)
- Episodic : `memory/episodic.db` (SQLite)
- Semantic : `memory/long_term.json` (JSON)
- Procedural : `config/procedures.json` (JSON)

### RAG Tuning

```python
# Top-k retrieval
results = mem.retrieve(query, k=10)  # Default 5

# Incluire/exclure couches
results = mem.retrieve(
    query,
    include_working=True,      # Inclure RAM volatile
    include_episodic=True,     # Inclure events
    include_semantic=True,     # Inclure facts
    include_procedural=False   # Exclure recettes
)

# Format contexte
context = mem.get_retrieval_context(
    query,
    k=3,
    separator="\n---\n"
)
```

## Tests

Lancer les tests :

```bash
python tests/test_memory_4layer.py
```

Couvre :
- Working memory FIFO
- Episodic write/search/decay
- Semantic facts CRUD
- Procedural recipes
- RAG retrieval cross-layer
- Stats & export
- Backward compatibility

## Roadmap

- [ ] Digest mensuel pour episodes >30j
- [ ] Embeddings caching + HNSWlib pour large scale
- [ ] Fine-tuning embeddings sur data spécifique Jarvis
- [ ] Compression episodic via LLM summarization
- [ ] Export/Import full memory snapshots
- [ ] Memory analytics dashboard

## Files

```
memory/
  ├── __init__.py                 # API publique
  ├── memory_manager.py           # API unifiée (NEW)
  ├── working_memory.py           # Volatile FIFO (ENHANCED)
  ├── episodic.py                 # Events timeline (COMPLETE)
  ├── semantic.py                 # Facts persistants (NEW)
  ├── procedural.py               # Recettes apprises (COMPLETE)
  ├── rag.py                       # RAG retrieval (NEW)
  ├── long_term.json              # Semantic facts (persistent)
  ├── episodic.db                 # Episodes SQLite (persistent)
  └── embeddings_cache.json       # Embedding vectors (cache)

config/
  └── procedures.json             # Procedural recipes (persistent)

tests/
  └── test_memory_4layer.py      # Integration tests (NEW)
```
"""
