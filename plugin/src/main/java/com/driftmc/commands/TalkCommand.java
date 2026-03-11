package com.driftmc.commands;

import org.bukkit.ChatColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import com.driftmc.intent.IntentRouter;
import com.driftmc.scene.RuleEventBridge;

public class TalkCommand implements CommandExecutor {

    @SuppressWarnings("unused")
    private final IntentRouter router;
    @SuppressWarnings("unused")
    private final RuleEventBridge ruleEvents;

    public TalkCommand(IntentRouter router, RuleEventBridge ruleEvents) {
        this.router = router;
        this.ruleEvents = ruleEvents;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command cmd, String label, String[] args) {

        if (!(sender instanceof Player p)) {
            sender.sendMessage("玩家才能使用此命令");
            return true;
        }

        if (args.length == 0) {
            p.sendMessage(ChatColor.RED + "用法: /talk <内容>");
            return true;
        }

        String msg = String.join(" ", args);
        // 统一语言入口：复用玩家聊天事件链路
        // PlayerChatListener -> IntentRouter2 -> IntentDispatcher2
        p.chat(msg);

        return true;
    }
}