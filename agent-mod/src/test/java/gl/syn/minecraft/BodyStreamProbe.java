package gl.syn.minecraft;
import com.google.gson.*;
import java.net.URI;
import java.net.http.HttpClient;

/** Used by the isolated Python WebSocket peer; never creates a Minecraft player. */
public final class BodyStreamProbe {
    public static void main(String[] args) throws Exception {
        try(BodyStream stream=new BodyStream(HttpClient.newHttpClient(),"Probe","probe-epoch","test-secret",URI.create(args[0]))) {
            long deadline=System.nanoTime()+20_000_000_000L;
            while(!stream.ready()) {stream.connect();Thread.sleep(5);if(System.nanoTime()>deadline)throw new AssertionError("connect timeout");}
            JsonObject frame=new JsonObject();frame.addProperty("agent","Probe");frame.addProperty("tick",1);
            if(!stream.send(frame))throw new AssertionError("first send rejected");
            JsonObject unsent=frame.deepCopy();unsent.addProperty("tick",999);
            if(stream.ready()||stream.send(unsent))throw new AssertionError("unprocessed observation did not apply backpressure");
            JsonObject action;
            while((action=stream.poll())==null) {Thread.sleep(5);if(System.nanoTime()>deadline)throw new AssertionError("grant timeout");}
            if(!"probe-action".equals(action.get("id").getAsString()))throw new AssertionError("wrong action");
            frame.addProperty("tick",2);while(!stream.ready())Thread.sleep(2);stream.send(frame);
            Thread.sleep(350);
            if(stream.poll()!=null)throw new AssertionError("queued stale frame renewed a grant on arrival");
            frame.addProperty("tick",3);while(!stream.ready())Thread.sleep(2);stream.send(frame);
            while((action=stream.poll())==null){Thread.sleep(5);if(System.nanoTime()>deadline)throw new AssertionError("stop grant timeout");}
            if(!"probe-stop".equals(action.get("id").getAsString())||!action.getAsJsonArray("commands").isEmpty())throw new AssertionError("fresh stop grant missing");
            frame.addProperty("tick",4);while(!stream.ready())Thread.sleep(2);stream.send(frame);
            long stalled=System.nanoTime();
            while(!stream.ready()) {stream.connect();Thread.sleep(5);if(System.nanoTime()>deadline)throw new AssertionError("ACK stall failed to reconnect");}
            if(System.nanoTime()-stalled<2_000_000_000L)throw new AssertionError("missing ACK did not hold frame backpressure");
            frame.addProperty("tick",5);if(!stream.send(frame))throw new AssertionError("new socket retained old pending observation");
            while((action=stream.poll())==null){Thread.sleep(5);if(System.nanoTime()>deadline)throw new AssertionError("reconnected grant timeout");}
            if(!"probe-reconnected".equals(action.get("id").getAsString()))throw new AssertionError("old grant survived reconnect");
            Thread.sleep(300);
            if(stream.poll()!=null)throw new AssertionError("stalled bridge kept a grant alive");
            stream.close();
            if(stream.poll()!=null)throw new AssertionError("closed bridge kept a grant");
            System.out.println("BodyStream ACK backpressure/stall reconnect, no replay, stale grants, fresh stop, 200ms expiry and close checks passed");
        }
    }
}
