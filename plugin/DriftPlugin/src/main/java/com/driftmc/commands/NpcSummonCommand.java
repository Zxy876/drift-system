package com.driftmc.commands;

import org.bukkit.ChatColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import com.driftmc.npc.NPCManager;

public class NpcSummonCommand implements CommandExecutor {

    private final NPCManager npcManager;

    public NpcSummonCommand(NPCManager npcManager) {
        this.npcManager = npcManager;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command cmd, String label, String[] args) {

        if (!(sender instanceof Player p)) {
            sender.sendMessage("只有玩家才能召唤 NPC");
            return true;
        }

        String name = "小玉兔";
        if (args.length > 0) {
            name = String.join(" ", args);
        }

        npcManager.spawnRabbit(p, name);
        p.sendMessage(ChatColor.AQUA + "已召唤 NPC: " + name);

        return true;
    }
}