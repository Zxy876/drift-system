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
 * /heartmenu
 * 显示「心悦宇宙」帮助 & 氛围菜单。
 */
public class HeartMenuCommand implements CommandExecutor {

    @SuppressWarnings("unused")
    private final BackendClient backend;
    @SuppressWarnings("unused")
    private final IntentRouter router;
    @SuppressWarnings("unused")
    private final WorldPatchExecutor world;
    @SuppressWarnings("unused")
    private final PlayerSessionManager sessions;

    public HeartMenuCommand(
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
            sender.sendMessage(ChatColor.RED + "只有玩家可以打开心悦菜单~");
            return true;
        }

        player.sendMessage(ChatColor.LIGHT_PURPLE + "========== 心悦宇宙 · 菜单 ==========");
        player.sendMessage(ChatColor.AQUA + "/level flagship_tutorial  "
                + ChatColor.GRAY + "进入「心悦文集 · 第 1 章」");
        player.sendMessage(ChatColor.AQUA + "/storynext       "
                + ChatColor.GRAY + "让故事自动向前一步");
        player.sendMessage(ChatColor.AQUA + "/saytoai <话>   "
                + ChatColor.GRAY + "对心悦的世界说话");
        player.sendMessage(ChatColor.AQUA + "直接聊天        "
                + ChatColor.GRAY + "→ 自然语言驱动世界");
        player.sendMessage(ChatColor.AQUA + "/tp2            "
                + ChatColor.GRAY + "心悦宇宙中的轻便传送");
        player.sendMessage(ChatColor.AQUA + "/time2 <day|night|tick> "
                + ChatColor.GRAY + "调节世界时间");
        player.sendMessage(ChatColor.AQUA + "/sayc <话>      "
                + ChatColor.GRAY + "用心悦风格广播一句话");
        player.sendMessage(ChatColor.LIGHT_PURPLE + "====================================");

        return true;
    }
}