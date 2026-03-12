package com.driftmc.commands;

import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import com.driftmc.npc.NPCManager;

public class NpcMasterCommand implements CommandExecutor {

    private final NPCManager npcManager;

    public NpcMasterCommand(NPCManager npcManager) {
        this.npcManager = npcManager;
    }

    @Override
    public boolean onCommand(CommandSender sender,
                             Command command,
                             String label,
                             String[] args) {

        if (!(sender instanceof Player player)) {
            sender.sendMessage("玩家才能使用 npc 指令");
            return true;
        }

        if (args.length == 0) {
            player.sendMessage("§e用法: /npc <summon|remove|follow|stay>");
            return true;
        }

        switch (args[0].toLowerCase()) {

            case "summon":
                return new NpcSummonCommand(npcManager).onCommand(sender, command, label, shiftArgs(args));

            // 拓展项：未来你会用到
            case "remove":
            case "follow":
            case "stay":
                player.sendMessage("§c这个功能我们后面再做！");
                return true;

            default:
                player.sendMessage("§c未知 npc 子命令");
                return true;
        }
    }

    private String[] shiftArgs(String[] args) {
        if (args.length <= 1) return new String[0];
        String[] r = new String[args.length - 1];
        System.arraycopy(args, 1, r, 0, args.length - 1);
        return r;
    }
}