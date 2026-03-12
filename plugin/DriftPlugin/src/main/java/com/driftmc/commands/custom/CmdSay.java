package com.driftmc.commands.custom;

import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;

import com.driftmc.backend.BackendClient;
import com.driftmc.intent.IntentRouter;
import com.driftmc.session.PlayerSessionManager;
import com.driftmc.world.WorldPatchExecutor;

/**
 * /sayc <内容>
 * 用「心悦宇宙风格」在服务器广播一句话。
 */
public class CmdSay implements CommandExecutor {

    @SuppressWarnings("unused")
    private final BackendClient backend;
    @SuppressWarnings("unused")
    private final IntentRouter router;
    @SuppressWarnings("unused")
    private final WorldPatchExecutor world;
    @SuppressWarnings("unused")
    private final PlayerSessionManager sessions;

    public CmdSay(
            BackendClient backend,
            IntentRouter router,
            WorldPatchExecutor world,
            PlayerSessionManager sessions
    ) {
        this.backend = backend;
        this.router = router;
        this.world = world;
        this.sessions = sessions;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command cmd, String label, String[] args) {

        if (args.length == 0) {
            sender.sendMessage(ChatColor.RED + "用法: /sayc <内容>");
            return true;
        }

        String msg = String.join(" ", args);
        String prefix = ChatColor.LIGHT_PURPLE + "【心悦广播】 " + ChatColor.WHITE;

        Bukkit.getOnlinePlayers().forEach(p ->
                p.sendMessage(prefix + msg)
        );
        sender.sendMessage(ChatColor.GREEN + "✔ 已以心悦宇宙的名义广播。");

        return true;
    }
}