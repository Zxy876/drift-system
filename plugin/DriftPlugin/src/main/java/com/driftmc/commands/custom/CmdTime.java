package com.driftmc.commands.custom;

import org.bukkit.ChatColor;
import org.bukkit.World;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import com.driftmc.backend.BackendClient;
import com.driftmc.intent.IntentRouter;
import com.driftmc.session.PlayerSessionManager;
import com.driftmc.world.WorldPatchExecutor;

/**
 * /time2 <day|night|tick>
 * 调节世界时间。
 */
public class CmdTime implements CommandExecutor {

    @SuppressWarnings("unused")
    private final BackendClient backend;
    @SuppressWarnings("unused")
    private final IntentRouter router;
    @SuppressWarnings("unused")
    private final WorldPatchExecutor world;
    @SuppressWarnings("unused")
    private final PlayerSessionManager sessions;

    public CmdTime(
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
            sender.sendMessage(ChatColor.RED + "只有玩家可以改变时间~");
            return true;
        }

        World w = player.getWorld();

        if (args.length == 0) {
            player.sendMessage(ChatColor.RED + "用法: /time2 <day|night|tick>");
            return true;
        }

        String mode = args[0].toLowerCase();

        try {
            switch (mode) {
                case "day" -> {
                    w.setTime(1000);
                    player.sendMessage(ChatColor.YELLOW + "✧ 心悦宇宙的天空亮了起来。");
                }
                case "night" -> {
                    w.setTime(13000);
                    player.sendMessage(ChatColor.DARK_BLUE + "✧ 夜色降临，适合思考数学与故事。");
                }
                default -> {
                    long tick = Long.parseLong(mode);
                    w.setTime(tick);
                    player.sendMessage(ChatColor.AQUA + "✧ 世界时间被拨动到 tick=" + tick);
                }
            }
        } catch (Exception e) {
            player.sendMessage(ChatColor.RED + "用法: /time2 <day|night|tick>");
        }

        return true;
    }
}