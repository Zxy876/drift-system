package com.driftmc.dsl;

import org.bukkit.ChatColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

public class DslRunCommand implements CommandExecutor {

    private final DslExecutor executor;

    public DslRunCommand(DslExecutor executor) {
        this.executor = executor;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command cmd, String label, String[] args) {

        if (!(sender instanceof Player p)) {
            sender.sendMessage("玩家才能使用 DSL");
            return true;
        }

        if (args.length == 0) {
            p.sendMessage(ChatColor.RED + "用法: /drift <json>");
            return true;
        }

        String json = String.join(" ", args);
        DslRuntime runtime = DslParser.parse(json);

        if (runtime == null) {
            p.sendMessage(ChatColor.RED + "DSL 解析失败");
            return true;
        }

        executor.run(p, runtime);
        return true;
    }
}