package com.driftmc.listeners;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class MiniJson {

    public static Map<String, Object> parse(String json) {
        return (Map<String, Object>) parseValue(new Token(json));
    }

    private static Object parseValue(Token t) {
        t.skip();
        char c = t.peek();

        if (c == '{') return parseObject(t);
        if (c == '[') return parseArray(t);
        if (c == '"') return parseString(t);
        if (Character.isDigit(c) || c == '-') return parseNumber(t);

        if (t.starts("true")) {
            t.advance(4);
            return true;
        }
        if (t.starts("false")) {
            t.advance(5);
            return false;
        }
        if (t.starts("null")) {
            t.advance(4);
            return null;
        }

        throw new RuntimeException("Bad JSON at: " + t.pos);
    }

    private static Map<String, Object> parseObject(Token t) {
        Map<String, Object> map = new LinkedHashMap<>();
        t.expect('{');
        t.skip();

        if (t.peek() == '}') {
            t.expect('}');
            return map;
        }

        while (true) {
            String key = parseString(t);
            t.skip();
            t.expect(':');
            Object val = parseValue(t);
            map.put(key, val);

            t.skip();
            if (t.peek() == ',') {
                t.expect(',');
                continue;
            }
            t.expect('}');
            break;
        }
        return map;
    }

    private static List<Object> parseArray(Token t) {
        List<Object> arr = new ArrayList<>();
        t.expect('[');
        t.skip();

        if (t.peek() == ']') {
            t.expect(']');
            return arr;
        }

        while (true) {
            arr.add(parseValue(t));
            t.skip();
            if (t.peek() == ',') {
                t.expect(',');
                continue;
            }
            t.expect(']');
            break;
        }
        return arr;
    }

    private static String parseString(Token t) {
        t.expect('"');
        StringBuilder sb = new StringBuilder();
        while (true) {
            char c = t.next();
            if (c == '"') break;
            if (c == '\\') c = t.next();
            sb.append(c);
        }
        return sb.toString();
    }

    private static Double parseNumber(Token t) {
        int start = t.pos;
        while (t.pos < t.s.length() && "0123456789.-".indexOf(t.peek()) >= 0)
            t.pos++;
        return Double.valueOf(t.s.substring(start, t.pos));
    }

    private static class Token {
        String s;
        int pos;

        Token(String s) { this.s = s; }

        void skip() {
            while (pos < s.length() && Character.isWhitespace(s.charAt(pos))) pos++;
        }

        char peek() { return s.charAt(pos); }

        char next() { return s.charAt(pos++); }

        void expect(char c) {
            skip();
            if (s.charAt(pos) != c)
                throw new RuntimeException("Expected '" + c + "' at " + pos);
            pos++;
        }

        boolean starts(String prefix) {
            return s.startsWith(prefix, pos);
        }

        void advance(int n) { pos += n; }
    }
}