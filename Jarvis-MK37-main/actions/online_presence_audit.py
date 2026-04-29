"""
Online Presence Audit Tool
Retrouve tous les comptes publics associés à partir d'un Instagram principal
"""

import requests
from typing import Dict, List, Tuple


def online_presence_audit(instagram_handle: str, aliases: list = None) -> Dict:
    """
    Audit tous les comptes publics associés.
    
    Args:
        instagram_handle: @handle Instagram principal
        aliases: liste optionnelle de pseudos à chercher
    
    Returns:
        Dict avec comptes confirmés, probables, incertains
    """
    
    if aliases is None:
        aliases = []
    
    # Ajouter le handle Instagram et ses variantes de base
    search_terms = [instagram_handle.replace("@", "")] + aliases
    search_terms = list(set(search_terms))  # Enlever doublons
    
    results = {
        "confirmé": [],
        "probable": [],
        "incertain": []
    }
    
    platforms = {
        "TikTok": "https://www.tiktok.com/@{username}",
        "Twitter/X": "https://twitter.com/{username}",
        "YouTube": "https://www.youtube.com/@{username}",
        "Twitch": "https://www.twitch.tv/{username}",
        "GitHub": "https://github.com/{username}",
        "LinkedIn": "https://linkedin.com/in/{username}",
        "Snapchat": "https://snapchat.com/add/{username}",
    }
    
    for term in search_terms:
        for platform, url_template in platforms.items():
            profile_url = url_template.format(username=term)
            
            try:
                response = requests.head(profile_url, timeout=5, allow_redirects=True)
                
                if response.status_code == 200:
                    result = {
                        "plateforme": platform,
                        "handle": term,
                        "url": profile_url,
                        "preuve": f"Profil public trouvé"
                    }
                    
                    # Classifier selon la proximité du pseudo
                    if term == instagram_handle.replace("@", ""):
                        results["confirmé"].append(result)
                    elif any(part in instagram_handle for part in term.split("_")):
                        results["probable"].append(result)
                    else:
                        results["incertain"].append(result)
                        
            except (requests.ConnectionError, requests.Timeout):
                pass  # Compte probablement inexistant
    
    return results


def format_audit_results(results: Dict) -> str:
    """Formate les résultats pour l'affichage"""
    
    output = "📊 AUDIT DE PRÉSENCE EN LIGNE\n"
    output += "=" * 50 + "\n\n"
    
    # Confirmé
    if results["confirmé"]:
        output += "✅ CONFIRMÉ\n"
        for item in results["confirmé"]:
            output += f"  • {item['plateforme']:15} | @{item['handle']:20} | {item['url']}\n"
        output += "\n"
    
    # Probable
    if results["probable"]:
        output += "⚠️  PROBABLE\n"
        for item in results["probable"]:
            output += f"  • {item['plateforme']:15} | @{item['handle']:20} | {item['url']}\n"
        output += "\n"
    
    # Incertain
    if results["incertain"]:
        output += "❓ INCERTAIN\n"
        for item in results["incertain"]:
            output += f"  • {item['plateforme']:15} | @{item['handle']:20} | {item['url']}\n"
        output += "\n"
    
    if not any([results["confirmé"], results["probable"], results["incertain"]]):
        output += "❌ Aucun compte trouvé avec ces pseudos.\n"
    
    return output
