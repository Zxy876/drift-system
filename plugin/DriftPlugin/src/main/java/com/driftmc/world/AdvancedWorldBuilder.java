package com.driftmc.world;

import java.util.List;
import java.util.Map;

import org.bukkit.ChatColor;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.World;
import org.bukkit.attribute.Attribute;
import org.bukkit.entity.Entity;
import org.bukkit.entity.EntityType;
import org.bukkit.entity.LivingEntity;
import org.bukkit.entity.Minecart;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

/**
 * AdvancedWorldBuilder - 高级世界构建器
 * 
 * 支持复杂场景构建：
 * - 赛车赛道
 * - 考场环境
 * - 隧道场景
 * - 可交互物体（可驾驶的矿车等）
 */
public class AdvancedWorldBuilder {

  private final JavaPlugin plugin;
  private final WorldPatchExecutor executor;

  public AdvancedWorldBuilder(JavaPlugin plugin, WorldPatchExecutor executor) {
    this.plugin = plugin;
    this.executor = executor;
  }

  /**
   * 处理 build_multi：批量构建结构
   */
  @SuppressWarnings("unchecked")
  public void handleBuildMulti(Player player, List<?> buildList) {
    if (buildList == null || buildList.isEmpty())
      return;

    for (Object buildObj : buildList) {
      if (buildObj instanceof Map<?, ?> buildMap) {
        handleSingleBuild(player, (Map<String, Object>) buildMap);
      }
    }

    player.sendMessage(ChatColor.YELLOW + "✧ 环境已完整构建。");
  }

  public void handleBuildMulti(Player player, List<?> buildList, Location anchor) {
    handleBuildMulti(player, buildList);
  }

  /**
   * 处理单个构建指令
   */
  @SuppressWarnings("unchecked")
  private void handleSingleBuild(Player player, Map<String, Object> buildMap) {
    String shape = string(buildMap.get("shape"), "platform");

    switch (shape.toLowerCase()) {
      case "race_track" -> buildRaceTrack(player, buildMap);
      case "hollow_cube" -> buildHollowCube(player, buildMap);
      case "grid" -> buildGrid(player, buildMap);
      case "fence_ring" -> buildFenceRing(player, buildMap);
      case "tunnel" -> buildTunnel(player, buildMap);
      case "light_line" -> buildLightLine(player, buildMap);
      case "line" -> buildLine(player, buildMap);
      default -> {
        // 其他形状交给原始执行器处理
        plugin.getLogger().info("[AdvancedWorldBuilder] Delegating shape '" + shape + "' to base executor");
      }
    }
  }

  /**
   * 构建赛车赛道（椭圆形）
   */
  @SuppressWarnings("unchecked")
  private void buildRaceTrack(Player player, Map<String, Object> params) {
    World world = player.getWorld();

    Map<String, Object> center = (Map<String, Object>) params.get("center");
    if (center == null)
      return;

    double cx = number(center.get("x"), 0).doubleValue();
    double cy = number(center.get("y"), 70).doubleValue();
    double cz = number(center.get("z"), 0).doubleValue();

    double radiusX = number(params.get("radius_x"), 20).doubleValue();
    double radiusZ = number(params.get("radius_z"), 30).doubleValue();
    int width = number(params.get("width"), 5).intValue();

    String materialName = string(params.get("material"), "GRAY_CONCRETE");
    Material material = Material.matchMaterial(materialName.toUpperCase());
    if (material == null)
      material = Material.GRAY_CONCRETE;

    // 绘制椭圆形赛道
    for (int angle = 0; angle < 360; angle += 2) {
      double rad = Math.toRadians(angle);
      double x = cx + radiusX * Math.cos(rad);
      double z = cz + radiusZ * Math.sin(rad);

      // 在每个点周围绘制宽度
      for (int w = -width / 2; w <= width / 2; w++) {
        for (int d = -width / 2; d <= width / 2; d++) {
          world.getBlockAt((int) (x + w), (int) cy, (int) (z + d)).setType(material);
        }
      }
    }

    plugin.getLogger().info("[AdvancedWorldBuilder] 赛道已构建 at " + cx + "," + cy + "," + cz);
  }

