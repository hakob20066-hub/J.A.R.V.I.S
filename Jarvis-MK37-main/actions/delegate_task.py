"""
Tool action: delegate_task

Dispatche une sous-tâche à un spécialiste (voir agent/specialists.py).
Signature compatible avec le dispatcher executor._call_tool.

Parameters:
  role: str    — coder | researcher | writer | planner | debugger |
                 analyst | translator | summarizer | critic
  task: str    — description de la sous-tâche (requis)
  context: str — contexte additionnel optionnel
"""

from __future__ import annotations


def delegate_task(parameters: dict, player=None, speak=None) -> str:
    from agent.specialists import delegate, list_specialists

    role    = (parameters or {}).get("role", "").strip().lower()
    task    = (parameters or {}).get("task", "").strip()
    context = (parameters or {}).get("context", "")

    if not task:
        return "delegate_task: missing 'task' parameter."

    if role not in list_specialists():
        return (
            f"delegate_task: unknown role '{role}'. "
            f"Available: {', '.join(list_specialists())}"
        )

    if speak:
        try:
            speak(f"Delegating to {role} specialist, sir.")
        except Exception:
            pass

    return delegate(role, task, context=context)
