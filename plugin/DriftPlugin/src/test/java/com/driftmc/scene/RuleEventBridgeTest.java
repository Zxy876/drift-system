package com.driftmc.scene;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.logging.Logger;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.World;
import org.bukkit.command.ConsoleCommandSender;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import org.junit.jupiter.api.AfterEach;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import org.mockito.MockedStatic;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.when;

import com.driftmc.backend.BackendClient;
import com.driftmc.hud.dialogue.ChoicePanel;
import com.driftmc.hud.dialogue.DialoguePanel;
import com.driftmc.npc.NPCManager;
import com.driftmc.session.PlayerSessionManager;
import com.driftmc.tutorial.TutorialManager;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

import okhttp3.Callback;

class RuleEventBridgeTest {

    private JavaPlugin plugin;
    private RecordingBackend backend;
    private SceneAwareWorldPatchExecutor worldPatcher;
    private RuleEventBridge bridge;
    private NPCManager npcManager;
    private ChoicePanel choicePanel;
    private DialoguePanel dialoguePanel;
    private PlayerSessionManager sessions;
    private TutorialManager tutorialManager;
    private MockedStatic<Bukkit> bukkit;
    private Player player;
    private UUID playerId;
    private List<String> messages;

    @BeforeEach
    void setUp() {
        System.setProperty("net.bytebuddy.experimental", "true");
        plugin = mock(JavaPlugin.class);
        when(plugin.getLogger()).thenReturn(Logger.getLogger("TestPlugin"));

        backend = new RecordingBackend();
        npcManager = new NPCManager(plugin);
        worldPatcher = new SceneAwareWorldPatchExecutor(plugin, npcManager);
        choicePanel = new ChoicePanel(plugin);
        dialoguePanel = new DialoguePanel(plugin, choicePanel);
        sessions = new PlayerSessionManager();
        tutorialManager = new TutorialManager(plugin, backend, sessions);
        bridge = new RuleEventBridge(plugin, backend, worldPatcher, null, dialoguePanel, choicePanel, sessions, tutorialManager);
        choicePanel.setRuleEventBridge(bridge);

        player = mock(Player.class);
        playerId = UUID.randomUUID();
        when(player.getUniqueId()).thenReturn(playerId);
        when(player.getName()).thenReturn("QuestRunner");
        when(player.isOnline()).thenReturn(true);
        World world = mock(World.class);
        Location location = new Location(world, 0, 64, 0);
        when(player.getWorld()).thenReturn(world);
        when(player.getLocation()).thenReturn(location);

        messages = new ArrayList<>();
        doAnswer(invocation -> {
            messages.add(invocation.getArgument(0));
            return null;
        }).when(player).sendMessage(anyString());

        bukkit = mockStatic(Bukkit.class);
        ConsoleCommandSender console = mock(ConsoleCommandSender.class);
        bukkit.when(Bukkit::getConsoleSender).thenReturn(console);
        bukkit.when(Bukkit::isPrimaryThread).thenReturn(true);
        bukkit.when(() -> Bukkit.dispatchCommand(any(), anyString())).thenReturn(true);
        bukkit.when(() -> Bukkit.getPlayer(any(UUID.class))).thenAnswer(invocation -> {
            UUID id = invocation.getArgument(0);
            return playerId.equals(id) ? player : null;
        });
    }

    @AfterEach
    void tearDown() {
        backend.clear();
        bukkit.close();
    }

    @Test
    void duplicateTriggerSuppression() {
        bridge.setCooldownMillis(10_000L);

        bridge.emit(player, "chat", Map.of("text", "hello"));
        bridge.emit(player, "chat", Map.of("text", "hello"));

        assertEquals(1, backend.requestCount(), "Cooldown should suppress duplicate payloads");
    }

    @Test
    void offlinePlayerResponseIsDiscarded() throws Exception {
        UUID ghostId = UUID.randomUUID();

        JsonObject worldPatch = new JsonObject();
        worldPatch.addProperty("tell", "should_not_apply");

        invokeApplyRuleEventResult(
                bridge,
                ghostId,
                "GhostPlayer",
                worldPatch,
                new JsonArray(),
                new JsonArray(),
                new JsonArray(),
                new JsonArray(),
                false,
            new JsonObject(),
            new JsonObject());

        assertTrue(getPlayerStates(bridge).isEmpty(),
                "Player state map should remain empty for offline players");
    }

