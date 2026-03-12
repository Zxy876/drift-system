package com.driftmc.dsl;

import java.io.*;
import java.nio.charset.StandardCharsets;

/**
 * 读取 DSL 文件（骨架）
 */
public class DslFileLoader {

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