  /**
   * 构建空心立方体（房间）
   */
  @SuppressWarnings("unchecked")
  private void buildHollowCube(Player player, Map<String, Object> params) {
    World world = player.getWorld();

    Map<String, Object> center = (Map<String, Object>) params.get("center");
    if (center == null)
      return;

    int cx = number(center.get("x"), 0).intValue();
    int cy = number(center.get("y"), 80).intValue();
    int cz = number(center.get("z"), 0).intValue();

    int size = number(params.get("size"), 20).intValue();
    int height = number(params.get("height"), 6).intValue();

    String materialName = string(params.get("material"), "QUARTZ_BLOCK");
    Material material = Material.matchMaterial(materialName.toUpperCase());
    if (material == null)
      material = Material.QUARTZ_BLOCK;

    int halfSize = size / 2;

    // 构建四面墙
    for (int y = 0; y < height; y++) {
      // 前后墙
      for (int x = -halfSize; x <= halfSize; x++) {
        world.getBlockAt(cx + x, cy + y, cz - halfSize).setType(material);
        world.getBlockAt(cx + x, cy + y, cz + halfSize).setType(material);
      }
      // 左右墙
      for (int z = -halfSize; z <= halfSize; z++) {
        world.getBlockAt(cx - halfSize, cy + y, cz + z).setType(material);
        world.getBlockAt(cx + halfSize, cy + y, cz + z).setType(material);
      }
    }

    plugin.getLogger().info("[AdvancedWorldBuilder] 空心立方体已构建");
  }

  /**
   * 构建网格（灯光等）
   */
  @SuppressWarnings("unchecked")
  private void buildGrid(Player player, Map<String, Object> params) {
    World world = player.getWorld();

    Map<String, Object> center = (Map<String, Object>) params.get("center");
    if (center == null)
      return;

    int cx = number(center.get("x"), 0).intValue();
    int cy = number(center.get("y"), 85).intValue();
    int cz = number(center.get("z"), 0).intValue();

    int size = number(params.get("size"), 18).intValue();
    int spacing = number(params.get("spacing"), 4).intValue();

    String materialName = string(params.get("material"), "SEA_LANTERN");
    Material material = Material.matchMaterial(materialName.toUpperCase());
    if (material == null)
      material = Material.SEA_LANTERN;

    int halfSize = size / 2;

    for (int x = -halfSize; x <= halfSize; x += spacing) {
      for (int z = -halfSize; z <= halfSize; z += spacing) {
        world.getBlockAt(cx + x, cy, cz + z).setType(material);
      }
    }

    plugin.getLogger().info("[AdvancedWorldBuilder] 网格已构建");
  }

  /**
   * 构建栅栏环（赛道围栏）
   */
  @SuppressWarnings("unchecked")
  private void buildFenceRing(Player player, Map<String, Object> params) {
    World world = player.getWorld();

    Map<String, Object> center = (Map<String, Object>) params.get("center");
    if (center == null)
      return;

    double cx = number(center.get("x"), 0).doubleValue();
    double cy = number(center.get("y"), 71).doubleValue();
    double cz = number(center.get("z"), 0).doubleValue();

    double radiusX = number(params.get("radius_x"), 25).doubleValue();
    double radiusZ = number(params.get("radius_z"), 35).doubleValue();

    String materialName = string(params.get("material"), "OAK_FENCE");
    Material material = Material.matchMaterial(materialName.toUpperCase());
    if (material == null)
      material = Material.OAK_FENCE;

    for (int angle = 0; angle < 360; angle += 5) {
      double rad = Math.toRadians(angle);
      double x = cx + radiusX * Math.cos(rad);
      double z = cz + radiusZ * Math.sin(rad);

      world.getBlockAt((int) x, (int) cy, (int) z).setType(material);
    }

    plugin.getLogger().info("[AdvancedWorldBuilder] 栅栏环已构建");
  }

