package com.driftmc.tutorial;

import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Level;

import org.bukkit.ChatColor;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;

import com.driftmc.session.PlayerSessionManager;

/**
 * Lightweight state tracker that keeps the plugin aligned with backend tutorial
 * progress.
 */
public class TutorialStateMachine {

    private final Plugin plugin;
    private final PlayerSessionManager sessions;
    private final Map<UUID, TutorialState> stateByPlayer = new ConcurrentHashMap<>();

    public TutorialStateMachine(Plugin plugin, PlayerSessionManager sessions) {
        this.plugin = Objects.requireNonNull(plugin, "plugin");
        this.sessions = sessions;
    }

    public TutorialState getState(Player player) {
        if (player == null) {
            return TutorialState.INACTIVE;
        }
        return getState(player.getUniqueId());
    }

    public TutorialState getState(UUID playerId) {
        if (playerId == null) {
            return TutorialState.INACTIVE;
        }
        TutorialState state = stateByPlayer.get(playerId);
        if (state != null) {
            return state;
        }
        if (sessions != null && sessions.hasCompletedTutorial(playerId)) {
            return TutorialState.COMPLETE;
        }
        return TutorialState.INACTIVE;
    }

    public void start(Player player) {
        setState(player, TutorialState.WELCOME, "start");
    }

    public void setState(Player player, TutorialState state) {
        setState(player, state, "set");
    }

    public void setState(Player player, TutorialState state, String reason) {
        if (player == null || state == null || state == TutorialState.INACTIVE) {
            return;
        }
        UUID playerId = player.getUniqueId();
        TutorialState current = getState(playerId);
        if (current == TutorialState.COMPLETE) {
            if (state == TutorialState.COMPLETE) {
                return;
            }
            return;
        }
        if (!state.hasUnlocked(current)) {
            return;
        }
        stateByPlayer.put(playerId, state);
        if (sessions != null) {
            sessions.setTutorialState(player, state);
        }
        plugin.getLogger().log(Level.INFO,
                "[TutorialStateMachine] {0} -> {1} ({2})",
                new Object[] { player.getName(), state, reason });
    }

    public void reset(Player player) {
        if (player == null) {
            return;
        }
        stateByPlayer.remove(player.getUniqueId());
        if (sessions != null) {
            sessions.clearTutorialState(player);
        }
    }

    public boolean isComplete(Player player) {
        if (player == null) {
            return false;
        }
        return getState(player) == TutorialState.COMPLETE;
    }

    public boolean markCompleted(Player player) {
        return markCompleted(player, "completed");
    }

    public boolean markCompleted(Player player, String reason) {
        if (player == null) {
            return false;
        }
        TutorialState current = getState(player);
        if (current == TutorialState.COMPLETE) {
            return false;
        }
        String appliedReason = (reason == null || reason.isBlank()) ? "completed" : reason;
        setState(player, TutorialState.COMPLETE, appliedReason);
        return true;
    }

    @Deprecated
    public void markComplete(Player player, String reason) {
        markCompleted(player, reason);
    }

    public void handleStepResult(Player player, TutorialState completed, TutorialState next) {
        if (player == null) {
            return;
        }
        if (completed != null) {
            setState(player, completed, "completed" + (next != null ? " -> " + next : ""));
        }
        if (next != null) {
            setState(player, next, "next_step");
        } else if (completed == TutorialState.VIEW_MAP || completed == TutorialState.COMPLETE) {
            markCompleted(player, "final-step");
        }
    }

    public void syncFromPatch(Player player, Map<String, Object> patch) {
        if (player == null || patch == null || patch.isEmpty()) {
            return;
        }
        TutorialState state = extractStateFromPatch(patch);
        if (state != null) {
            setState(player, state, "world_patch");
        }
    }

    public boolean ensureUnlocked(Player player, TutorialState required, String lockedMessage) {
        if (player == null) {
            return false;
        }
        if (sessions == null || !sessions.isTutorial(player)) {
            return true;
        }
        TutorialState current = getState(player);
        if (current.hasUnlocked(required)) {
            return true;
        }
        String message = lockedMessage != null && !lockedMessage.isBlank()
                ? lockedMessage
                : defaultLockedMessage(required);
        player.sendMessage(ChatColor.YELLOW + message);
        player.sendMessage(ChatColor.GRAY + "当前阶段: " + current.getDisplayName());
        return false;
    }

    private String defaultLockedMessage(TutorialState required) {
        if (required == null) {
            return "该功能已开放";
        }
        return "请先完成教学步骤：" + required.getDisplayName() + " —— " + required.getRequirementHint();
    }

    private TutorialState extractStateFromPatch(Map<String, Object> patch) {
        Object variablesObj = patch.get("variables");
        TutorialState fromVariables = TutorialState.fromObject(variablesObj);
        if (fromVariables != null && fromVariables != TutorialState.INACTIVE) {
            return fromVariables;
        }
        for (Map.Entry<String, Object> entry : patch.entrySet()) {
            Object value = entry.getValue();
            TutorialState state = TutorialState.fromObject(value);
            if (state != null && state != TutorialState.INACTIVE) {
                return state;
            }
        }
        return null;
    }
}
