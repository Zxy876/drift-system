package com.driftmc.commands;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import com.driftmc.cinematic.CinematicController;

/**
 * Utility command for triggering cinematic test sequences.
 */
public final class CinematicCommand implements CommandExecutor {

    private final CinematicController controller;

    public CinematicCommand(CinematicController controller) {
        this.controller = controller;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        Objects.requireNonNull(sender, "sender");
        if (!(sender instanceof Player)) {
            sender.sendMessage("§c只有玩家可以使用此命令。");
            return true;
        }
        Player player = (Player) sender;
        if (controller == null) {
            player.sendMessage("§cCinematic 控制器尚未初始化。");
            return true;
        }
        if (args.length == 0) {
            showHelp(player);
            return true;
        }

        if ("test".equalsIgnoreCase(args[0])) {
            playTestSequence(player);
            return true;
        }

        showHelp(player);
        return true;
    }

    private void showHelp(Player player) {
        player.sendMessage("§b========== Cinematic 调试 ==========");
        player.sendMessage("§f/cinematic test §7- 播放示例过场动画");
        player.sendMessage("§b================================");
    }

    private void playTestSequence(Player player) {
        Map<String, Object> cinematic = new LinkedHashMap<>();
        cinematic.put("slow_motion", 0.7d);

        List<Map<String, Object>> sequence = new ArrayList<>();
        sequence.add(simpleAction("fade_out", 1.2d));
        sequence.add(simpleAction("wait", 0.35d));

        Map<String, Object> camera = new LinkedHashMap<>();
        camera.put("action", "camera");
        Map<String, Object> offset = new LinkedHashMap<>();
        offset.put("yaw", 35.0d);
        offset.put("pitch", -12.0d);
        camera.put("offset", offset);
        camera.put("hold", 0.6d);
        sequence.add(camera);

        Map<String, Object> sound = new LinkedHashMap<>();
        sound.put("action", "sound");
        sound.put("sound", "MUSIC_DISC_PIGSTEP");
        sound.put("volume", 1.2d);
        sound.put("pitch", 0.95d);
        sound.put("hold", 0.6d);
        sequence.add(sound);

        Map<String, Object> particles = new LinkedHashMap<>();
        particles.put("action", "particle");
        particles.put("particle", "FIREWORK");
        particles.put("count", 80);
        particles.put("radius", 1.6d);
        Map<String, Object> particleOffset = new LinkedHashMap<>();
        particleOffset.put("y", 1.0d);
        particles.put("offset", particleOffset);
        particles.put("hold", 0.5d);
        sequence.add(particles);

        sequence.add(simpleAction("fade_in", 1.0d));

        cinematic.put("sequence", sequence);

        controller.playSequence(player, cinematic);
        player.sendMessage("§b[Drift] 正在播放示例过场动画...");
    }

    private Map<String, Object> simpleAction(String name, double duration) {
        Map<String, Object> action = new LinkedHashMap<>();
        action.put("action", name);
        action.put("duration", duration);
        return action;
    }
}
