#!/bin/bash

BASE="src/main/java/com/driftmc/dsl"

echo ">>> 创建 DSL 目录"
mkdir -p $BASE

# ========== DSLCommand ==========
cat > $BASE/DSLCommand.java << 'EOF'
package com.driftmc.dsl;

import java.util.List;

/**
 * 心悦宇宙 DSL 指令数据结构（待填充）
 */
public class DSLCommand {

    public enum Type {
        UNKNOWN,   // 占位
        // TODO：未来加入 NPC、WORLD、AI、COSMOS 等类型
    }

    public final Type type;
    public final List<String> args;

    public DSLCommand(Type type, List<String> args) {
        this.type = type;
        this.args = args;
    }
}
EOF

# ========== DSLParser ==========
cat > $BASE/DSLParser.java << 'EOF'
package com.driftmc.dsl;

import java.util.*;

/**
 * 心悦宇宙 DSL 文本 → 命令列表（宽松解析版骨架）
 */
public class DSLParser {

    public List<DSLCommand> parse(String script) {
        List<DSLCommand> cmds = new ArrayList<>();
        // TODO：未来添加解析逻辑
        return cmds;
    }
}
EOF

# ========== DSLExecutor ==========
cat > $BASE/DSLExecutor.java << 'EOF'
package com.driftmc.dsl;

import org.bukkit.entity.Player;
import java.util.List;

/**
 * 心悦宇宙 DSL 执行器：宽松模式（骨架版）
 */
public class DSLExecutor {

    public void execute(Player player, List<DSLCommand> commands) {
        // TODO：依次执行命令
        // TODO：宽松模式：不中断，只记录错误
    }
}
EOF

# ========== DSLRuntime ==========
cat > $BASE/DSLRuntime.java << 'EOF'
package com.driftmc.dsl;

import org.bukkit.entity.Player;

/**
 * 心悦宇宙 DSL 运行时管理器（骨架）
 */
public class DSLRuntime {

    public void runScript(Player player, String script) {
        // TODO：解析 + 执行
    }
}
EOF

# ========== DSLFileLoader ==========
cat > $BASE/DSLFileLoader.java << 'EOF'
package com.driftmc.dsl;

import java.io.*;
import java.nio.charset.StandardCharsets;

/**
 * 读取 DSL 文件（骨架）
 */
public class DSLFileLoader {

    public static String load(String path) {
        try {
            return new String(java.nio.file.Files.readAllBytes(
                java.nio.file.Paths.get(path)
            ), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return null;
        }
    }
}
EOF

# ========== DslCommand（/dsl run） ==========
cat > src/main/java/com/driftmc/commands/DslRunCommand.java << 'EOF'
package com.driftmc.commands;

import com.driftmc.dsl.*;
import org.bukkit.command.*;
import org.bukkit.entity.Player;

/**
 * /dsl run <file>
 * 运行 DSL 脚本（骨架）
 */
public class DslRunCommand implements CommandExecutor {

    @Override
    public boolean onCommand(CommandSender sender, Command cmd, String label, String[] args) {

        if (!(sender instanceof Player player)) {
            sender.sendMessage("Only players can run DSL.");
            return true;
        }

        if (args.length == 0) {
            player.sendMessage("Usage: /dsl run <file>");
            return true;
        }

        String filename = args[0];

        String script = DSLFileLoader.load("scripts/" + filename);
        if (script == null) {
            player.sendMessage("Script not found: " + filename);
            return true;
        }

        DSLRuntime rt = new DSLRuntime();
        rt.runScript(player, script);

        player.sendMessage("§a运行 DSL 脚本：" + filename);
        return true;
    }
}
EOF

echo ">>> DSL 骨架创建完成！"
