package com.driftmc.listeners;

import java.util.List;
import java.util.logging.Level;

import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.exit.ExitIntentDetector;
import com.driftmc.hud.dialogue.ChoicePanel;
import com.driftmc.intent2.IntentDispatcher2;
import com.driftmc.intent2.IntentResponse2;
import com.driftmc.intent2.IntentRouter2;
import com.driftmc.scene.RuleEventBridge;
import com.driftmc.tutorial.TutorialManager;

import io.papermc.paper.event.player.AsyncChatEvent;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;

public class PlayerChatListener implements Listener {

    private final JavaPlugin plugin;
    private final IntentRouter2 router;
    private final IntentDispatcher2 dispatcher;
    private final TutorialManager tutorialManager;
    private final RuleEventBridge ruleEvents;
    private final ExitIntentDetector exitDetector;
    private final ChoicePanel choicePanel;

    public PlayerChatListener(JavaPlugin plugin, IntentRouter2 router, IntentDispatcher2 dispatcher,
            TutorialManager tutorialManager, RuleEventBridge ruleEvents, ExitIntentDetector exitDetector,
            ChoicePanel choicePanel) {
        this.plugin = plugin;
        this.router = router;
        this.dispatcher = dispatcher;
        this.tutorialManager = tutorialManager;
        this.ruleEvents = ruleEvents;
        this.exitDetector = exitDetector;
        this.choicePanel = choicePanel;
    }

    @EventHandler
    public void onAsyncChat(AsyncChatEvent e) {
        Player p = e.getPlayer();

        String msg = PlainTextComponentSerializer.plainText().serialize(e.message());
        e.setCancelled(true);

        if (choicePanel != null && choicePanel.consumeSelection(p, msg)) {
            return;
        }

        p.sendMessage("§7你：" + msg);
        plugin.getLogger().log(Level.INFO, "[聊天] 玩家 {0} 说: {1}", new Object[]{p.getName(), msg});

        if (ruleEvents != null) {
            ruleEvents.emitTalk(p, msg);
        }

        // 保存原始消息
        final String originalMsg = msg;

        // 首先检查教学进度（如果玩家在教学中）
        tutorialManager.checkProgress(p, originalMsg);

        if (exitDetector != null && exitDetector.handle(p, originalMsg)) {
            return;
        }

        // 多意图版本
        router.askIntent(p.getName(), msg, (List<IntentResponse2> intents) -> {
            plugin.getLogger().log(Level.INFO, "[聊天] 收到 {0} 个意图", intents.size());
            Bukkit.getScheduler().runTask(plugin, () -> {
                StringBuilder intentSeq = new StringBuilder();
                for (int i = 0; i < intents.size(); i++) {
                    if (i > 0) {
                        intentSeq.append(", ");
                    }
                    intentSeq.append(intents.get(i).type);
                }
                plugin.getLogger().log(Level.INFO,
                        "[DEBUG] intents=[{0}] player={1} text={2}",
                        new Object[]{intentSeq.toString(), p.getName(), originalMsg});

                // 依次分发所有意图，并传递原始消息
                for (IntentResponse2 intent : intents) {
                    plugin.getLogger().log(Level.INFO,
                            "[聊天] 分发意图: {0}, rawText={1}",
                            new Object[]{intent.type, intent.rawText});

                    // 如果intent没有rawText，使用原始消息
                    IntentResponse2 fixedIntent = intent;
                    if (intent.rawText == null || intent.rawText.isEmpty()) {
                        fixedIntent = new IntentResponse2(
                                intent.type,
                                intent.levelId,
                                intent.minimap,
                                originalMsg, // 使用原始消息
                                intent.sceneTheme,
                            intent.sceneHint,
                                intent.worldPatch);
                        plugin.getLogger().log(Level.INFO,
                                "[聊天] 修正后的rawText: {0}", originalMsg);
                    }

                    dispatcher.dispatch(p, fixedIntent);
                }
            });
        });
    }
}