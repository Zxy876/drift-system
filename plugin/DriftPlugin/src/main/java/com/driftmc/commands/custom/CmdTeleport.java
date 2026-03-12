package com.driftmc.commands.custom;

import org.bukkit.ChatColor;
import org.bukkit.Location;
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
 * /tp2 [x y z]
 * 简单传送指令（如果不填坐标，就向前方小范围位移）
 */
public class CmdTeleport implements CommandExecutor {

    @SuppressWarnings("unused")
    private final BackendClient backend;
    @SuppressWarnings("unused")
    private final IntentRouter router;
    @SuppressWarnings("unused")
    private final WorldPatchExecutor world;
    @SuppressWarnings("unused")
    private final PlayerSessionManager sessions;

    public CmdTeleport(
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
            sender.sendMessage(ChatColor.RED + "只有玩家可以传送~");
            return true;
        }

        World worldObj = player.getWorld();
        Location current = player.getLocation();

        try {
            Location target;
            if (args.length == 3) {
                double x = Double.parseDouble(args[0]);
                double y = Double.parseDouble(args[1]);
                double z = Double.parseDouble(args[2]);
                target = new Location(worldObj, x, y, z, current.getYaw(), current.getPitch());
            } else {
                // 默认向视线方向小步前进
                target = current.clone().add(
                        current.getDirection().normalize().multiply(5)
                );
            }

            player.teleport(target);
            player.sendMessage(ChatColor.GREEN + "✧ 你在心悦宇宙中轻轻「闪现」了一下。");

        } catch (Exception e) {
            player.sendMessage(ChatColor.RED + "用法: /tp2 或 /tp2 <x> <y> <z>");
        }

        return true;
    }
}