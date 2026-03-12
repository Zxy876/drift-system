package com.driftmc.session;

import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.bukkit.entity.Player;

import com.driftmc.tutorial.TutorialState;

public class PlayerSessionManager {

    public enum Mode {
        NORMAL,
        TUTORIAL,
        AI_CHAT
    }

    private final Map<UUID, Mode> modeMap = new ConcurrentHashMap<>();
    private final Set<UUID> completedTutorial = ConcurrentHashMap.newKeySet();
    private final Set<UUID> tutorialCompletionSignals = ConcurrentHashMap.newKeySet();
    private final Set<UUID> tutorialExited = ConcurrentHashMap.newKeySet();
    private final Map<UUID, TutorialState> tutorialStates = new ConcurrentHashMap<>();

    public PlayerSessionManager() {
    }

    public Mode getMode(Player player) {
        return modeMap.getOrDefault(player.getUniqueId(), Mode.NORMAL);
    }

    public void setMode(Player player, Mode mode) {
        if (player == null || mode == null) {
            return;
        }
        if (mode == Mode.NORMAL) {
            modeMap.remove(player.getUniqueId());
        } else {
            modeMap.put(player.getUniqueId(), mode);
        }
    }

    public TutorialState getTutorialState(Player player) {
        if (player == null) {
            return TutorialState.INACTIVE;
        }
        return getTutorialState(player.getUniqueId());
    }

    public TutorialState getTutorialState(UUID playerId) {
        if (playerId == null) {
            return TutorialState.INACTIVE;
        }
        TutorialState state = tutorialStates.get(playerId);
        if (state != null) {
            return state;
        }
        if (completedTutorial.contains(playerId)) {
            return TutorialState.COMPLETE;
        }
        return TutorialState.INACTIVE;
    }

    public void setTutorialState(Player player, TutorialState state) {
        if (player == null || state == null) {
            return;
        }
        setTutorialState(player.getUniqueId(), state);
    }

    public void setTutorialState(UUID playerId, TutorialState state) {
        if (playerId == null || state == null) {
            return;
        }
        if (state == TutorialState.INACTIVE) {
            tutorialStates.remove(playerId);
        } else {
            tutorialStates.put(playerId, state);
        }
    }

    public void clearTutorialState(Player player) {
        if (player == null) {
            return;
        }
        tutorialStates.remove(player.getUniqueId());
    }

    public boolean hasUnlockedTutorialStep(Player player, TutorialState required) {
        if (required == null) {
            return true;
        }
        return getTutorialState(player).hasUnlocked(required);
    }

    public boolean isAiChat(Player player) {
        return getMode(player) == Mode.AI_CHAT;
    }

    public boolean isTutorial(Player player) {
        return getMode(player) == Mode.TUTORIAL;
    }

    public void setTutorial(Player player, boolean active) {
        if (player == null) {
            return;
        }
        if (active) {
            setMode(player, Mode.TUTORIAL);
        } else {
            setMode(player, Mode.NORMAL);
        }
    }

    public void markTutorialStarted(Player player) {
        if (player == null) {
            return;
        }
        setMode(player, Mode.TUTORIAL);
    }

    public void markTutorialComplete(Player player) {
        if (player == null) {
            return;
        }
        tutorialCompletionSignals.remove(player.getUniqueId());
        completedTutorial.add(player.getUniqueId());
        setMode(player, Mode.NORMAL);
        tutorialStates.put(player.getUniqueId(), TutorialState.COMPLETE);
    }

    public void markTutorialExited(Player player) {
        if (player == null) {
            return;
        }
        tutorialExited.add(player.getUniqueId());
    }

    public boolean hasExitedTutorial(Player player) {
        if (player == null) {
            return false;
        }
        return tutorialExited.contains(player.getUniqueId());
    }

    public boolean hasExitedTutorial(UUID playerId) {
        if (playerId == null) {
            return false;
        }
        return tutorialExited.contains(playerId);
    }

    public void clearTutorialExit(Player player) {
        if (player == null) {
            return;
        }
        tutorialExited.remove(player.getUniqueId());
    }

    public boolean hasCompletedTutorial(Player player) {
        if (player == null) {
            return false;
        }
        return completedTutorial.contains(player.getUniqueId());
    }

    public boolean hasCompletedTutorial(UUID playerId) {
        if (playerId == null) {
            return false;
        }
        return completedTutorial.contains(playerId);
    }

    public void markTutorialCompletionSignal(Player player) {
        if (player == null) {
            return;
        }
        tutorialCompletionSignals.add(player.getUniqueId());
    }

    public boolean hasTutorialCompletionSignal(Player player) {
        if (player == null) {
            return false;
        }
        return tutorialCompletionSignals.contains(player.getUniqueId());
    }

    public boolean hasTutorialCompletionSignal(UUID playerId) {
        if (playerId == null) {
            return false;
        }
        return tutorialCompletionSignals.contains(playerId);
    }

    public void clearTutorialCompletionSignal(Player player) {
        if (player == null) {
            return;
        }
        tutorialCompletionSignals.remove(player.getUniqueId());
    }

    public void reset(Player player) {
        if (player == null) {
            return;
        }
        UUID id = player.getUniqueId();
        modeMap.remove(id);
        completedTutorial.remove(id);
        tutorialStates.remove(id);
        tutorialCompletionSignals.remove(id);
        tutorialExited.remove(id);
    }
}
