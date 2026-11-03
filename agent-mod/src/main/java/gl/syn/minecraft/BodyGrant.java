package gl.syn.minecraft;

import com.google.gson.*;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicBoolean;

/** Same-host wall deadline plus a monotonic upper bound; never renew age on delivery. */
final class BodyGrant {
    final JsonObject action;
    final long issued,expires,monotonicExpires;
    private final AtomicLong wallSeen;
    private final AtomicBoolean invalid=new AtomicBoolean();
    private BodyGrant(JsonObject action,long issued,long expires,long wall,long nanos) {
        this.action=action;this.issued=issued;this.expires=expires;
        monotonicExpires=nanos+(expires-wall)*1_000_000L;wallSeen=new AtomicLong(wall);
    }
    static long integer(JsonObject value,String field) {
        JsonElement element=value.get(field);
        if(element==null||!element.isJsonPrimitive()||!element.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException("invalid_grant_deadline");
        try{return element.getAsBigDecimal().longValueExact();}
        catch(ArithmeticException error){throw new IllegalArgumentException("invalid_grant_deadline",error);}
    }
    static BodyGrant receive(JsonObject envelope,long wall,long nanos,long latestIssued) {
        long issued=integer(envelope,"issued_at_ms"),expires=integer(envelope,"expires_at_ms");
        if(issued<0||expires<=issued||expires-issued>200)throw new IllegalArgumentException("invalid_grant_window");
        if(issued>wall||expires<=wall||issued<latestIssued)return null;
        JsonObject action=envelope.getAsJsonObject("action");
        if(action==null)throw new IllegalArgumentException("missing_grant_action");
        if(action.has("commands"))for(JsonElement item:action.getAsJsonArray("commands")) {
            JsonObject command=item.getAsJsonObject();
            if(integer(command,"deadline_ms")<0)throw new IllegalArgumentException("invalid_action_deadline");
            long ticks=integer(command,"timeout_ticks");
            if(ticks<1||ticks>1200)throw new IllegalArgumentException("invalid_action_timeout");
        }
        return new BodyGrant(action,issued,expires,wall,nanos);
    }
    boolean fresh(long wall,long nanos) {
        if(invalid.get())return false;
        long observed=wallSeen.accumulateAndGet(wall,Math::max);
        boolean valid=wall>=observed&&wall>=issued&&wall<expires&&nanos-monotonicExpires<0;
        if(!valid)invalid.set(true);
        return valid;
    }
    JsonObject poll(long wall,long nanos) {
        if(!fresh(wall,nanos))return null;
        JsonArray commands=action.getAsJsonArray("commands");
        if(commands==null||commands.isEmpty())return action;
        JsonObject copy=new JsonObject();action.entrySet().forEach(e->copy.add(e.getKey(),e.getValue()));
        JsonArray bounded=new JsonArray();
        for(JsonElement item:commands) {
            JsonObject command=item.getAsJsonObject().deepCopy();
            long remaining=integer(command,"deadline_ms")-wall;
            int ticks=remaining>60_000?1200:(int)Math.max(1,(remaining+49)/50);
            command.addProperty("timeout_ticks",Math.min(command.get("timeout_ticks").getAsInt(),ticks));
            bounded.add(command);
        }
        copy.add("commands",bounded);return copy;
    }
}
