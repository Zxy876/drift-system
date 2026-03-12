package com.driftmc.dsl;

import java.util.HashMap;
import java.util.Map;

import org.bukkit.ChatColor;
import org.bukkit.entity.Player;

import com.driftmc.backend.BackendClient;
import com.driftmc.npc.NPCManager;
import com.driftmc.world.WorldPatchExecutor;

public class DslRegistry {

    private final Map<String, DslExecutor.DslAction> actions = new HashMap<>();

    public static DslRegistry createDefault(
            WorldPatchExecutor world,
            NPCManager npc,
            BackendClient backend
    ) {
        DslRegistry reg = new DslRegistry();

        // --- 文本提示 ---
        reg.register("say", (player, args) -> {
            Object t = args.get("text");
            if (t instanceof String s && !s.isEmpty()) {
                player.sendMessage(ChatColor.YELLOW + s);
            }
        });

        // --- 世界补丁 ---
        reg.register("world_patch", (player, args) -> {
            Object raw = args.get("patch");
            if (!(raw instanceof Map<?, ?> map)) return;

            Map<String, Object> cast = new HashMap<>();
            map.forEach((k, v) -> cast.put(String.valueOf(k), v));

            world.execute(player, cast);
        });

        // --- 召唤 NPC ---
        reg.register("spawn_npc", (player, args) -> {
            String name = (String) args.getOrDefault("name", "NPC");
            npc.spawnRabbit(player, name);
        });

        return reg;
    }

    public void register(String key, DslExecutor.DslAction action) {
        actions.put(key, action);
    }

    public DslExecutor.DslAction getAction(String key) {
        return actions.get(key);
    }
}