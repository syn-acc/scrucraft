package gl.syn.minecraft;
import com.google.gson.*;
import java.util.*;
import net.minecraft.world.phys.Vec3;

/** First direct-control milestone: navigation, orientation, cancellation and receipts. */
public final class PrimitiveControl {
    private final AgentPlayer body;
    private final NativeNavigator navigator;
    private final LinkedHashMap<String,JsonObject> results=new LinkedHashMap<>();
    private String active;
    public final String epoch=UUID.randomUUID().toString();
    public PrimitiveControl(AgentPlayer body) {this.body=body;navigator=new NativeNavigator(body);}
    private void result(String id,String state,String reason) {
        JsonObject row=new JsonObject();row.addProperty("id",id);row.addProperty("state",state);
        row.addProperty("reason",reason);row.addProperty("body_epoch",epoch);
        results.put(id,row);
        while(results.size()>64)results.remove(results.keySet().iterator().next());
    }
    public JsonArray observations() {JsonArray rows=new JsonArray();results.values().forEach(rows::add);return rows;}
    public void cancel(String reason) {
        if(active!=null) {navigator.cancel(reason);result(active,"cancelled",reason);active=null;}
    }
    public void accept(JsonObject action) {
        String id=action.get("id").getAsString();
        if(results.containsKey(id))return;
        if(!epoch.equals(action.get("body_epoch").getAsString())) {result(id,"failed","body_changed");return;}
        cancel("replaced");
        try {
            String op=action.get("op").getAsString();
            if(op.equals("stop")) {body.zza=0;body.xxa=0;result(id,"done","stopped");return;}
            JsonArray p=action.getAsJsonArray("target");
            if(p.size()!=3)throw new IllegalArgumentException();
            Vec3 point=new Vec3(p.get(0).getAsDouble(),p.get(1).getAsDouble(),p.get(2).getAsDouble());
            if(!Double.isFinite(point.x)||!Double.isFinite(point.y)||!Double.isFinite(point.z))throw new IllegalArgumentException();
            if(op.equals("look_at")) {
                Vec3 d=point.subtract(body.getEyePosition());
                body.setYRot((float)Math.toDegrees(Math.atan2(-d.x,d.z)));
                body.setYHeadRot(body.getYRot());
                body.setXRot((float)-Math.toDegrees(Math.atan2(d.y,Math.sqrt(d.x*d.x+d.z*d.z))));
                result(id,"done","oriented");return;
            }
            if(!op.equals("move_to")) {result(id,"failed","unsupported_operation");return;}
            navigator.start(point.x,point.y,point.z,action.get("timeout_ticks").getAsInt());
            active=id;result(id,"started","path_search");
        } catch(Exception ex) {result(id,"failed","invalid_arguments");}
    }
    public void tick(long deadline) {
        if(active==null)return;
        navigator.tick(deadline);
        if(!navigator.state().equals("started")) {
            result(active,navigator.state(),navigator.reason());active=null;
        }
    }
}
