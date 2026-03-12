package com.driftmc.cinematic;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Level;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.Particle;
import org.bukkit.Sound;
import org.bukkit.World;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.potion.PotionEffect;
import org.bukkit.potion.PotionEffectType;
import org.bukkit.util.Vector;

import com.driftmc.world.WorldPatchExecutor;

/**
 * Coordinates cinematic playback for scripted story beats.
 */
public final class CinematicController {

    private final JavaPlugin plugin;
    private final WorldPatchExecutor world;
    private final Map<UUID, CinematicPlayback> active = new ConcurrentHashMap<>();

    public CinematicController(JavaPlugin plugin, WorldPatchExecutor world) {
        this.plugin = plugin;
        this.world = world;
    }

    public void playSequence(Player player, Map<String, Object> config) {
        if (player == null || config == null || config.isEmpty()) {
            return;
        }
        Object sequenceObj = config.get("sequence");
        List<?> sequenceRaw = sequenceObj instanceof List<?> list ? list : Collections.emptyList();
        if (sequenceRaw.isEmpty()) {
            return;
        }

        List<CinematicAction> actions = buildActions(sequenceRaw);
        if (actions.isEmpty()) {
            return;
        }

        UUID playerId = player.getUniqueId();
        CinematicPlayback previous = active.remove(playerId);
        if (previous != null) {
            previous.cancel();
        }

        CinematicContext context = new CinematicContext(plugin, world, player);
        double slowMotion = number(config.get("slow_motion"), 1.0d);
        if (slowMotion > 0.0d && slowMotion < 0.999d) {
            context.applySlowMotion(slowMotion);
        }

        CinematicPlayback playback = new CinematicPlayback(playerId, context, actions);
        active.put(playerId, playback);
        playback.start();
    }

    private List<CinematicAction> buildActions(List<?> definitions) {
        List<CinematicAction> actions = new ArrayList<>();
        for (Object entry : definitions) {
            CinematicAction action = parseAction(entry);
            if (action != null) {
                actions.add(action);
            }
        }
        return actions;
    }

    private CinematicAction parseAction(Object definition) {
        if (definition instanceof CinematicAction action) {
            return action;
        }
        if (definition instanceof Map<?, ?> map) {
            CinematicAction action = parseActionFromMap(toStringKeyMap(map));
            if (action == null) {
                log(Level.FINE, "[Cinematic] Unsupported action map: {0}", map);
            }
            return action;
        }
        if (definition instanceof String str) {
                String cleaned = str.trim();
                if (cleaned.isEmpty()) {
                    log(Level.FINE, "[Cinematic] Unsupported action string: {0}", str);
                    return null;
                }
                CinematicAction action = parseActionFromString(cleaned);
            return action;
        }
        return null;
    }

    private CinematicAction parseActionFromString(String spec) {
        if (spec == null) {
            return null;
        }
        String trimmed = spec.trim();
            if (trimmed.isEmpty()) {
                log(Level.FINE, "[Cinematic] Empty action spec");
                return null;
            }
        String lowered = trimmed.toLowerCase(Locale.ROOT);
        int paren = lowered.indexOf('(');
        String name = paren >= 0 ? lowered.substring(0, paren) : lowered;
        String args = "";
        if (paren >= 0 && lowered.endsWith(")")) {
            args = trimmed.substring(paren + 1, trimmed.length() - 1).trim();
        }
        name = name.replace('-', '_');
        double value = parseFirstNumber(args, 0.0d);
        return switch (name) {
            case "fade_out" -> new FadeAction(true, toTicks(value > 0 ? value : 1.0d));
            case "fade_in" -> new FadeAction(false, toTicks(value > 0 ? value : 1.0d));
            case "wait", "delay", "sleep" -> new WaitAction(toTicks(value > 0 ? value : 0.5d));
            default -> null;
        };
    }

