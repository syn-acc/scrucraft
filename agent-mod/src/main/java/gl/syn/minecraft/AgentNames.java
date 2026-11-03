package gl.syn.minecraft;

import java.util.Collection;
import java.util.Locale;
import java.util.regex.Pattern;

/** Shared name rules, independent of Minecraft so they can be tested offline. */
public final class AgentNames {
    private AgentNames() {}
    public static boolean valid(String name) {
        return name != null && name.matches("[A-Za-z0-9_]{1,16}");
    }
    public static boolean conflicts(String name, Collection<String> existing) {
        return existing.stream().anyMatch(name::equalsIgnoreCase);
    }
    public static boolean addressed(String text, String name) {
        String lower = text.toLowerCase(Locale.ROOT);
        if (Pattern.compile("\\b" + Pattern.quote(name.toLowerCase(Locale.ROOT)) + "\\b").matcher(lower).find()) return true;
        return name.startsWith("Syn_") && name.length() > 4
            && Pattern.compile("\\b" + Pattern.quote(name.substring(4).toLowerCase(Locale.ROOT)) + "\\b").matcher(lower).find();
    }
}
