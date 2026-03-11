package com.driftmc.commands;

import org.bukkit.ChatColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import com.driftmc.backend.BackendClient;
import com.driftmc.intent.IntentRouter;
import com.driftmc.session.PlayerSessionManager;
import com.driftmc.world.WorldPatchExecutor;

/**
 * /levels
 * 发布版关卡列表面板。
 */
public class LevelsCommand implements CommandExecutor {

    @SuppressWarnings("unused")
    private final BackendClient backend;
    @SuppressWarnings("unused")
    private final IntentRouter router;
    @SuppressWarnings("unused")
    private final WorldPatchExecutor world;
    @SuppressWarnings("unused")
    private final PlayerSessionManager sessions;

    public LevelsCommand(
            BackendClient backend,
            IntentRouter router,
            WorldPatchExecutor world,
            PlayerSessionManager sessions) {
        this.backend = backend;
        this.router = router;
        this.world = world;
        this.sessions = sessions;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command cmd, String label, String[] args) {

        if (!(sender instanceof Player player)) {
            sender.sendMessage(ChatColor.RED + "只有玩家可以查看心悦宇宙关卡~");
            return true;
        }

        player.sendMessage(ChatColor.LIGHT_PURPLE + "====== 心悦宇宙 · Levels ======");
        player.sendMessage(ChatColor.AQUA + "flagship_01 " + ChatColor.GRAY + "→ 昆明湖启程");
        player.sendMessage(ChatColor.AQUA + "flagship_02 " + ChatColor.GRAY + "→ 湖岸市集");
        player.sendMessage(ChatColor.AQUA + "flagship_03 " + ChatColor.GRAY + "→ 夜色远航");
        player.sendMessage("");
        player.sendMessage(ChatColor.YELLOW + "推荐命令:");
        player.sendMessage(ChatColor.AQUA + "/drift load flagship_01 " + ChatColor.GRAY + "→ 加载关卡");
        player.sendMessage(ChatColor.AQUA + "/drift spawn " + ChatColor.GRAY + "→ 生成场景片段");
        player.sendMessage(ChatColor.GRAY + "旧命令 /levels /level /spawnfragment 仍可使用");
        player.sendMessage(ChatColor.LIGHT_PURPLE + "================================");

        return true;
    }
}