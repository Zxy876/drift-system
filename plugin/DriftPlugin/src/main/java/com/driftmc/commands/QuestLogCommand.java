package com.driftmc.commands;

import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import com.driftmc.hud.QuestLogHud;
import com.driftmc.hud.QuestLogHud.Trigger;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;

/**
 * /questlog — display the structured quest log HUD for the caller.
 */
public final class QuestLogCommand implements CommandExecutor {

    private final QuestLogHud questLogHud;

    public QuestLogCommand(QuestLogHud questLogHud) {
        this.questLogHud = questLogHud;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(Component.text("该命令只能由玩家使用。", NamedTextColor.RED));
            return true;
        }

        if (questLogHud == null) {
            player.sendMessage(Component.text("任务日志系统尚未初始化。", NamedTextColor.RED));
            return true;
        }

        questLogHud.showQuestLog(player, Trigger.COMMAND);
        return true;
    }
}
