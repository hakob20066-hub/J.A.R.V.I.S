"""
MissionRunner — daemon thread qui exécute les missions Voie 3 en background.

Pull les missions pending du MissionStore, les claim atomiquement, exécute via
la voix appropriée (Voie 2 ou 4 selon `mission.voice_used`), met à jour le status.

Configurable :
  - max_workers : nombre de missions en parallèle (default 2 — laisse de la RAM
    pour le voice loop principal)
  - poll_interval : secondes entre 2 polls quand store vide (default 3s)

Usage :
    from agent.mission_runner import get_runner
    runner = get_runner()
    runner.start()      # démarre le thread daemon
    runner.stop()       # graceful shutdown
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Optional

from agent.flow_manager import get_flow_manager
from agent.mission_models import Mission
from agent.mission_store import MissionStore


DEFAULT_MAX_WORKERS  = 2
DEFAULT_POLL_INTERVAL = 3.0  # seconds
CLEAR_DONE_KEEP_LAST = 50    # purge missions done au boot et périodiquement


def _adaptive_max_workers() -> int:
    """1 worker si AirLLM (RAM-bound), 2 sinon. Lit runtime.json."""
    try:
        import json as _json
        from pathlib import Path as _Path
        rt_path = _Path(__file__).resolve().parent.parent / "config" / "runtime.json"
        if rt_path.exists():
            data = _json.loads(rt_path.read_text(encoding="utf-8"))
            backend = (data.get("hardware", {}).get("recommended_local_backend")
                       or data.get("local_backend_override", ""))
            if str(backend).lower() == "airllm":
                return 1
    except Exception:
        pass
    return DEFAULT_MAX_WORKERS


class MissionRunner:
    """Singleton daemon. Idempotent start/stop."""

    def __init__(
        self,
        store:         Optional[MissionStore] = None,
        max_workers:   Optional[int] = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ):
        self.store         = store or MissionStore()
        self.max_workers   = max_workers if max_workers is not None else _adaptive_max_workers()
        self.poll_interval = poll_interval
        self._executor: Optional[ThreadPoolExecutor] = None
        self._poller_thread: Optional[threading.Thread] = None
        self._running   = False
        self._stopping  = False
        self._inflight: dict[str, Future] = {}
        self._on_done_callbacks: list[Callable[[Mission], None]] = []
        self._callbacks_registered = False
        self._flow = get_flow_manager()

    # ---------- lifecycle ----------

    def start(self) -> None:
        if self._running:
            return
        self._register_default_callbacks()
        # Recover orphans (missions "running" au crash précédent)
        recovered = self.store.recover_orphans()
        if recovered:
            print(f"[MissionRunner] 🔄 recovered {len(recovered)} orphan mission(s)")
        # Cleanup automatique des anciennes missions done (évite store qui grossit)
        purged = self.store.clear_done(keep_last=CLEAR_DONE_KEEP_LAST)
        if purged:
            print(f"[MissionRunner] 🧹 purged {purged} old done mission(s)")

        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix="mission-worker"
        )
        self._stopping = False
        self._running = True
        self._poller_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="mission-poller",
        )
        self._poller_thread.start()
        print(f"[MissionRunner] ▶️ started ({self.max_workers} workers)")

    def stop(self, wait: bool = True, timeout: float = 30.0) -> None:
        if not self._running:
            return
        self._stopping = True
        self._running = False
        if self._executor:
            self._executor.shutdown(wait=wait, cancel_futures=not wait)
        print("[MissionRunner] ⏹️ stopped")

    def is_running(self) -> bool:
        return self._running

    # ---------- callbacks ----------

    def on_mission_done(self, cb: Callable[[Mission], None]) -> None:
        """Enregistre un callback appelé à chaque mission completed (UI notif)."""
        self._on_done_callbacks.append(cb)

    # ---------- polling loop ----------

    def _poll_loop(self) -> None:
        while self._running:
            try:
                # Cleanup inflight terminés
                for mid in list(self._inflight.keys()):
                    f = self._inflight[mid]
                    if f.done():
                        del self._inflight[mid]

                # Si capacité libre + missions pending → submit
                free_slots = self.max_workers - len(self._inflight)
                for _ in range(free_slots):
                    if self._stopping:
                        break
                    mission = self._claim_next_runnable()
                    if mission is None:
                        break
                    if self._executor:
                        f = self._executor.submit(self._run_mission_safe, mission)
                        self._inflight[mission.id] = f

                time.sleep(self.poll_interval)
            except Exception as e:
                print(f"[MissionRunner] ⚠️ poll loop error: {e}")
                time.sleep(self.poll_interval)

    # ---------- claim ----------

    def _claim_next_runnable(self) -> Optional[Mission]:
        """
        Comme claim_next_pending mais SKIP les missions top-level dont les sub-tasks
        ne sont pas toutes terminées. Évite la concurrence top-level vs subtasks.
        """
        # Snapshot des pending triés par age
        pending = sorted(self.store.get_pending(), key=lambda m: m.created_at)
        for m in pending:
            if m.subtask_ids:
                # Top-level : ne lance que si toutes les sub-tasks sont terminales
                subs = [self.store.get(sid) for sid in m.subtask_ids]
                if any(s is None or not s.is_terminal() for s in subs):
                    continue  # sous-tâches encore en cours, attendre
            # OK : claim atomic
            claimed = self.store.get(m.id)
            if claimed and claimed.status == "pending":
                claimed.mark_running()
                self.store.update(claimed)
                return claimed
        return None

    # ---------- execution ----------

    def _run_mission_safe(self, mission: Mission) -> None:
        try:
            self._run_mission(mission)
        except Exception as e:
            mission.mark_failed(f"runner exception: {e}")
            self.store.update(mission)
            print(f"[MissionRunner] ❌ mission {mission.id[:8]}: {e}")

    def _run_mission(self, mission: Mission) -> None:
        print(f"[MissionRunner] ▶️ {mission.id[:8]}: {mission.description[:80]}")
        mission.progress = 0.4
        mission.metadata["current_step"] = "parser le contenu"
        self.store.update(mission)

        # Détermine la voie d'exécution (2 ou 4)
        voice_id = mission.voice_used
        if voice_id == 3:
            voice_id = 2  # Voie 3 = scheduler, l'exécution réelle = Voie 2 par défaut

        try:
            response_text = self._dispatch_to_voice(voice_id, mission)
            mission.mark_done(response_text)
            mission.metadata["current_step"] = "finaliser le rapport"
            self.store.update(mission)
            self._flow.mark_low_task_done(mission.id, status="done")
            self._fire_callbacks(mission)
            print(f"[MissionRunner] ✅ {mission.id[:8]} done")
        except Exception as e:
            mission.mark_failed(str(e))
            self.store.update(mission)
            self._flow.mark_low_task_done(mission.id, status="failed")
            print(f"[MissionRunner] ❌ {mission.id[:8]} failed: {e}")
            # Retry si possible (re-add comme pending)
            if mission.can_retry():
                mission.status = "pending"
                self.store.update(mission)
                print(f"[MissionRunner] 🔁 {mission.id[:8]} retry {mission.retry_count}/{mission.max_retries}")

    def _register_default_callbacks(self) -> None:
        if self._callbacks_registered:
            return
        try:
            from agent.voice_router import notify_mission_completed
            self.on_mission_done(notify_mission_completed)
            self._callbacks_registered = True
            print("[MissionRunner] 🟣[MISSION] async notification callback registered")
        except Exception as e:
            print(f"[MissionRunner] ⚠️ unable to register async callback: {e}")

    def _dispatch_to_voice(self, voice_id: int, mission: Mission) -> str:
        """Lazy import pour éviter circulaires."""
        from agent.voice_router import _get_voice

        voice = _get_voice(voice_id)
        ctx = mission.metadata.get("context", {}) or {}
        ctx["mission_id"] = mission.id
        ctx["specialists_hint"] = mission.metadata.get("specialists", [])
        response = voice.process(mission.description, context=ctx)
        if response.specialists_called:
            mission.specialists_called = response.specialists_called
        return response.text

    def _fire_callbacks(self, mission: Mission) -> None:
        for cb in self._on_done_callbacks:
            try:
                cb(mission)
            except Exception as e:
                print(f"[MissionRunner] ⚠️ callback error: {e}")


# ---------- singleton ----------

_RUNNER_SINGLETON: Optional[MissionRunner] = None


def get_runner() -> MissionRunner:
    global _RUNNER_SINGLETON
    if _RUNNER_SINGLETON is None:
        _RUNNER_SINGLETON = MissionRunner()
    return _RUNNER_SINGLETON


def reset_runner() -> None:
    global _RUNNER_SINGLETON
    if _RUNNER_SINGLETON and _RUNNER_SINGLETON.is_running():
        _RUNNER_SINGLETON.stop(wait=False)
    _RUNNER_SINGLETON = None
