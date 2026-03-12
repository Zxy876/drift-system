package com.driftmc.dsl;

import java.util.Map;

import org.bukkit.entity.Player;

public class DslExecutor {

    @FunctionalInterface
    public interface DslAction {
        void execute(Player player, Map<String, Object> args);
    }

    private final DslRegistry registry;

    public DslExecutor(DslRegistry registry) {
        this.registry = registry;
    }

    public void run(Player player, DslRuntime runtime) {
        if (runtime == null) return;

        String type = runtime.getType();
        Map<String, Object> args = runtime.getArgs();

        DslAction action = registry.getAction(type);
        if (action != null) {
            action.execute(player, args);
        }
    }
}