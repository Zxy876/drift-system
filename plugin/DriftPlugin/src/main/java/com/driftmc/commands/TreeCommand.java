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
 * /tree
 * 暂时作为「故事树说明」，不强依赖后端，保证一定能编译通过。
 */
public class TreeCommand implements CommandExecutor {

    @SuppressWarnings("unused")
    private final BackendClient backend;
    @SuppressWarnings("unused")
    private final IntentRouter router;
    @SuppressWarnings("unused")
    private final WorldPatchExecutor world;
    @SuppressWarnings("unused")
    private final PlayerSessionManager sessions;

    public TreeCommand(
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

        if (!(sender instanceof Player player)) {
            sender.sendMessage(ChatColor.RED + "只有玩家可以查看心悦事件树~");
            return true;
        }

        player.sendMessage(ChatColor.LIGHT_PURPLE + "====== 心悦事件树 ======");
        player.sendMessage(ChatColor.GRAY + "· 每一次 /advance 或自然语言对话，都会在心悦的树上生长一个节点。");
        player.sendMessage(ChatColor.GRAY + "· 未来可以在 Web/可视化界面查看完整树结构。");
        player.sendMessage(ChatColor.DARK_AQUA + "当前版本：树结构在后端内存中维护，命令仅作说明用。");
        player.sendMessage(ChatColor.LIGHT_PURPLE + "========================");

        return true;
    }
}