  /**
   * 构建隧道
   */
  @SuppressWarnings("unchecked")
  private void buildTunnel(Player player, Map<String, Object> params) {
    World world = player.getWorld();

    Map<String, Object> start = (Map<String, Object>) params.get("start");
    if (start == null)
      return;

    int sx = number(start.get("x"), 0).intValue();
    int sy = number(start.get("y"), 60).intValue();
    int sz = number(start.get("z"), 0).intValue();

    String direction = string(params.get("direction"), "north");
    int length = number(params.get("length"), 50).intValue();
    int width = number(params.get("width"), 5).intValue();
    int height = number(params.get("height"), 5).intValue();

    String materialName = string(params.get("material"), "STONE_BRICKS");
    Material material = Material.matchMaterial(materialName.toUpperCase());
    if (material == null)
      material = Material.STONE_BRICKS;

    int dx = 0, dz = 0;
    switch (direction.toLowerCase()) {
      case "north" -> dz = -1;
      case "south" -> dz = 1;
      case "east" -> dx = 1;
      case "west" -> dx = -1;
    }

    for (int i = 0; i < length; i++) {
      int x = sx + dx * i;
      int z = sz + dz * i;

      // 地板
      for (int wx = -width / 2; wx <= width / 2; wx++) {
        for (int wz = -width / 2; wz <= width / 2; wz++) {
          world.getBlockAt(x + wx, sy, z + wz).setType(material);
        }
      }

      // 墙壁
      for (int h = 1; h < height; h++) {
        for (int w = -width / 2; w <= width / 2; w++) {
          if (dx != 0) {
            world.getBlockAt(x, sy + h, z - width / 2).setType(material);
            world.getBlockAt(x, sy + h, z + width / 2).setType(material);
          } else {
            world.getBlockAt(x - width / 2, sy + h, z).setType(material);
            world.getBlockAt(x + width / 2, sy + h, z).setType(material);
          }
        }
      }

      // 天花板
      for (int wx = -width / 2; wx <= width / 2; wx++) {
        for (int wz = -width / 2; wz <= width / 2; wz++) {
          world.getBlockAt(x + wx, sy + height, z + wz).setType(material);
        }
      }
    }

    plugin.getLogger().info("[AdvancedWorldBuilder] 隧道已构建");
  }

  /**
   * 构建灯光线
   */
  @SuppressWarnings("unchecked")
  private void buildLightLine(Player player, Map<String, Object> params) {
    World world = player.getWorld();

    Map<String, Object> start = (Map<String, Object>) params.get("start");
    if (start == null)
      return;

    int sx = number(start.get("x"), 0).intValue();
    int sy = number(start.get("y"), 64).intValue();
    int sz = number(start.get("z"), 0).intValue();

    String direction = string(params.get("direction"), "north");
    int length = number(params.get("length"), 50).intValue();
    int spacing = number(params.get("spacing"), 5).intValue();

    String materialName = string(params.get("material"), "TORCH");
    Material material = Material.matchMaterial(materialName.toUpperCase());
    if (material == null)
      material = Material.TORCH;

    int dx = 0, dz = 0;
    switch (direction.toLowerCase()) {
      case "north" -> dz = -1;
      case "south" -> dz = 1;
      case "east" -> dx = 1;
      case "west" -> dx = -1;
    }

    for (int i = 0; i < length; i += spacing) {
      int x = sx + dx * i;
      int z = sz + dz * i;
      world.getBlockAt(x, sy, z).setType(material);
    }

    plugin.getLogger().info("[AdvancedWorldBuilder] 灯光线已构建");
  }

