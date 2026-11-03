package gl.syn.minecraft;

import java.util.List;

public final class AgentNamesTest {
    private static int checks;
    private static void check(boolean value) {
        checks++;
        if (!value) throw new AssertionError("Name assertion " + checks);
    }
    public static void main(String[] args) {
        check(AgentNames.valid("Forge"));
        check(AgentNames.valid("A"));
        check(AgentNames.valid("1234567890123456"));
        check(!AgentNames.valid("12345678901234567"));
        check(!AgentNames.valid("x\nstop"));
        check(!AgentNames.valid(""));
        check(!AgentNames.valid(null));
        check(AgentNames.conflicts("closeddoor",List.of("ClosedDoor")));
        check(AgentNames.addressed("Forge, stop", "Forge"));
        check(!AgentNames.addressed("forgeable", "Forge"));
        check(!AgentNames.addressed("door, stop", "ClosedDoor"));
        check(AgentNames.addressed("Moss, stop", "Syn_Moss"));
        check(AgentNames.addressed("A, stop", "A"));
        System.out.println(checks + " agent name assertions passed");
    }
}
