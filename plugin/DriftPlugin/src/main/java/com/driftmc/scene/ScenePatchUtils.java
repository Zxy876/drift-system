package com.driftmc.scene;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class ScenePatchUtils {

    private ScenePatchUtils() {
    }

    static Map<String, Object> deepCopyMap(Map<?, ?> source) {
        if (source == null) {
            return new LinkedHashMap<>();
        }
        Map<String, Object> copy = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : source.entrySet()) {
            String key = entry.getKey() != null ? entry.getKey().toString() : null;
            Object value = entry.getValue();
            if (value instanceof Map<?, ?> mapValue) {
                copy.put(key, deepCopyMap(mapValue));
            } else if (value instanceof List<?> listValue) {
                copy.put(key, deepCopyList(listValue));
            } else {
                copy.put(key, value);
            }
        }
        return copy;
    }

    static List<Object> deepCopyList(List<?> source) {
        List<Object> copy = new ArrayList<>();
        if (source == null) {
            return copy;
        }
        for (Object value : source) {
            if (value != null && Map.class.isInstance(value)) {
                copy.add(deepCopyMap(Map.class.cast(value)));
            } else if (value != null && List.class.isInstance(value)) {
                copy.add(deepCopyList(List.class.cast(value)));
            } else {
                copy.add(value);
            }
        }
        return copy;
    }

    static Map<String, Object> invertBuild(Map<?, ?> build) {
        if (build == null) {
            return new LinkedHashMap<>();
        }
        Map<String, Object> inverted = deepCopyMap(build);
        inverted.put("material", "AIR");
        Object offset = inverted.get("offset");
        if (!(offset instanceof Map<?, ?>) && inverted.containsKey("safe_offset")) {
            inverted.put("offset", deepCopyMap((Map<?, ?>) inverted.get("safe_offset")));
        }
        inverted.remove("safe_offset");
        inverted.remove("spawn");
        inverted.remove("teleport");
        return inverted;
    }

    static List<Object> invertBuildList(List<?> buildList) {
        List<Object> results = new ArrayList<>();
        if (buildList == null) {
            return results;
        }
        for (Object entry : buildList) {
            if (entry instanceof Map<?, ?> map) {
                results.add(invertBuild(map));
            }
        }
        return results;
    }
}