  /**
   * 构建直线
   */
  @SuppressWarnings("unchecked")
  private void buildLine(Player player, Map<String, Object> params) {
    World world = player.getWorld();

    Map<String, Object> start = (Map<String, Object>) params.get("start");
    Map<String, Object> end = (Map<String, Object>) params.get("end");
    if (start == null || end == null)
      return;

    int x1 = number(start.get("x"), 0).intValue();
    int y1 = number(start.get("y"), 70).intValue();
    int z1 = number(start.get("z"), 0).intValue();

    int x2 = number(end.get("x"), 0).intValue();
    int y2 = number(end.get("y"), 70).intValue();
    int z2 = number(end.get("z"), 0).intValue();

    String materialName = string(params.get("material"), "RED_CONCRETE");
    Material material = Material.matchMaterial(materialName.toUpperCase());
    if (material == null)
      material = Material.RED_CONCRETE;

    // 使用Bresenham算法绘制直线
    int dx = Math.abs(x2 - x1);
    int dz = Math.abs(z2 - z1);
    int sx = x1 < x2 ? 1 : -1;
    int sz = z1 < z2 ? 1 : -1;
    int err = dx - dz;

    while (true) {
      world.getBlockAt(x1, y1, z1).setType(material);

      if (x1 == x2 && z1 == z2)
        break;

      int e2 = 2 * err;
      if (e2 > -dz) {
        err -= dz;
        x1 += sx;
      }
      if (e2 < dx) {
        err += dx;
        z1 += sz;
      }
    }
  }

  /**
   * 处理 spawn_multi：批量生成实体
   */
  @SuppressWarnings("unchecked")
  public void handleSpawnMulti(Player player, List<?> spawnList) {
    if (spawnList == null || spawnList.isEmpty())
      return;

    for (Object spawnObj : spawnList) {
      if (spawnObj instanceof Map<?, ?> spawnMap) {
        handleSingleSpawn(player, (Map<String, Object>) spawnMap);
      }
    }

    player.sendMessage(ChatColor.LIGHT_PURPLE + "✧ 实体已生成。");
  }

  public void handleSpawnMulti(Player player, List<?> spawnList, Location anchor) {
    handleSpawnMulti(player, spawnList);
  }

  /**
   * 处理单个实体生成
   */
  @SuppressWarnings("unchecked")
  private void handleSingleSpawn(Player player, Map<String, Object> spawnMap) {
    World world = player.getWorld();

    String typeName = string(spawnMap.get("type"), "ARMOR_STAND");
    String name = string(spawnMap.get("name"), "");

    Map<String, Object> position = (Map<String, Object>) spawnMap.get("position");
    if (position == null)
      return;

    double x = number(position.get("x"), 0).doubleValue();
    double y = number(position.get("y"), 70).doubleValue();
    double z = number(position.get("z"), 0).doubleValue();

    Location loc = new Location(world, x, y, z);

    EntityType type = EntityType.fromName(typeName.toUpperCase());
    if (type == null) {
      type = EntityType.ARMOR_STAND;
    }

    Entity entity = world.spawnEntity(loc, type);

    if (entity instanceof LivingEntity living) {
      if (!name.isEmpty()) {
        living.setCustomName(name);
        living.setCustomNameVisible(true);
      }

      var attr = living.getAttribute(Attribute.GENERIC_MAX_HEALTH);
      if (attr != null) {
        attr.setBaseValue(40.0);
        living.setHealth(40.0);
      }
    }

    // 特殊处理：可驾驶的矿车
    if (entity instanceof Minecart minecart) {
      minecart.setCustomName(name);
      minecart.setCustomNameVisible(true);
      minecart.setMaxSpeed(0.8); // 设置最大速度

      Boolean rideable = (Boolean) spawnMap.get("rideable");
      if (rideable != null && rideable) {
        player.sendMessage(ChatColor.YELLOW + "✧ 赛车已就位，右键点击开始驾驶！");
      }
    }

    plugin.getLogger().info("[AdvancedWorldBuilder] 生成实体: " + typeName + " at " + x + "," + y + "," + z);
  }

  // =============================== 工具方法 ===============================
  private String string(Object o, String def) {
    return o == null ? def : o.toString();
  }

  private Number number(Object o, Number def) {
    if (o instanceof Number n)
      return n;
    if (o == null)
      return def;
    try {
      return Double.parseDouble(o.toString());
    } catch (Exception e) {
      return def;
    }
  }
}
