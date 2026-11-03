package gl.syn.minecraft;

import com.google.gson.*;
import java.net.URI;
import java.net.http.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Bounded network mailbox. World access and control application remain on the game thread. */
final class BodyStream implements AutoCloseable {
    private record Grant(JsonObject action,long received) {}
    private final HttpClient http;
    private final String name,epoch,token;
    private final URI endpoint;
    private final AtomicReference<Grant> latest=new AtomicReference<>();
    private final AtomicBoolean sending=new AtomicBoolean(),connecting=new AtomicBoolean();
    private final AtomicLong generation=new AtomicLong();
    private volatile WebSocket socket;
    private volatile long retryAfter;
    private volatile boolean closed;
    BodyStream(HttpClient http,String name,String epoch,String token) {
        this(http,name,epoch,token,URI.create("ws://127.0.0.1:8769/internal/body"));
    }
    BodyStream(HttpClient http,String name,String epoch,String token,URI endpoint) {
        this.http=http;this.name=name;this.epoch=epoch;this.token=token;this.endpoint=endpoint;
    }
    void connect() {
        if(closed||socket!=null||System.nanoTime()<retryAfter||!connecting.compareAndSet(false,true))return;
        long attempt=generation.incrementAndGet();
        http.newWebSocketBuilder().connectTimeout(java.time.Duration.ofSeconds(2))
            .buildAsync(endpoint,new WebSocket.Listener() {
                private final StringBuilder fragments=new StringBuilder();
                @Override public void onOpen(WebSocket ws) {
                    if(closed||generation.get()!=attempt){ws.abort();return;}
                    JsonObject auth=new JsonObject();auth.addProperty("agent",name);
                    auth.addProperty("body_epoch",epoch);auth.addProperty("token",token);
                    ws.sendText(auth.toString(),true).whenComplete((v,error)->{
                        if(error!=null||closed||generation.get()!=attempt) {ws.abort();failed(attempt);}
                        else {socket=ws;connecting.set(false);ws.request(1);}
                    });
                }
                @Override public CompletionStage<?> onText(WebSocket ws,CharSequence data,boolean last) {
                    if(generation.get()!=attempt||closed){ws.abort();return null;}
                    if(fragments.length()+data.length()>16384){ws.abort();failed(attempt);return null;}
                    fragments.append(data);
                    if(last) {
                        try {
                            JsonObject envelope=JsonParser.parseString(fragments.toString()).getAsJsonObject();
                            JsonObject action=envelope.getAsJsonObject("action");
                            if(!"control".equals(envelope.get("type").getAsString())||!epoch.equals(action.get("body_epoch").getAsString()))throw new IllegalArgumentException();
                            latest.set(new Grant(action,System.nanoTime()));
                        } catch(Exception ex) {ws.abort();failed(attempt);}
                        fragments.setLength(0);
                    }
                    ws.request(1);return null;
                }
                @Override public CompletionStage<?> onClose(WebSocket ws,int status,String reason) {failed(attempt);return null;}
                @Override public void onError(WebSocket ws,Throwable error) {failed(attempt);}
            }).whenComplete((ws,error)->{if(error!=null)failed(attempt);});
    }
    private void failed(long attempt) {
        if(generation.get()!=attempt)return;
        socket=null;latest.set(null);retryAfter=System.nanoTime()+2_000_000_000L;connecting.set(false);
    }
    JsonObject poll() {
        Grant grant=latest.get();
        if(socket==null||grant==null||System.nanoTime()-grant.received()>200_000_000L)return null;
        return grant.action();
    }
    boolean ready() {return socket!=null&&!sending.get();}
    boolean send(JsonObject observation) {
        WebSocket ws=socket;
        long attempt=generation.get();
        if(ws==null||!sending.compareAndSet(false,true))return false;
        try {
            ws.sendText(observation.toString(),true).whenComplete((v,error)->{
                sending.set(false);if(error!=null){ws.abort();failed(attempt);}
            });
        } catch(RuntimeException ex) {sending.set(false);ws.abort();failed(attempt);return false;}
        return true;
    }
    @Override public void close() {closed=true;generation.incrementAndGet();latest.set(null);WebSocket ws=socket;socket=null;if(ws!=null)ws.abort();}
}
