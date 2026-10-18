package com.homehub.kiosk;

import java.net.URI;
import java.net.URLEncoder;

/** Pure URL policy, shared with host-side Java contract checks. No DNS lookup. */
public final class BrowserPolicy {
    public static boolean isPublicHttps(String value) {
        try {
            if (value == null || value.length() > 4096 || value.matches(".*[\\x00-\\x20\\x7f\\\\].*")) return false;
            URI uri = new URI(value);
            String host = uri.getHost();
            if (!"https".equals(uri.getScheme()) || host == null || uri.getUserInfo() != null
                    || (uri.getPort() != -1 && uri.getPort() != 443)) return false;
            host = host.toLowerCase(java.util.Locale.ROOT);
            // DNS website names only. Refuse IP literals, numeric/hex host
            // spellings and terminal dots rather than relying on Java's IP
            // parser, whose canonicalization differs from Chromium's.
            if (host.contains(":") || host.contains("%") || host.endsWith(".")
                    || host.equals("localhost") || host.endsWith(".localhost")
                    || host.endsWith(".local") || host.endsWith(".lan") || host.endsWith(".internal")) return false;
            if (!host.contains(".") || !host.matches("[a-z0-9.-]+")) return false;
            String last = host.substring(host.lastIndexOf('.') + 1);
            return last.matches("[a-z][a-z0-9-]*");
        } catch (Exception ignored) { return false; }
    }

    public static String destination(String input) {
        String text = input == null ? "" : input.trim();
        if (text.length() > 2048) throw new IllegalArgumentException();
        if (text.length() == 0) return "https://duckduckgo.com/";
        if (text.startsWith("https://") || text.contains("://")) {
            if (!isPublicHttps(text)) throw new IllegalArgumentException();
            return text;
        }
        if (!text.contains(" ") && text.contains(":")) throw new IllegalArgumentException();
        if (!text.contains(" ") && text.contains(".")) {
            String candidate = "https://" + text;
            if (isPublicHttps(candidate)) return candidate;
            throw new IllegalArgumentException();
        }
        return "https://duckduckgo.com/?q=" + encode(text);
    }

    public static String origin(String value) {
        try {
            URI uri = new URI(value);
            if (uri.getHost() == null || uri.getUserInfo() != null
                    || !("http".equals(uri.getScheme()) || "https".equals(uri.getScheme()))) return "";
            return new URI(uri.getScheme(), null, uri.getHost(), uri.getPort(), null, null, null).toString();
        } catch (Exception ignored) { return ""; }
    }

    public static String encode(String text) {
        try { return URLEncoder.encode(text, "UTF-8"); }
        catch (Exception ignored) { throw new IllegalArgumentException(); }
    }
}
