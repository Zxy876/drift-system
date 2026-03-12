package com.driftmc.dsl;

import org.bukkit.entity.Player;

@FunctionalInterface
public interface DslCommand {
    void execute(Player player, DslRuntime runtime, String[] args) throws Exception;
}
