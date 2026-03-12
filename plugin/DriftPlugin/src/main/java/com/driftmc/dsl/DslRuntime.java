package com.driftmc.dsl;

import java.util.HashMap;
import java.util.Map;

public class DslRuntime {

    private final String type;
    private final Map<String, Object> args;

    public DslRuntime(String type, Map<String, Object> args) {
        this.type = type;
        this.args = args != null ? args : new HashMap<>();
    }

    public String getType() {
        return type;
    }

    public Map<String, Object> getArgs() {
        return args;
    }
}