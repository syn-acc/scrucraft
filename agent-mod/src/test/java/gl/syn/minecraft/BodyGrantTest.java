package gl.syn.minecraft;

import com.google.gson.*;

/** Deterministic clock regressions for EXEC-03/06; no server or wall-clock sleeps. */
final class BodyGrantTest {
    private static JsonObject envelope(long issued,long expires) {
        JsonObject value=new JsonObject();value.addProperty("issued_at_ms",issued);value.addProperty("expires_at_ms",expires);
        JsonObject action=new JsonObject();action.addProperty("kind","controls");action.add("commands",new JsonArray());value.add("action",action);return value;
    }
    static void check() {
        if(BodyGrant.receive(envelope(1000,1200),1200,10,0)!=null)throw new AssertionError("expired arrival accepted");
        if(BodyGrant.receive(envelope(1000,1200),999,10,0)!=null)throw new AssertionError("future issue accepted");
        if(BodyGrant.receive(envelope(1000,1200),1050,10,1001)!=null)throw new AssertionError("older grant replay accepted");
        BodyGrant remaining=BodyGrant.receive(envelope(1000,1200),1150,10,0);
        if(!remaining.fresh(1199,49_000_010))throw new AssertionError("remaining grant lifetime rejected");
        if(remaining.fresh(1199,50_000_010))throw new AssertionError("delivery renewed monotonic lifetime");
        BodyGrant backwards=BodyGrant.receive(envelope(1000,1200),1100,10,0);
        if(backwards.fresh(1099,11)||backwards.fresh(1101,12))throw new AssertionError("clock rollback resurrected grant");
        BodyGrant forwards=BodyGrant.receive(envelope(1000,1200),1050,10,0);
        if(forwards.fresh(1201,11)||forwards.fresh(1051,12))throw new AssertionError("clock forward/backward resurrected expired grant");
        JsonObject value=envelope(1000,1200),command=new JsonObject();command.addProperty("deadline_ms",1120);command.addProperty("timeout_ticks",100);
        value.getAsJsonObject("action").getAsJsonArray("commands").add(command);
        BodyGrant clamped=BodyGrant.receive(value,1050,10,0);
        if(clamped.poll(1070,20).getAsJsonArray("commands").get(0).getAsJsonObject().get("timeout_ticks").getAsInt()!=1)
            throw new AssertionError("original action deadline not preserved");
        if(command.get("timeout_ticks").getAsInt()!=100)throw new AssertionError("poll mutated retransmitted request");
        if(clamped.poll(1121,30).getAsJsonArray("commands").size()!=1)throw new AssertionError("expired command lost explicit outcome opportunity");
        for(JsonObject invalid:new JsonObject[]{envelope(1000,1201),envelope(1000,1000),envelope(-1,10),new JsonObject()}) {
            try{BodyGrant.receive(invalid,1050,10,0);throw new AssertionError("malformed window accepted");}
            catch(IllegalArgumentException expected){}
        }
        System.out.println("Body grant clock, delayed arrival, retry and original deadline checks passed");
    }
}
