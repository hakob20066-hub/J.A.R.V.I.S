"""Tests for Phase 7.5 Safety Net components."""

from __future__ import annotations

import sys
import tempfile
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.emergency_stop import get_emergency_stop, reset_emergency_stop  # noqa: E402


def test_emergency_stop_initialization():
    """Test que l'emergency stop s'initialise correctement."""
    reset_emergency_stop()
    emergency = get_emergency_stop()
    
    status = emergency.get_status()
    assert status["active"] is True
    assert status["emergency_triggered"] is False
    assert status["hotkey_registered"] is True  # Si keyboard module disponible
    assert status["callbacks_count"] == 0


def test_emergency_stop_trigger():
    """Test le déclenchement de l'arrêt d'urgence."""
    reset_emergency_stop()
    emergency = get_emergency_stop()
    
    # Trigger manuel
    emergency._emergency_trigger()
    
    status = emergency.get_status()
    assert status["emergency_triggered"] is True
    assert emergency.is_emergency_active() is True


def test_emergency_stop_reset():
    """Test la réinitialisation de l'état d'urgence."""
    reset_emergency_stop()
    emergency = get_emergency_stop()
    
    # Trigger puis reset
    emergency._emergency_trigger()
    assert emergency.is_emergency_active() is True
    
    result = emergency.reset_emergency("test")
    assert result is True
    assert emergency.is_emergency_active() is False


def test_emergency_stop_callbacks():
    """Test l'ajout et l'exécution des callbacks."""
    reset_emergency_stop()
    emergency = get_emergency_stop()
    
    callback_called = False
    def test_callback():
        nonlocal callback_called
        callback_called = True
    
    emergency.add_callback(test_callback)
    status = emergency.get_status()
    assert status["callbacks_count"] == 1
    
    # Trigger et vérifier callback
    emergency._emergency_trigger()
    assert callback_called is True


def test_emergency_stop_audit_log():
    """Test l'audit logging des événements."""
    reset_emergency_stop()
    emergency = get_emergency_stop()
    
    # Trigger quelques événements
    emergency._emergency_trigger()
    emergency.reset_emergency("test")
    
    # Vérifier les événements récents
    events = emergency.get_recent_events(limit=5)
    assert len(events) >= 2
    
    # Vérifier structure des événements
    for event in events:
        assert "timestamp" in event
        assert "event_type" in event
        assert "message" in event
        assert "emergency_active" in event
    
    # Vérifier types d'événements
    event_types = [e["event_type"] for e in events]
    assert "EMERGENCY_TRIGGERED" in event_types
    assert "EMERGENCY_RESET" in event_types


def test_demo_mode_toggle():
    """Test le mode demo dans JarvisLive."""
    # Mock JarvisLive pour tester le mode demo
    with patch('main.JarvisUI') as mock_ui:
        from main import JarvisLive
        
        jarvis = JarvisLive(mock_ui)
        
        # Test activation/désactivation
        assert jarvis.get_demo_mode() is False
        
        jarvis.set_demo_mode(True)
        assert jarvis.get_demo_mode() is True
        
        jarvis.set_demo_mode(False)
        assert jarvis.get_demo_mode() is False


def test_action_tracking():
    """Test le tracking des actions pour rollback."""
    with patch('main.JarvisUI') as mock_ui:
        from main import JarvisLive
        
        jarvis = JarvisLive(mock_ui)
        
        # Test tracking d'action
        jarvis._track_action("keyboard", "Type hello", {"text": "hello"})
        
        last_action = jarvis.get_last_action()
        assert last_action is not None
        assert last_action["type"] == "keyboard"
        assert last_action["description"] == "Type hello"
        assert last_action["details"]["text"] == "hello"
        assert "timestamp" in last_action


def test_rollback_keyboard():
    """Test le rollback d'action keyboard."""
    with patch('main.JarvisUI') as mock_ui, \
         patch('pyautogui.hotkey') as mock_hotkey:
        from main import JarvisLive
        
        jarvis = JarvisLive(mock_ui)
        
        # Tracker une action keyboard
        jarvis._track_action("keyboard", "Type test", {"keys": "ctrl+s"})
        
        # Rollback
        result = jarvis.rollback_last_action()
        assert "rolled back" in result.lower()
        mock_hotkey.assert_called_with('ctrl', 'z')
        
        # Vérifier que l'action a été effacée
        assert jarvis.get_last_action() is None


def test_rollback_no_action():
    """Test le rollback quand aucune action n'est disponible."""
    with patch('main.JarvisUI') as mock_ui:
        from main import JarvisLive
        
        jarvis = JarvisLive(mock_ui)
        
        # Rollback sans action
        result = jarvis.rollback_last_action()
        assert "No action to rollback" in result


def test_rollback_mouse_click():
    """Test le rollback d'action mouse click (non implémenté)."""
    with patch('main.JarvisUI') as mock_ui:
        from main import JarvisLive
        
        jarvis = JarvisLive(mock_ui)
        
        # Tracker une action mouse
        jarvis._track_action("mouse_click", "Click button", {"x": 100, "y": 200})
        
        # Rollback
        result = jarvis.rollback_last_action()
        assert "cannot be rolled back" in result.lower()


def test_demo_mode_blocks_sensitive_actions():
    """Test que le mode demo bloque les actions sensibles."""
    with patch('main.JarvisUI') as mock_ui, \
         patch('main.types.FunctionResponse') as mock_response:
        from main import JarvisLive
        
        jarvis = JarvisLive(mock_ui)
        jarvis.set_demo_mode(True)
        
        # Mock function call
        mock_fc = MagicMock()
        mock_fc.name = "computer_control"
        mock_fc.args = {"action": "click", "x": 100, "y": 100}
        
        # Exécuter l'outil
        import asyncio
        result = asyncio.run(jarvis._execute_tool(mock_fc))
        
        # Vérifier que c'est en mode demo
        mock_response.assert_called_once()
        call_args = mock_response.call_args
        assert "Demo mode" in str(call_args)
        assert "not executed" in str(call_args)


def test_emergency_blocks_all_actions():
    """Test que l'état d'urgence bloque toutes les actions."""
    with patch('main.JarvisUI') as mock_ui, \
         patch('main.types.FunctionResponse') as mock_response:
        from main import JarvisLive
        
        jarvis = JarvisLive(mock_ui)
        
        # Activer l'état d'urgence
        jarvis._emergency_stop._emergency_trigger()
        
        # Mock function call
        mock_fc = MagicMock()
        mock_fc.name = "open_app"
        mock_fc.args = {"app_name": "notepad"}
        
        # Exécuter l'outil
        import asyncio
        result = asyncio.run(jarvis._execute_tool(mock_fc))
        
        # Vérifier que c'est bloqué
        mock_response.assert_called_once()
        call_args = mock_response.call_args
        assert "Emergency stop active" in str(call_args)


if __name__ == "__main__":
    # Exécuter tous les tests
    test_functions = [f for name, f in globals().items() 
                     if name.startswith('test_') and callable(f)]
    
    passed = 0
    failed = 0
    
    for test_func in test_functions:
        try:
            test_func()
            print(f"[OK] {test_func.__name__}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test_func.__name__}: {e}")
            failed += 1
    
    print(f"\n[RESULTS] Phase 7.5 Safety Tests: {passed} passed, {failed} failed")
    
    # Nettoyer
    reset_emergency_stop()