    private CinematicAction parseActionFromMap(Map<String, Object> data) {
        if (data.isEmpty()) {
            return null;
        }
        String type = string(data.remove("action"));
        if (type == null) {
            type = string(data.remove("type"));
        }
        if (type == null && data.size() == 1) {
            Map.Entry<String, Object> entry = data.entrySet().iterator().next();
            type = entry.getKey();
            if (entry.getValue() instanceof Map<?, ?> mapValue) {
                data = toStringKeyMap(mapValue);
            } else {
                data = new LinkedHashMap<>();
                data.put("value", entry.getValue());
            }
        }
        if (type == null) {
            return null;
        }

        String normalized = type.toLowerCase(Locale.ROOT).replace('-', '_');
        return switch (normalized) {
            case "fade", "fade_out", "fadein", "fade_in" -> {
                boolean fadeOut = normalized.contains("out") || "out".equals(string(data.get("mode")));
                if (normalized.equals("fade")) {
                    String mode = string(data.get("mode"));
                    if (mode != null) {
                        fadeOut = mode.toLowerCase(Locale.ROOT).contains("out");
                    }
                }
                double seconds = number(firstNonNull(
                    data.remove("duration"),
                    data.remove("seconds"),
                    data.remove("time"),
                    data.remove("value")),
                    1.0d);
                yield new FadeAction(fadeOut, toTicks(Math.max(seconds, 0.1d)));
            }
            case "wait", "delay", "sleep" -> {
                double seconds = number(firstNonNull(
                    data.remove("duration"),
                    data.remove("seconds"),
                    data.remove("time"),
                    data.remove("value")),
                    0.5d);
                yield new WaitAction(toTicks(Math.max(seconds, 0.05d)));
            }
            case "teleport", "tp" -> {
                Map<String, Object> teleport = resolveTeleportTarget(data);
                if (teleport.isEmpty()) {
                    yield null;
                }
                long delay = toTicks(number(firstNonNull(
                        data.remove("hold"),
                        data.remove("wait_after"),
                        data.remove("delay")), 0.25d));
                yield new TeleportAction(teleport, Math.max(delay, 1L));
            }
            case "camera", "camera_pan", "camera_pan_to", "look_at" -> {
                Map<String, Object> lookAt = toStringKeyMap(data.get("look_at"));
                Map<String, Object> offset = toStringKeyMap(data.get("offset"));
                Map<String, Object> position = toStringKeyMap(data.get("position"));
                Double yaw = optionalNumber(data.get("yaw"));
                Double pitch = optionalNumber(data.get("pitch"));
                if (lookAt.isEmpty() && offset.isEmpty() && position.isEmpty() && yaw == null && pitch == null) {
                    yield null;
                }
                long hold = toTicks(number(firstNonNull(
                        data.remove("hold"),
                        data.remove("wait_after"),
                        data.remove("duration")), 0.25d));
                yield new CameraAction(lookAt, offset, position, yaw, pitch, Math.max(hold, 1L));
            }
            case "sound", "play_sound", "music" -> {
                String sound = string(firstNonNull(
                    data.remove("sound"),
                    data.remove("id"),
                    data.remove("name"),
                    data.remove("type")));
                if (sound == null || sound.isEmpty()) {
                    yield null;
                }
                double volume = number(data.remove("volume"), 1.0d);
                double pitch = number(data.remove("pitch"), 1.0d);
                Map<String, Object> offset = toStringKeyMap(data.get("offset"));
                long hold = toTicks(number(firstNonNull(
                        data.remove("hold"),
                        data.remove("wait_after")), 0.15d));
                yield new SoundAction(sound, (float) volume, (float) pitch, offset, Math.max(hold, 1L));
            }
            case "particle", "particles" -> {
                String particle = string(firstNonNull(
                    data.remove("particle"),
                    data.remove("type")));
                if (particle == null || particle.isEmpty()) {
                    yield null;
                }
                int count = (int) Math.max(1, Math.round(number(data.remove("count"), 30))); 
                double speed = number(data.remove("speed"), 0.05d);
                Map<String, Object> offset = toStringKeyMap(data.get("offset"));
                Map<String, Object> spread = toStringKeyMap(data.get("spread"));
                double radius = number(data.remove("radius"), 0.0d);
                long hold = toTicks(number(firstNonNull(
                        data.remove("hold"),
                        data.remove("wait_after")), 0.15d));
                yield new ParticleAction(particle, count, speed, offset, spread, radius, Math.max(hold, 1L));
            }
            case "world", "patch", "world_patch" -> {
                Map<String, Object> operations = extractWorldOperations(data);
                if (operations.isEmpty()) {
                    yield null;
                }
                long hold = toTicks(number(firstNonNull(
                        data.remove("hold"),
                        data.remove("wait_after")), 0.1d));
                yield new WorldPatchAction(operations, Math.max(hold, 1L));
            }
            default -> null;
        };
    }

