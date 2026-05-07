"""recon_ng_cli — alias léger autour de ReconNgConnector déjà défini.

Permet de lister recon-ng dans le registre via deux noms (rétrocompat),
mais exécute le même client.
"""
from __future__ import annotations

# ReconNgConnector se enregistre déjà via reconng_client.py.
# Ce module ne fait rien de plus — il existe pour cohérence avec la liste
# des 15 wrappers Session 3 (recon_ng_cli).
from agent.osint.reconng_client import ReconNgConnector  # noqa: F401
