# 🚀 Installation JARVIS sur un nouveau PC

## Étape 1️⃣ : Cloner le projet depuis GitHub

```bash
git clone <YOUR_GITHUB_REPO_URL>
cd Jarvis-MK37-main
```

## Étape 2️⃣ : Créer le fichier `.env` avec vos clés API

Copier le fichier d'exemple et le remplir :

```bash
cp .env.example .env
```

Puis ouvrir `.env` dans un éditeur et remplacer les valeurs :

```env
GEMINI_API_KEY=votre_clé_ici
OS_SYSTEM=windows
```

**⚠️ Important** : Le fichier `.env` est **ignoré par Git** (dans `.gitignore`). C'est normal et sécurisé !

### Où trouver vos clés API ?
- **Gemini** → [console.cloud.google.com](https://console.cloud.google.com)
- **OpenAI** → [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- **Autres services** → Voir `.env.example` pour la liste complète

## Étape 3️⃣ : Installer les dépendances

### Option A : Setup automatique (recommandé)
```bash
python setup.py
```

### Option B : Installation manuelle
```bash
pip install -r requirements.txt
playwright install
```

## Étape 4️⃣ : Lancer JARVIS

```bash
python main.py
```

---

## 🔒 Sécurité

- ✅ Le fichier `.env` contient vos clés **confidentielles**
- ✅ `.env` n'est **jamais commité** sur GitHub
- ✅ Seul `.env.example` est partagé (template vide)
- ✅ Chaque PC a son propre `.env` local

## ⚙️ Configuration supplémentaire

Si vous avez besoin d'autres clés API, ajoutez-les dans `.env` :

```env
GEMINI_API_KEY=...
OPENAI_API_KEY=...
GROQ_API_KEY=...
ANTHROPIC_API_KEY=...
```

Puis mettez à jour le code dans `main.py` pour les utiliser.

---

## ❓ Problèmes courants

### `GEMINI_API_KEY not found`
→ Vérifier que `.env` existe et contient la clé

### Import error `dotenv`
```bash
pip install python-dotenv
```

### Problème Playwright
```bash
playwright install
```

---

**Questions ?** Consultez le README.md principal.
