package gl.syn.minecraft;
import com.google.gson.*;
import java.net.URI;
import java.net.http.HttpClient;

/** Used by the isolated Python WebSocket peer; never creates a Minecraft player. */
public final class BodyStreamProbe {
    public static void main(String[] args) throws Exception {
        try(BodyStream stream=new BodyStream(HttpClient.newHttpClient(),"Probe","probe-epoch","test-secret",URI.create(args[0]))) {
            long deadline=System.nanoTime()+5_000_000_000L;
            while(!stream.ready()) {stream.connect();Thread.sleep(5);if(System.nanoTime()>deadline)throw new AssertionError("connect timeout");}
            JsonObject frame=new JsonObject();frame.addProperty("agent","Probe");frame.addProperty("tick",1);
            if(!stream.send(frame))throw new AssertionError("first send rejected");
            JsonObject action;
            while((action=stream.poll())==null) {Thread.sleep(5);if(System.nanoTime()>deadline)throw new AssertionError("grant timeout");}
            if(!"probe-action".equals(action.get("id").getAsString()))throw new AssertionError("wrong action");
            Thread.sleep(300);
            if(stream.poll()!=null)throw new AssertionError("stalled bridge kept a grant alive");
            stream.close();
            if(stream.poll()!=null)throw new AssertionError("closed bridge kept a grant");
            System.out.println("BodyStream handshake, telemetry, control, 200ms expiry and close checks passed");
        }
    }
}