    @Test
    void integrationAppliesWorldPatchAndNodes() throws Exception {
        JsonObject worldPatch = new JsonObject();
        worldPatch.addProperty("tell", "奖励已发放");

        JsonArray nodes = new JsonArray();
        JsonObject node = new JsonObject();
        node.addProperty("type", "task_complete");
        node.addProperty("title", "完成：collect_sunflower");
        node.addProperty("text", "你闻到了花香。");
        nodes.add(node);

        JsonArray completed = new JsonArray();
        completed.add("collect_sunflower");

        JsonObject summary = new JsonObject();
        summary.addProperty("type", "task_summary");
        summary.addProperty("title", "任务总结");
        summary.addProperty("text", "继续冒险吧！");

        invokeApplyRuleEventResult(
                bridge,
                playerId,
                player.getName(),
                worldPatch,
                nodes,
                new JsonArray(),
                completed,
                new JsonArray(),
                true,
            summary,
            new JsonObject());

        assertTrue(messages.stream().anyMatch(msg -> msg.contains("奖励已发放")),
            "Tell operations should reach the player");
        assertTrue(messages.stream().anyMatch(msg -> msg.contains("完成") && msg.contains("collect_sunflower")),
                "Completion headline should be announced");
        assertTrue(messages.stream().anyMatch(msg -> msg.contains("✔ 任务完成")),
                "Completed task toast should reach the player");
        assertTrue(messages.stream().anyMatch(msg -> msg.contains("当前关卡任务全部完成")),
                "Exit readiness message should notify the player");
    }

        @Test
        void tutorialMilestoneMarksCompletion() throws Exception {
        sessions.markTutorialStarted(player);

        JsonArray milestones = new JsonArray();
        milestones.add("tutorial_complete");

        invokeApplyRuleEventResult(
            bridge,
            playerId,
            player.getName(),
            new JsonObject(),
            new JsonArray(),
            new JsonArray(),
            new JsonArray(),
            milestones,
            false,
            new JsonObject(),
            new JsonObject());

        assertTrue(messages.stream().anyMatch(msg -> msg.contains("教程完成")),
            "Tutorial completion message should reach the player");
        assertTrue(sessions.hasCompletedTutorial(player));
        }

        private static void invokeApplyRuleEventResult(
            RuleEventBridge bridge,
            UUID playerId,
            String playerName,
            JsonObject worldPatch,
            JsonArray nodes,
            JsonArray commands,
            JsonArray completed,
            JsonArray milestones,
            boolean exitReady,
            JsonObject summary,
            JsonObject activeTasks) throws Exception {

        Method method = RuleEventBridge.class.getDeclaredMethod(
                "applyRuleEventResult",
                UUID.class,
                String.class,
                JsonObject.class,
                JsonArray.class,
                JsonArray.class,
                JsonArray.class,
                JsonArray.class,
                boolean.class,
            JsonObject.class,
            JsonObject.class);
        method.setAccessible(true);
        method.invoke(
                bridge,
                playerId,
                playerName,
                worldPatch,
                nodes,
                commands,
                completed,
                milestones,
                exitReady,
                summary,
                activeTasks);
    }

    @SuppressWarnings("unchecked")
    private static Map<UUID, ?> getPlayerStates(RuleEventBridge bridge) throws Exception {
        Field field = RuleEventBridge.class.getDeclaredField("playerStates");
        field.setAccessible(true);
        return (Map<UUID, ?>) field.get(bridge);
    }

    private static final class RecordingBackend extends BackendClient {

        private int requests;

        RecordingBackend() {
            super("http://localhost");
        }

        @Override
        public void postJsonAsync(String path, String json, Callback callback) {
            requests++;
        }

        int requestCount() {
            return requests;
        }

        void clear() {
            requests = 0;
        }
    }


}