    private Map<String, Object> extractWorldOperations(Map<String, Object> source) {
        Map<String, Object> operations = toStringKeyMap(source.get("operations"));
        if (!operations.isEmpty()) {
            return operations;
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : source.entrySet()) {
            String key = entry.getKey();
            if (key == null) {
                continue;
            }
            String lower = key.toLowerCase(Locale.ROOT);
            if (lower.equals("action") || lower.equals("type") || lower.startsWith("wait") || lower.equals("hold")
                || lower.equals("duration") || lower.equals("seconds")) {
                continue;
            }
            result.put(key, entry.getValue());
        }
        return result;
    }

    private Map<String, Object> resolveTeleportTarget(Map<String, Object> data) {
        Map<String, Object> teleport = toStringKeyMap(data.get("teleport"));
        if (!teleport.isEmpty()) {
            return teleport;
        }
        Map<String, Object> target = toStringKeyMap(data.get("target"));
        if (!target.isEmpty()) {
            return target;
        }
        if (data.containsKey("x") || data.containsKey("y") || data.containsKey("z")) {
            Map<String, Object> manual = new LinkedHashMap<>();
            manual.put("x", data.get("x"));
            manual.put("y", data.get("y"));
            manual.put("z", data.get("z"));
            if (data.containsKey("yaw")) {
                manual.put("yaw", data.get("yaw"));
            }
            if (data.containsKey("pitch")) {
                manual.put("pitch", data.get("pitch"));
            }
            String mode = string(data.get("mode"));
            if (mode != null) {
                manual.put("mode", mode);
            }
            return manual;
        }
        return Collections.emptyMap();
    }

    private Map<String, Object> toStringKeyMap(Object candidate) {
        if (!(candidate instanceof Map<?, ?> raw)) {
            return Collections.emptyMap();
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : raw.entrySet()) {
            if (entry.getKey() instanceof String key) {
                result.put(key, entry.getValue());
            }
        }
        return result;
    }

