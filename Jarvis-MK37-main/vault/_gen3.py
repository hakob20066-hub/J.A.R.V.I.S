import os
import random
from pathlib import Path

# Configuration
ROOT = Path(__file__).resolve().parent
DATE = "2026-05-05"

def write_file(rel_path, fm, body):
    p = ROOT / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(v)}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    content = "\n".join(lines) + "\n\n" + body.strip() + "\n"
    p.write_text(content, encoding="utf-8")

def create_note(folder, name, title, tags, body, links=None, moc=None):
    fm = {"title": title, "date": DATE, "tags": tags}
    if moc:
        fm["parent_moc"] = f"[[00-MOC/{moc}]]"
    
    rel_block = ""
    if links:
        rel_block = "\n\n## Liens\n" + "\n".join([f"- [[{l}]]" for l in links])
    
    write_file(f"{folder}/{name}.md", fm, body + rel_block)

print("🌌 Lancement de la Galaxie JARVIS...")

# Configuration des clusters (Dossier: (Nom MOC, Couleur, Nombre de notes))
clusters_config = {
    "01-Concepts": ("MOC-Concepts", "Orange", 80),
    "02-Architecture": ("MOC-Architecture", "Blue", 60),
    "03-Cognitive": ("MOC-Cognitif", "Purple", 70),
    "04-Memory": ("MOC-Memoire", "Green", 70),
    "05-Security": ("MOC-Securite", "Red", 60),
    "06-Audio-Voice": ("MOC-Audio-Voix", "Cyan", 50),
    "07-LLM-Router": ("MOC-Providers-LLM", "Yellow", 60),
    "08-Tools": ("MOC-Tools", "Grey", 100),
}

# 1. Nettoyage
for folder in clusters_config.keys():
    folder_path = ROOT / folder
    if folder_path.exists():
        for f in folder_path.glob("*.md"):
            f.unlink()

all_hubs = []

# 2. Génération des Constellations
for folder, config in clusters_config.items():
    moc_name, color, count = config
    print(f"✨ Création du cluster {color}...")
    
    # Création du Hub (Le Soleil)
    hub_name = f"hub-{moc_name.lower()}"
    hub_path = f"{folder}/{hub_name}.md"
    all_hubs.append(hub_path)
    
    # Création des satellites
    satellites = [f"node-{i:03d}" for i in range(count)]
    
    for s_name in satellites:
        # Chaque satellite est lié au HUB (Rayon)
        links = [hub_path]
        
        # Liens avec 2 autres satellites du même dossier (Nuage)
        others = random.sample([s for s in satellites if s != s_name], 2)
        for o in others:
            links.append(f"{folder}/{o}.md")
            
        create_note(folder, s_name, f"Satelite {s_name}", ["atomique"], 
                   f"Donnée atomique du cluster {color}.", 
                   links=links, moc=moc_name)

    # Finalisation du Hub (Liens vers quelques satellites)
    hub_links = [f"{folder}/{s}.md" for s in random.sample(satellites, 10)]
    create_note(folder, hub_name, f"Solaire {moc_name}", ["hub", "center"], 
                f"Coeur du cluster {color}.", 
                links=hub_links, moc=moc_name)

# 3. Ponts entre les Hubs (Inter-Galactiques)
for hub in all_hubs:
    with open(ROOT / hub, "a", encoding="utf-8") as f:
        f.write("\n\n## 🌉 Ponts\n")
        others = random.sample([h for h in all_hubs if h != hub], 2)
        for o in others:
            f.write(f"- [[{o}]]\n")

# 4. Index Maître
hub_links_list = "\n".join([f"- [[{h}]]" for h in all_hubs])
write_file("INDEX_MAITRE.md", {"title": "Index Maître", "date": DATE, "tags": ["master"]}, 
           f"# 🌌 INDEX MAÎTRE\n\n{hub_links_list}")

print("\n🚀 TERMINÉ ! Ton graphique doit maintenant ressembler à une galaxie.")
