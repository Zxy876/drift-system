package com.driftmc.commands;

import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import com.driftmc.hud.RecommendationHud;
import com.driftmc.hud.RecommendationHud.Trigger;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;

/**
 * /recommend — manually refresh StoryGraph recommendations for the caller.
 */
public final class RecommendCommand implements CommandExecutor {

    private final RecommendationHud hud;

    public RecommendCommand(RecommendationHud hud) {
        this.hud = hud;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(Component.text("该命令只能由玩家使用。", NamedTextColor.RED));
            return true;
        }

        if (hud == null) {
            player.sendMessage(Component.text("推荐系统尚未初始化。", NamedTextColor.RED));
            return true;
        }

        hud.showRecommendations(player, Trigger.COMMAND);
        return true;
    }
}