    private Object firstNonNull(Object... values) {
        for (Object value : values) {
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private String string(Object value) {
        if (value instanceof String str) {
            return str;
        }
        if (value != null) {
            return value.toString();
        }
        return null;
    }

    private double number(Object value, double defaultValue) {
        Double result = optionalNumber(value);
        return result != null ? result : defaultValue;
    }

    private Double optionalNumber(Object value) {
        if (value instanceof Number num) {
            return num.doubleValue();
        }
        if (value instanceof String str) {
            if (str.isBlank()) {
                return null;
            }
            try {
                return Double.valueOf(str);
            } catch (NumberFormatException ignored) {
                return null;
            }
        }
        return null;
    }

    private double parseFirstNumber(String args, double defaultValue) {
        if (args == null || args.isEmpty()) {
            return defaultValue;
        }
        String primary = args.split(",", 2)[0].trim();
        if (primary.isEmpty()) {
            return defaultValue;
        }
        Double parsed = optionalNumber(primary);
        return parsed != null ? parsed : defaultValue;
    }

    private long toTicks(double seconds) {
        return Math.max(1L, Math.round(seconds * 20.0d));
    }

    private void log(Level level, String message) {
        if (plugin.getLogger().isLoggable(level)) {
            plugin.getLogger().log(level, message);
        }
    }

    private void log(Level level, String message, Object arg) {
        if (plugin.getLogger().isLoggable(level)) {
            plugin.getLogger().log(level, message, arg);
        }
    }

    private final class CinematicPlayback {

        private final UUID playerId;
        private final CinematicContext context;
        private final List<CinematicAction> actions;
        private int index;
        private boolean cancelled;

        CinematicPlayback(UUID playerId, CinematicContext context, List<CinematicAction> actions) {
            this.playerId = playerId;
            this.context = context;
            this.actions = new ArrayList<>(actions);
        }

        void start() {
            runNext();
        }

        void cancel() {
            cancelled = true;
            finish();
        }

        private void runNext() {
            if (cancelled) {
                finish();
                return;
            }
            Player player = context.getPlayer();
            if (player == null || !player.isOnline()) {
                finish();
                return;
            }
            if (index >= actions.size()) {
                finish();
                return;
            }
            CinematicAction current = actions.get(index++);
            Bukkit.getScheduler().runTask(plugin, () -> {
                try {
                    current.play(context, () -> Bukkit.getScheduler().runTask(plugin, this::runNext));
                } catch (Throwable t) {
                    plugin.getLogger().log(Level.WARNING, "[Cinematic] Action execution failed", t);
                    Bukkit.getScheduler().runTask(plugin, this::runNext);
                }
            });
        }

        private void finish() {
            context.clearSlowMotion();
            active.remove(playerId, this);
        }
    }

    private static final class FadeAction implements CinematicAction {

        private final boolean fadeOut;
        private final long ticks;

        FadeAction(boolean fadeOut, long ticks) {
            this.fadeOut = fadeOut;
            this.ticks = Math.max(1L, ticks);
        }

        @Override
        public void play(CinematicContext context, Runnable onComplete) {
            Player player = context.getPlayer();
            if (player == null) {
                onComplete.run();
                return;
            }
            JavaPlugin plugin = context.getPlugin();
            if (fadeOut) {
                player.addPotionEffect(new PotionEffect(PotionEffectType.BLINDNESS, (int) ticks, 1, false, false, false));
                Bukkit.getScheduler().runTaskLater(plugin, onComplete, ticks);
            } else {
                Bukkit.getScheduler().runTaskLater(plugin, () -> {
                    Player refreshed = context.getPlayer();
                    if (refreshed != null) {
                        refreshed.removePotionEffect(PotionEffectType.BLINDNESS);
                    }
                    onComplete.run();
                }, ticks);
            }
        }
    }

    private static final class WaitAction implements CinematicAction {

        private final long ticks;

        WaitAction(long ticks) {
            this.ticks = Math.max(1L, ticks);
        }

        @Override
        public void play(CinematicContext context, Runnable onComplete) {
            Bukkit.getScheduler().runTaskLater(context.getPlugin(), onComplete, ticks);
        }
    }

    private static final class TeleportAction implements CinematicAction {

        private final Map<String, Object> teleport;
        private final long holdTicks;

        TeleportAction(Map<String, Object> teleport, long holdTicks) {
            this.teleport = new LinkedHashMap<>(teleport);
            this.holdTicks = Math.max(1L, holdTicks);
        }

        @Override
        public void play(CinematicContext context, Runnable onComplete) {
            Player player = context.getPlayer();
            if (player == null) {
                onComplete.run();
                return;
            }
            Map<String, Object> patch = new LinkedHashMap<>();
            patch.put("teleport", new LinkedHashMap<>(teleport));
            context.getWorldExecutor().execute(player, patch);
            Bukkit.getScheduler().runTaskLater(context.getPlugin(), onComplete, holdTicks);
        }
    }

    private static final class CameraAction implements CinematicAction {

        private final Map<String, Object> lookAt;
        private final Map<String, Object> offset;
        private final Map<String, Object> position;
        private final Double yaw;
        private final Double pitch;
        private final long holdTicks;

        CameraAction(Map<String, Object> lookAt,
                     Map<String, Object> offset,
                     Map<String, Object> position,
                     Double yaw,
                     Double pitch,
                     long holdTicks) {
            this.lookAt = new LinkedHashMap<>(lookAt);
            this.offset = new LinkedHashMap<>(offset);
            this.position = new LinkedHashMap<>(position);
            this.yaw = yaw;
            this.pitch = pitch;
            this.holdTicks = Math.max(1L, holdTicks);
        }

        @Override
        public void play(CinematicContext context, Runnable onComplete) {
            Player player = context.getPlayer();
            if (player == null) {
                onComplete.run();
                return;
            }
            Location location = player.getLocation().clone();
            applyPosition(location, position);
            applyYawPitch(location, yaw, pitch);
            applyOffset(location, offset);
            applyLookAt(location, lookAt);
            player.teleport(location);
            Bukkit.getScheduler().runTaskLater(context.getPlugin(), onComplete, holdTicks);
        }

        private void applyPosition(Location location, Map<String, Object> data) {
            if (data.isEmpty()) {
                return;
            }
            String mode = null;
            if (data.containsKey("mode")) {
                mode = data.get("mode").toString();
            }
            double x = getDouble(data.get("x"), 0.0d);
            double y = getDouble(data.get("y"), 0.0d);
            double z = getDouble(data.get("z"), 0.0d);
            if ("absolute".equalsIgnoreCase(mode)) {
                location.setX(x);
                location.setY(y);
                location.setZ(z);
            } else {
                location.add(x, y, z);
            }
        }

        private void applyYawPitch(Location location, Double yaw, Double pitch) {
            if (yaw != null) {
                location.setYaw(yaw.floatValue());
            }
            if (pitch != null) {
                location.setPitch(pitch.floatValue());
            }
        }

        private void applyOffset(Location location, Map<String, Object> data) {
            if (data.isEmpty()) {
                return;
            }
            double yawOffset = getDouble(data.get("yaw"), 0.0d);
            double pitchOffset = getDouble(data.get("pitch"), 0.0d);
            double dx = getDouble(data.get("x"), 0.0d);
            double dy = getDouble(data.get("y"), 0.0d);
            double dz = getDouble(data.get("z"), 0.0d);
            location.add(dx, dy, dz);
            if (yawOffset != 0.0d) {
                location.setYaw(location.getYaw() + (float) yawOffset);
            }
            if (pitchOffset != 0.0d) {
                location.setPitch(location.getPitch() + (float) pitchOffset);
            }
        }

        private void applyLookAt(Location location, Map<String, Object> data) {
            if (data.isEmpty()) {
                return;
            }
            double targetX = getDouble(data.get("x"), location.getX());
            double targetY = getDouble(data.get("y"), location.getY());
            double targetZ = getDouble(data.get("z"), location.getZ());
            Vector dir = new Vector(targetX - location.getX(), targetY - location.getY(), targetZ - location.getZ());
            if (dir.lengthSquared() == 0.0d) {
                return;
            }
            dir.normalize();
            double xz = Math.sqrt(dir.getX() * dir.getX() + dir.getZ() * dir.getZ());
            float yawValue = (float) Math.toDegrees(Math.atan2(-dir.getX(), dir.getZ()));
            float pitchValue = (float) Math.toDegrees(-Math.atan2(dir.getY(), xz));
            location.setYaw(yawValue);
            location.setPitch(pitchValue);
        }

        private double getDouble(Object value, double def) {
            if (value instanceof Number num) {
                return num.doubleValue();
            }
            if (value instanceof String str) {
                if (str.isBlank()) {
                    return def;
                }
                try {
                    return Double.parseDouble(str);
                } catch (NumberFormatException ignored) {
                    return def;
                }
            }
            return def;
        }
    }

    private static final class SoundAction implements CinematicAction {

        private final String soundName;
        private final float volume;
        private final float pitch;
        private final Map<String, Object> offset;
        private final long holdTicks;

        SoundAction(String soundName, float volume, float pitch, Map<String, Object> offset, long holdTicks) {
            this.soundName = soundName;
            this.volume = volume;
            this.pitch = pitch;
            this.offset = new LinkedHashMap<>(offset);
            this.holdTicks = Math.max(1L, holdTicks);
        }

        @Override
        public void play(CinematicContext context, Runnable onComplete) {
            Player player = context.getPlayer();
            if (player == null) {
                onComplete.run();
                return;
            }
            Sound sound;
            try {
                sound = Sound.valueOf(soundName.toUpperCase(Locale.ROOT));
            } catch (IllegalArgumentException ex) {
                context.getPlugin().getLogger().log(Level.WARNING,
                    "[Cinematic] Unknown sound: {0}", soundName);
                onComplete.run();
                return;
            }
            Location location = player.getLocation().clone();
            location.add(getDouble(offset.get("x"), 0.0d),
                         getDouble(offset.get("y"), 0.0d),
                         getDouble(offset.get("z"), 0.0d));
            player.playSound(location, sound, volume, pitch);
            Bukkit.getScheduler().runTaskLater(context.getPlugin(), onComplete, holdTicks);
        }

        private double getDouble(Object value, double def) {
            if (value instanceof Number num) {
                return num.doubleValue();
            }
            if (value instanceof String str) {
                if (str.isBlank()) {
                    return def;
                }
                try {
                    return Double.parseDouble(str);
                } catch (NumberFormatException ignored) {
                    return def;
                }
            }
            return def;
        }
    }

    private static final class ParticleAction implements CinematicAction {

        private final String particleName;
        private final int count;
        private final double speed;
        private final Map<String, Object> offset;
        private final Map<String, Object> spread;
        private final double radius;
        private final long holdTicks;

        ParticleAction(String particleName,
                       int count,
                       double speed,
                       Map<String, Object> offset,
                       Map<String, Object> spread,
                       double radius,
                       long holdTicks) {
            this.particleName = particleName;
            this.count = count;
            this.speed = speed;
            this.offset = new LinkedHashMap<>(offset);
            this.spread = new LinkedHashMap<>(spread);
            this.radius = radius;
            this.holdTicks = Math.max(1L, holdTicks);
        }

        @Override
        public void play(CinematicContext context, Runnable onComplete) {
            Player player = context.getPlayer();
            if (player == null) {
                onComplete.run();
                return;
            }
            Particle particle;
            try {
                particle = Particle.valueOf(particleName.toUpperCase(Locale.ROOT));
            } catch (IllegalArgumentException ex) {
                context.getPlugin().getLogger().log(Level.WARNING,
                    "[Cinematic] Unknown particle type: {0}", particleName);
                onComplete.run();
                return;
            }
            Location origin = player.getLocation().clone();
            origin.add(value(offset.get("x")), value(offset.get("y")), value(offset.get("z")));
            double spreadX = value(spread.get("x"));
            double spreadY = value(spread.get("y"));
            double spreadZ = value(spread.get("z"));
            if (radius > 0.0d) {
                spreadX = spreadY = spreadZ = radius;
            }
            World world = origin.getWorld();
            if (world != null) {
                world.spawnParticle(particle, origin, count, spreadX, spreadY, spreadZ, speed);
            }
            Bukkit.getScheduler().runTaskLater(context.getPlugin(), onComplete, holdTicks);
        }

        private double value(Object candidate) {
            if (candidate instanceof Number num) {
                return num.doubleValue();
            }
            if (candidate instanceof String str) {
                if (str.isBlank()) {
                    return 0.0d;
                }
                try {
                    return Double.parseDouble(str);
                } catch (NumberFormatException ignored) {
                    return 0.0d;
                }
            }
            return 0.0d;
        }
    }

    private static final class WorldPatchAction implements CinematicAction {

        private final Map<String, Object> operations;
        private final long holdTicks;

        WorldPatchAction(Map<String, Object> operations, long holdTicks) {
            this.operations = new LinkedHashMap<>(operations);
            this.holdTicks = Math.max(1L, holdTicks);
        }

        @Override
        public void play(CinematicContext context, Runnable onComplete) {
            Player player = context.getPlayer();
            if (player == null) {
                onComplete.run();
                return;
            }
            context.getWorldExecutor().execute(player, new LinkedHashMap<>(operations));
            Bukkit.getScheduler().runTaskLater(context.getPlugin(), onComplete, holdTicks);
        }
    }
}
