package gl.syn.minecraft;

import com.google.gson.*;
import java.util.*;
import java.util.function.Consumer;
import net.minecraft.core.*;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.protocol.game.ServerboundPlayerActionPacket;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.*;
import net.minecraft.world.entity.*;
import net.minecraft.world.item.*;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.*;

/** Tick-thread executor. Gateway grants authorize calls; native survival mechanics execute them. */
public final class PrimitiveControl {
    public static final List<String> CAPABILITIES=List.of("move_to","look_at","stop","cancel","select_slot","swap_hands","drop","jump","sneak","sprint","dig","place","use_item","release_use","use_on","attack","chat","query_blocks","query_recipes","query_recipe","query_inventory","open_container","move_item","close_container","craft");
    private final AgentPlayer body;
    private final NativeNavigator navigator;
    private final BodyInventory inventory;
    private final LinkedHashMap<String,JsonObject> results=new LinkedHashMap<>(),payloads=new LinkedHashMap<>();
    private String active, digging, using, lease;
    private int resultRotation;
    private static final Set<String> RESULT_CORE=Set.of("id","state","reason","body_epoch","tick");
    private static JsonObject compact(JsonObject row,String marker) {
        JsonObject copy=new JsonObject();for(String key:RESULT_CORE)if(row.has(key))copy.add(key,row.get(key));copy.addProperty(marker,true);return copy;
    }
    private JsonObject area;
    private BlockPos digPos;
    private BlockState digState;
    private ItemStack digTool;
    private int digTicks, useTicks;
    private boolean digStopped, breakAttempt, jumping,sneaking,sprinting;
    private Float lookYaw,lookPitch;
    private long lastChat=-1000;
    private Consumer<String> chatSink;
    private JsonArray queried=new JsonArray();
    private JsonArray inventorySnapshot;
    private long inventoryRevision;
    public long inventoryRevision(JsonArray snapshot) {if(!snapshot.equals(inventorySnapshot)){inventoryRevision++;inventorySnapshot=snapshot.deepCopy();}return inventoryRevision;}
    public final String epoch=UUID.randomUUID().toString();
    public PrimitiveControl(AgentPlayer body) {this.body=body;navigator=new NativeNavigator(body);inventory=new BodyInventory(body);}
    public void chatSink(Consumer<String> sink) {chatSink=sink;}
    private void result(String id,String state,String reason) {result(id,state,reason,null);}
    private void result(String id,String state,String reason,JsonObject details) {
        JsonObject row=new JsonObject();row.addProperty("id",id);row.addProperty("state",state);row.addProperty("reason",reason);row.addProperty("body_epoch",epoch);row.addProperty("tick",body.level().getGameTime());
        if(details!=null)for(var e:details.entrySet())row.add(e.getKey(),e.getValue());
        if(row.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8).length>400_000) {
            row=compact(row,"details_omitted");
            JsonObject request=payloads.get(id);String op=request!=null&&request.has("op")?request.get("op").getAsString():"";
            if(op.startsWith("query_")){row.addProperty("state","failed");row.addProperty("reason","query_result_too_large");}
        }
        // LinkedHashMap.put(existing) keeps insertion order: move updates to the tail so
        // a long-running action's terminal outcome cannot disappear when its channel clears.
        results.remove(id);results.put(id,row);
        // Never silently erase an unacknowledged outcome. Gateway admission bounds unfinished
        // commands (including pending full results); fully retained/orphan outcomes are ACKed.
        while(results.size()>512) {String oldest=null;for(var entry:results.entrySet())if(entry.getValue().has("details_retained_by_gateway")){oldest=entry.getKey();break;}if(oldest==null)break;results.remove(oldest);payloads.remove(oldest);}
    }
    public JsonArray observations() {
        JsonArray rows=new JsonArray();List<Map.Entry<String,JsonObject>> selected=new ArrayList<>();int skip=Math.max(0,results.size()-64),index=0;
        for(var entry:results.entrySet())if(index++>=skip||!entry.getValue().has("details_retained_by_gateway")||entry.getKey().equals(active)||entry.getKey().equals(digging)||entry.getKey().equals(using))selected.add(entry);
        if(!selected.isEmpty())Collections.rotate(selected,-Math.floorMod(resultRotation++,selected.size()));
        int budget=512_000;
        for(var entry:selected) {
            JsonObject row=entry.getValue();int bytes=row.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
            if(bytes<=budget){rows.add(row);budget-=bytes;}else rows.add(compact(row,"details_pending"));
        }
        return rows;
    }
    public JsonObject container() {return inventory.observe();}
    public JsonArray recipes() {return inventory.recipes();}
    public JsonArray queriedBlocks() {return queried;}
    public JsonObject state() {
        JsonObject o=new JsonObject();JsonArray running=new JsonArray();
        for(String id:new String[]{active,digging,using})if(id!=null)running.add(id);
        o.add("active_actions",running);o.addProperty("jump_requested",jumping);o.addProperty("sneak_requested",sneaking);o.addProperty("sprint_requested",sprinting);
        o.addProperty("on_ground",body.onGround());o.addProperty("sneaking",body.isShiftKeyDown());o.addProperty("sprinting",body.isSprinting());o.addProperty("using_item",body.isUsingItem());o.addProperty("use_ticks",body.getTicksUsingItem());
        if(digPos!=null) {o.add("dig_target",new Gson().toJsonTree(new int[]{digPos.getX(),digPos.getY(),digPos.getZ()}));o.addProperty("break_progress",Math.min(1,Math.max(0,digState.getDestroyProgress(body,body.level(),digPos)*(body.level().getGameTime()-digStarted+1))));}
        return o;
    }
    private long digStarted;
    public void broke(BlockPos p) {if(p.equals(digPos))breakAttempt=true;}
    private void abortDig(String reason) {
        if(digging!=null) {
            body.gameMode.handleBlockBreakAction(digPos,ServerboundPlayerActionPacket.Action.ABORT_DESTROY_BLOCK,Direction.UP,body.level().getMaxBuildHeight(),0);
            result(digging,"cancelled",reason);
        }
        digging=null;digPos=null;digState=null;digTool=null;
    }
    private void releaseUse(String reason) {
        if(body.isUsingItem())body.stopUsingItem();
        if(using!=null)result(using,"cancelled",reason);
        using=null;
    }
    public void cancel(String reason) {
        if(active!=null) {navigator.cancel(reason);result(active,"cancelled",reason);active=null;}
        abortDig(reason);releaseUse(reason);inventory.close(reason);
        if(body.containerMenu!=body.inventoryMenu)body.closeContainer();
        jumping=sneaking=sprinting=false;body.setShiftKeyDown(false);body.setSprinting(false);body.zza=body.xxa=0;lookYaw=lookPitch=null;
    }
    public void grant(JsonObject grant) {
        if(grant.has("acknowledged_results")&&grant.getAsJsonArray("acknowledged_results").size()<=512)for(JsonElement ack:grant.getAsJsonArray("acknowledged_results")) {
            String id=ack.getAsString();JsonObject row=results.get(id);
            if(row!=null&&Set.of("done","failed","cancelled").contains(row.get("state").getAsString()))results.put(id,compact(row,"details_retained_by_gateway"));
        }
        String incoming=grant.has("lease_id")&&!grant.get("lease_id").isJsonNull()?grant.get("lease_id").getAsString():null;
        if(!Objects.equals(incoming,lease)) {cancel("lease_changed");lease=incoming;}
        // Explicit null means unrestricted; missing/malformed grant data is not authority.
        if(!grant.has("area")||!(grant.get("area").isJsonNull()||grant.get("area").isJsonObject())) {
            cancel("invalid_work_area");lease=null;return;
        }
        area=grant.get("area").isJsonNull()?null:grant.getAsJsonObject("area");
        inventory.validateArea(area);
        if(incoming==null) {cancel("control_released");return;}
        JsonArray commands=grant.getAsJsonArray("commands");
        if(commands==null||commands.size()>32)return;
        for(JsonElement command:commands)if(command.isJsonObject())accept(command.getAsJsonObject());
    }
    private static Vec3 point(JsonObject action) {
        JsonArray p=action.getAsJsonArray("target");if(p==null||p.size()!=3)throw new NativeActionException("invalid_target");
        Vec3 v=new Vec3(p.get(0).getAsDouble(),p.get(1).getAsDouble(),p.get(2).getAsDouble());
        if(!Double.isFinite(v.x)||!Double.isFinite(v.y)||!Double.isFinite(v.z))throw new NativeActionException("invalid_target");return v;
    }
    private static BlockPos position(JsonObject action) {Vec3 p=point(action);if(p.x!=Math.floor(p.x)||p.y!=Math.floor(p.y)||p.z!=Math.floor(p.z))throw new NativeActionException("integer_block_position_required");return BlockPos.containing(p);}
    private static int integer(JsonObject o,String key,int min,int max) {
        double n=o.get(key).getAsDouble();if(!Double.isFinite(n)||n!=Math.floor(n)||n<min||n>max)throw new NativeActionException("invalid_"+key);return (int)n;
    }
    private InteractionHand hand(JsonObject action) {String name=action.has("hand")?action.get("hand").getAsString():"main";return switch(name){case "main"->InteractionHand.MAIN_HAND;case "off"->InteractionHand.OFF_HAND;default->throw new NativeActionException("invalid_hand");};}
    private void handFree() {if(digging!=null||using!=null||body.isUsingItem())throw new NativeActionException("hand_busy");}
    private void reach(BlockPos p) {if(!BodyAccess.reachable(body,p))throw new NativeActionException("out_of_reach_or_obstructed");}
    private static JsonObject semanticAction(JsonObject action) {
        JsonObject signature=action.deepCopy();
        // This is the gateway's remaining delivery budget, not a change to user intent.
        signature.remove("timeout_ticks");return signature;
    }
    public void accept(JsonObject action) {
        String id=action.has("id")?action.get("id").getAsString():"invalid";
        if(results.containsKey(id)) {
            // Gateway rejects changed payload retries; never perform either mutation twice.
            if(!semanticAction(action).equals(payloads.get(id)))return;
            JsonObject cached=results.remove(id);results.put(id,cached); // Resurface an unacknowledged result after network backpressure.
            return;
        }
        payloads.put(id,semanticAction(action));
        try {
            if(!epoch.equals(action.get("body_epoch").getAsString()))throw new NativeActionException("body_changed");
            if(!body.isAlive())throw new NativeActionException("dead");
            String op=action.get("op").getAsString();
            switch(op) {
                case "stop" -> {cancel("stopped");result(id,"done","stopped");}
                case "cancel" -> {
                    String target=action.get("action_id").getAsString();boolean found=false;
                    if(target.equals(active)){navigator.cancel("cancelled");result(active,"cancelled","cancelled");active=null;found=true;}
                    if(target.equals(digging)){abortDig("cancelled");found=true;}
                    if(target.equals(using)){releaseUse("cancelled");found=true;}
                    result(id,found||results.containsKey(target)?"done":"failed",found?"cancelled":results.containsKey(target)?"already_terminal":"unknown_action");
                }
                case "look_at" -> {Vec3 d=point(action).subtract(body.getEyePosition());lookYaw=(float)Math.toDegrees(Math.atan2(-d.x,d.z));lookPitch=(float)-Math.toDegrees(Math.atan2(d.y,Math.sqrt(d.x*d.x+d.z*d.z)));orient();result(id,"done","oriented");}
                case "move_to" -> {
                    if(active!=null){navigator.cancel("replaced");result(active,"cancelled","replaced");}
                    Vec3 p=point(action);navigator.start(p.x,p.y,p.z,integer(action,"timeout_ticks",1,1200));active=id;result(id,"started","path_search");
                }
                case "select_slot" -> {handFree();body.getInventory().selected=integer(action,"slot",0,8);body.getInventory().setChanged();result(id,"done","selected");}
                case "swap_hands" -> {handFree();ItemStack main=body.getMainHandItem(),off=body.getOffhandItem();body.setItemInHand(InteractionHand.MAIN_HAND,off);body.setItemInHand(InteractionHand.OFF_HAND,main);body.getInventory().setChanged();result(id,"done","swapped");}
                case "drop" -> {
                    handFree();int slot=integer(action,"slot",0,40),count=integer(action,"count",1,99);ItemStack stack=body.getInventory().getItem(slot);
                    if(stack.isEmpty()||stack.getCount()<count)throw new NativeActionException("insufficient_items");
                    int menuSlot=slot<9?36+slot:slot<36?slot:slot<40?44-slot:45;
                    if(!body.inventoryMenu.getSlot(menuSlot).mayPickup(body))throw new NativeActionException("item_cannot_be_removed");
                    // Spawn first, then decrement; failed spawning cannot consume inventory.
                    var entity=body.drop(stack.copyWithCount(count),false,true);if(entity==null)throw new NativeActionException("drop_rejected");
                    stack.shrink(count);body.getInventory().setChanged();JsonObject detail=new JsonObject();detail.addProperty("entity_id",entity.getId());result(id,"done","dropped",detail);
                }
                case "jump","sneak","sprint" -> {
                    boolean enabled=action.get("enabled").getAsBoolean();
                    if(op.equals("jump"))jumping=enabled;else if(op.equals("sneak")){sneaking=enabled;body.setShiftKeyDown(enabled);}else sprinting=enabled;
                    result(id,"done",enabled?"enabled":"released");
                }
                case "dig" -> {
                    handFree();BlockPos p=position(action);BodyAccess.require(body,p,area);reach(p);BlockState s=body.level().getBlockState(p);
                    if(s.isAir())throw new NativeActionException("target_air");if(s.getDestroySpeed(body.level(),p)<0)throw new NativeActionException("unbreakable");
                    if(!body.hasCorrectToolForDrops(s))throw new NativeActionException("wrong_tool");
                    int timeout=integer(action,"timeout_ticks",1,1200);digging=id;digPos=p;digState=s;digTool=body.getMainHandItem().copy();digTicks=timeout;digStarted=body.level().getGameTime();digStopped=false;breakAttempt=false;
                    result(id,"started","breaking");body.gameMode.handleBlockBreakAction(p,ServerboundPlayerActionPacket.Action.START_DESTROY_BLOCK,Direction.UP,body.level().getMaxBuildHeight(),0);
                }
                case "place" -> {handFree();place(action);result(id,"done","placed");}
                case "use_item" -> {
                    handFree();int timeout=integer(action,"timeout_ticks",1,1200);InteractionHand h=hand(action);ItemStack stack=body.getItemInHand(h);if(stack.isEmpty())throw new NativeActionException("empty_hand");
                    if(stack.getItem() instanceof BucketItem||stack.getItem() instanceof BlockItem)throw new NativeActionException("use_on_required");
                    InteractionResult outcome=body.gameMode.useItem(body,body.level(),stack,h);if(!outcome.consumesAction()&&!body.isUsingItem())throw new NativeActionException("use_rejected");
                    if(body.isUsingItem()){using=id;useTicks=timeout;result(id,"started","using");}else result(id,"done","used");
                }
                case "release_use" -> {if(body.isUsingItem())body.releaseUsingItem();if(using!=null)result(using,"done","released");using=null;result(id,"done","released");}
                case "use_on" -> {handFree();useOn(action);result(id,"done","interacted");}
                case "attack" -> {
                    handFree();Entity target=entity(action);if(target instanceof ServerPlayer&&!body.server.isPvpAllowed())throw new NativeActionException("pvp_disabled");
                    if(!target.isAttackable())throw new NativeActionException("not_attackable");if(body.getAttackStrengthScale(0)<1)throw new NativeActionException("attack_cooldown");
                    body.attack(target);body.swing(InteractionHand.MAIN_HAND);result(id,"done","attack_executed");
                }
                case "chat" -> {
                    String text=action.get("text").getAsString();if(text.isBlank()||text.length()>220||text.startsWith("/")||text.chars().anyMatch(c->c<32||c==127||c==167))throw new NativeActionException("invalid_chat");
                    if(body.level().getGameTime()-lastChat<40)throw new NativeActionException("chat_rate_limited");if(chatSink==null)throw new NativeActionException("chat_unavailable");
                    chatSink.accept(text);lastChat=body.level().getGameTime();result(id,"done","delivered");
                }
                case "query_blocks" -> {queried=query(action);JsonObject detail=new JsonObject();detail.add("blocks",queried);result(id,"done","observed",detail);}
                case "query_recipes","query_recipe","query_inventory","close_container" -> result(id,"done",op,inventory.execute(action,area));
                case "open_container","move_item","craft" -> {handFree();result(id,"done",op,inventory.execute(action,area));}
                default -> result(id,"failed","unsupported_operation");
            }
        } catch(NativeActionException ex) {result(id,"failed",ex.getMessage()==null?"invalid_arguments":ex.getMessage());}
        catch(Exception ex) {unknown(id);}
    }
    private void unknown(String id) {
        JsonObject details=new JsonObject();details.addProperty("reconciliation_required",true);details.addProperty("side_effects","unknown");
        result(id,"failed","outcome_unknown_executor_error",details);
    }
    private Entity entity(JsonObject action) {
        Entity target=body.level().getEntity(integer(action,"entity_id",0,Integer.MAX_VALUE));
        if(target==null||target==body||!target.isAlive())throw new NativeActionException("entity_missing");
        if(body.getEyePosition().distanceToSqr(target.getBoundingBox().getCenter())>9||!body.hasLineOfSight(target))throw new NativeActionException("out_of_reach_or_obstructed");return target;
    }
    private Direction face(JsonObject action) {Direction d=Direction.byName(action.get("face").getAsString());if(d==null)throw new NativeActionException("invalid_face");return d;}
    private BlockHitResult hit(BlockPos p,Direction face) {
        var shape=body.level().getBlockState(p).getShape(body.level(),p);
        if(shape.isEmpty())throw new NativeActionException("target_has_no_interaction_shape");
        AABB bounds=shape.bounds();Vec3 center=bounds.getCenter();
        Vec3 hit=new Vec3(p.getX()+(face==Direction.WEST?bounds.minX:face==Direction.EAST?bounds.maxX:center.x),
            p.getY()+(face==Direction.DOWN?bounds.minY:face==Direction.UP?bounds.maxY:center.y),
            p.getZ()+(face==Direction.NORTH?bounds.minZ:face==Direction.SOUTH?bounds.maxZ:center.z));
        if(body.getEyePosition().distanceToSqr(hit)>20.25)throw new NativeActionException("out_of_reach");
        BlockHitResult trace=body.level().clip(new ClipContext(body.getEyePosition(),hit.relative(face,-.001),ClipContext.Block.OUTLINE,ClipContext.Fluid.NONE,body));
        if(trace.getType()!=HitResult.Type.BLOCK||!trace.getBlockPos().equals(p)||trace.getDirection()!=face)throw new NativeActionException("face_obstructed");return new BlockHitResult(hit,face,p,false);
    }
    private void place(JsonObject action) {
        InteractionHand hand=hand(action);ItemStack held=body.getItemInHand(hand);
        if(held.isEmpty())throw new NativeActionException("empty_hand");if(!(held.getItem() instanceof BlockItem item))throw new NativeActionException("not_block_item");
        // Destination coordinates; adjacent support is opposite the requested clicked face.
        BlockPos destination=position(action);Direction face=face(action);BlockPos support=destination.relative(face.getOpposite());
        BodyAccess.require(body,destination,area);BodyAccess.require(body,support,area);reach(support);
        if(!body.level().getBlockState(destination).canBeReplaced())throw new NativeActionException("destination_occupied");
        Block block=item.getBlock();
        if(!BuiltInRegistries.BLOCK.getKey(block).getNamespace().equals("minecraft")||block instanceof ScaffoldingBlock)throw new NativeActionException("unsupported_placement_footprint");
        if(body.level().getBlockState(support).canBeReplaced())throw new NativeActionException("replaceable_support");
        List<BlockPos> affected=new ArrayList<>();affected.add(destination);
        if(block instanceof DoorBlock||block instanceof DoublePlantBlock)affected.add(destination.above());
        if(block instanceof BedBlock)affected.add(destination.relative(body.getDirection()));
        for(BlockPos pos:affected) {
            BodyAccess.require(body,pos,area);
            if(!body.level().getBlockState(pos).canBeReplaced())throw new NativeActionException("destination_occupied");
            if(body.getBoundingBox().intersects(new AABB(pos))||!body.level().getEntities(body,new AABB(pos),e->e instanceof LivingEntity).isEmpty())throw new NativeActionException("entity_collision");
        }
        BlockHitResult targetHit=hit(support,face);
        var placement=new net.minecraft.world.item.context.BlockPlaceContext(body,hand,held,targetHit);
        if(!placement.getClickedPos().equals(destination))throw new NativeActionException("placement_redirected");
        BlockState before=body.level().getBlockState(destination);int count=held.getCount();
        // Sneaking bypasses support activation, so clicking a chest places instead of opening it.
        boolean shifted=body.isShiftKeyDown();InteractionResult outcome;
        body.setShiftKeyDown(true);
        try {outcome=body.gameMode.useItemOn(body,body.level(),held,hand,targetHit);}
        finally {body.setShiftKeyDown(shifted);}
        if(!outcome.consumesAction()||body.level().getBlockState(destination).equals(before)||held.getCount()!=count-1)throw new NativeActionException("placement_rejected");
    }
    private void useOn(JsonObject action) {
        InteractionHand hand=hand(action);ItemStack held=body.getItemInHand(hand);InteractionResult outcome;
        if(action.has("entity_id")) {
            Entity entity=entity(action);BodyAccess.require(body,entity.blockPosition(),area);
            var previousMenu=body.containerMenu;outcome=body.interactOn(entity,hand);
            if(body.containerMenu!=previousMenu){body.closeContainer();throw new NativeActionException("unsupported_entity_menu");}
        }
        else {
            BlockPos pos=position(action);BodyAccess.require(body,pos,area);reach(pos);Direction face=face(action);
            BodyAccess.require(body,pos.relative(face),area);
            BlockState block=body.level().getBlockState(pos);
            if(block.getBlock() instanceof DoorBlock)BodyAccess.require(body,block.getValue(DoorBlock.HALF)==net.minecraft.world.level.block.state.properties.DoubleBlockHalf.LOWER?pos.above():pos.below(),area);
            if(held.getItem() instanceof BlockItem||held.getItem() instanceof BucketItem||held.getItem() instanceof BoneMealItem)throw new NativeActionException("unsupported_use_footprint");
            // Container state must only be opened through the session API.
            if(block.hasBlockEntity()||block.getMenuProvider(body.level(),pos)!=null)throw new NativeActionException("open_container_required");
            outcome=body.gameMode.useItemOn(body,body.level(),held,hand,hit(pos,face));
        }
        if(!outcome.consumesAction())throw new NativeActionException("interaction_rejected");
    }
    private JsonArray query(JsonObject action) {
        List<BlockPos> positions=new ArrayList<>();
        if(action.has("positions")) {
            JsonArray array=action.getAsJsonArray("positions");if(array.size()>64)throw new NativeActionException("query_too_large");
            for(JsonElement p:array){JsonObject row=new JsonObject();row.add("target",p);positions.add(position(row));}
        } else {BlockPos center=position(action);int radius=integer(action,"radius",0,4);for(int x=-radius;x<=radius;x++)for(int y=-radius;y<=radius;y++)for(int z=-radius;z<=radius;z++)positions.add(center.offset(x,y,z));}
        JsonArray out=new JsonArray();for(BlockPos p:positions) {
            if(p.distSqr(body.blockPosition())>32*32)throw new NativeActionException("query_out_of_range");
            JsonObject row=new JsonObject();row.add("position",new Gson().toJsonTree(new int[]{p.getX(),p.getY(),p.getZ()}));row.addProperty("dimension",body.level().dimension().location().toString());row.addProperty("tick",body.level().getGameTime());
            boolean loaded=body.level().hasChunkAt(p);row.addProperty("loaded",loaded);
            if(loaded) {BlockState state=body.level().getBlockState(p);row.addProperty("block",BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString());JsonObject props=new JsonObject();state.getValues().forEach((key,value)->props.addProperty(key.getName(),value.toString()));row.add("properties",props);row.addProperty("replaceable",state.canBeReplaced());row.addProperty("destroy_speed",state.getDestroySpeed(body.level(),p));}
            out.add(row);
        }return out;
    }
    private void orient() {if(lookYaw!=null){body.setYRot(lookYaw);body.setYHeadRot(lookYaw);body.setXRot(lookPitch);}}
    public void tick(long deadline) {
        if(active!=null) {
            navigator.tick(deadline);
            if(!navigator.state().equals("started")) {result(active,navigator.state(),navigator.reason());active=null;}
            else if(lookYaw!=null) {double angle=Math.toRadians(body.getYRot()-lookYaw);float speed=body.zza;body.zza=(float)(speed*Math.cos(angle));body.xxa=(float)(-speed*Math.sin(angle));}
        }
        orient();body.setShiftKeyDown(sneaking);body.setSprinting(sprinting&&body.getFoodData().getFoodLevel()>6&&body.zza>0&&!sneaking&&!body.isUsingItem()&&!body.horizontalCollision);
        if(sneaking){body.zza*=.3f;body.xxa*=.3f;}
        if(jumping&&body.onGround())body.jumpFromGround();
        if(digging!=null) {
            try {
                BodyAccess.require(body,digPos,area);
                BlockState now=body.level().getBlockState(digPos);
                if(now.isAir()&&breakAttempt){result(digging,"done","broken");digging=null;digPos=null;return;}
                if(!now.equals(digState))throw new NativeActionException("target_changed");reach(digPos);
                if(!ItemStack.isSameItemSameComponents(digTool,body.getMainHandItem()))throw new NativeActionException("held_item_changed");
                if(--digTicks<=0)throw new NativeActionException("timeout");
                if(!digStopped){body.gameMode.handleBlockBreakAction(digPos,ServerboundPlayerActionPacket.Action.STOP_DESTROY_BLOCK,Direction.UP,body.level().getMaxBuildHeight(),0);digStopped=true;}
                body.swing(InteractionHand.MAIN_HAND);
            }catch(NativeActionException ex){String id=digging;abortDig(ex.getMessage());result(id,"failed",ex.getMessage());}
            catch(Exception ex){String id=digging;try{abortDig("executor_error");}catch(Exception ignored){}digging=null;digPos=null;unknown(id);}
        }
        if(using!=null) {
            if(!body.isUsingItem()){result(using,"done","use_finished");using=null;}
            else if(--useTicks<=0){String id=using;releaseUse("timeout");result(id,"failed","timeout");}
        }
    }
}
