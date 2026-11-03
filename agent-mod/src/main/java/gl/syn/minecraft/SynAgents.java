package gl.syn.minecraft;

import com.google.gson.*;
import com.mojang.logging.LogUtils;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import net.minecraft.commands.Commands;
import net.minecraft.core.*;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.game.ServerboundPlayerActionPacket;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.*;
import net.minecraft.server.network.CommonListenerCookie;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.*;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.item.*;
import net.minecraft.world.item.crafting.*;
import net.minecraft.world.level.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.*;
import net.neoforged.fml.common.Mod;
import net.neoforged.neoforge.common.NeoForge;
import net.neoforged.neoforge.event.RegisterCommandsEvent;
import net.neoforged.neoforge.event.ServerChatEvent;
import net.neoforged.neoforge.event.server.*;
import net.neoforged.neoforge.event.tick.ServerTickEvent;

@Mod("synagents")
public final class SynAgents {
    private static final org.slf4j.Logger LOG=LogUtils.getLogger();
    private static final Gson JSON=new Gson();
    private static final Set<String> JOBS=Set.of("farmer","miner","builder","guard","medic","engineer");
    private static final Path CONFIG=Path.of("config/syn-agents.json");
    private final Map<String,AgentPlayer> agents=new LinkedHashMap<>();
    private final Map<String,JsonObject> plans=new HashMap<>();
    private final Map<String,Long> expiries=new HashMap<>();
    private final Map<String,BlockPos> breaking=new HashMap<>();
    private final Map<String,Long> respawns=new HashMap<>();
    private final Set<String> inFlight=new HashSet<>();
    private final Set<String> loading=new HashSet<>();
    private final Set<String> miningStopped=new HashSet<>();
    private final Deque<JsonObject> chat=new ArrayDeque<>();
    private final Map<String,String> lastSpeech=new HashMap<>(),lastAction=new HashMap<>();
    private final Map<String,Long> speechTicks=new HashMap<>();
    private SettlementProject project;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(1)).build();
    private MinecraftServer server;
    private long ticks;
    private String token="";
    private JsonObject config=new JsonObject();

    public SynAgents() {
        NeoForge.EVENT_BUS.addListener(this::start);
        NeoForge.EVENT_BUS.addListener(this::stop);
        NeoForge.EVENT_BUS.addListener(this::tick);
        NeoForge.EVENT_BUS.addListener(this::commands);
        NeoForge.EVENT_BUS.addListener(this::chat);
    }
    private void start(ServerStartedEvent e) {
        server=e.getServer();
        try {
            if (Files.exists(CONFIG)) config=JSON.fromJson(Files.readString(CONFIG),JsonObject.class);
            if(config.has("settlement")) project=SettlementProject.load(config.getAsJsonObject("settlement"));
            Path tokenPath=Path.of("../agent-service/token");
            if (Files.exists(tokenPath)) token=Files.readString(tokenPath).trim();
            var rules=server.overworld().getGameRules();
            rules.getRule(GameRules.RULE_KEEPINVENTORY).set(false,server);
            rules.getRule(GameRules.RULE_NATURAL_REGENERATION).set(true,server);
            rules.getRule(GameRules.RULE_DAYLIGHT).set(true,server);
            rules.getRule(GameRules.RULE_PLAYERS_SLEEPING_PERCENTAGE).set(50,server);
            if (config.has("agents")) for (JsonElement row:config.getAsJsonArray("agents")) {
                JsonObject a=row.getAsJsonObject(); spawn(a.get("name").getAsString(),a.get("job").getAsString());
            }
        } catch(Exception ex) { LOG.error("Agent startup failed",ex); }
    }
    private void stop(ServerStoppingEvent e) {
        for (AgentPlayer a:List.copyOf(agents.values())) server.getPlayerList().remove(a);
        agents.clear();
    }
    private void spawn(String name,String job) {
        if (!AgentNames.valid(name) || !JOBS.contains(job) || agents.size()+loading.size()>=10
            || AgentNames.conflicts(name,agents.keySet()) || AgentNames.conflicts(name,loading)
            || AgentNames.conflicts(name,java.util.Arrays.asList(server.getPlayerList().getWhiteListNames()))
            || server.getPlayerList().getPlayerByName(name)!=null) throw new IllegalArgumentException("Invalid/reserved agent name, role, or agent cap");
        loading.add(name);
        UUID id=UUID.nameUUIDFromBytes(("syn-agent:"+name).getBytes(java.nio.charset.StandardCharsets.UTF_8));
        net.luckperms.api.LuckPermsProvider.get().getUserManager().loadUser(id,name).whenComplete((user,error)->server.execute(()->{
            loading.remove(name);
            if(error!=null) { LOG.error("Cannot load agent permissions for {}",name,error); return; }
            try { spawnLoaded(name,job); saveConfig(); } catch(Exception ex) { LOG.error("Agent login failed for {}",name,ex); }
        }));
    }
    private void spawnLoaded(String name,String job) {
        if (server.getPlayerList().getPlayerByName(name)!=null
            || AgentNames.conflicts(name,java.util.Arrays.asList(server.getPlayerList().getWhiteListNames())))
            throw new IllegalArgumentException("Agent name conflicts with a human player");
        AgentPlayer a=new AgentPlayer(server.overworld(),name,job);
        // The pinned LP build normally initializes this during network login.
        // Internal players have no network configuration phase. Load their
        // user asynchronously above, then run the same LP post-login adapter
        // before command permissions can be queried during placeNewPlayer.
        try {
            Object api=net.luckperms.api.LuckPermsProvider.get();
            var field=api.getClass().getDeclaredField("plugin"); field.setAccessible(true);
            Object plugin=field.get(api);
            Object listener=plugin.getClass().getMethod("getConnectionListener").invoke(plugin);
            listener.getClass().getMethod("onPlayerLoggedIn",net.neoforged.neoforge.event.entity.player.PlayerEvent.PlayerLoggedInEvent.class)
                .invoke(listener,new net.neoforged.neoforge.event.entity.player.PlayerEvent.PlayerLoggedInEvent(a));
        } catch(ReflectiveOperationException ex) { throw new IllegalStateException("Pinned LuckPerms internal-player adapter failed",ex); }
        var c=new AgentPlayer.LocalConnection();
        server.getPlayerList().placeNewPlayer(c,a,CommonListenerCookie.createInitial(a.getGameProfile(),false));
        a.attachListener(c);
        a.setGameMode(GameType.SURVIVAL);
        agents.put(name,a);
        LOG.info("Spawned survival agent {} ({})",name,job);
    }
    private void tick(ServerTickEvent.Post e) {
        if (server==null) return;
        ticks++;
        long navigationDeadline=System.nanoTime()+1_000_000;
        boolean humans=server.getPlayerList().getPlayers().stream().anyMatch(p->!(p instanceof AgentPlayer));
        // Vanilla advances once per tick. Cancel one third of those advances,
        // preserving vanilla sleep-to-morning and other daylight behavior.
        if ((!humans && agents.isEmpty()) || ticks%3==0) for (ServerLevel l:server.getAllLevels()) if (l.dimensionType().hasSkyLight() && l.getGameRules().getBoolean(GameRules.RULE_DAYLIGHT)) l.setDayTime(l.getDayTime()-1);
        for (AgentPlayer a:List.copyOf(agents.values())) {
            if (!a.isAlive()) {
                a.controls.cancel("dead");
                long due=respawns.computeIfAbsent(a.getGameProfile().getName(),n->ticks+200);
                if (ticks>=due) try { respawn(a); } catch(Exception ex) { LOG.error("Agent respawn failed",ex); respawns.put(a.getGameProfile().getName(),ticks+600); }
                continue;
            }
            try {
                String name=a.getGameProfile().getName();
                JsonObject plan=plans.get(name);
                if (plan!=null && ticks<=expiries.getOrDefault(name,0L)) act(a,plan);
                else { a.controls.cancel("control_expired"); a.zza=0; a.xxa=0; abortMining(a); }
                a.controls.tick(navigationDeadline);
                // Emergency reactions run locally even when inference is down.
                if (ticks%20==0 && a.getFoodData().getFoodLevel()<12) consume(a);
                if (ticks%20==0 && !inFlight.contains(name) && !token.isBlank()) request(a);
            } catch(Exception ex) { LOG.error("Agent {} step failed",a.getGameProfile().getName(),ex); }
        }
    }
    private void respawn(AgentPlayer old) {
        String name=old.getGameProfile().getName(), job=old.job;
        AgentPlayer fresh=(AgentPlayer)server.getPlayerList().respawn(old,false,Entity.RemovalReason.KILLED);
        agents.put(name,fresh);
        plans.remove(name); breaking.remove(name); respawns.remove(name);
    }
    private JsonObject observation(AgentPlayer a) {
        long began=System.nanoTime();
        JsonObject o=new JsonObject();
        o.addProperty("body_epoch",a.controls.epoch);
        JsonArray raw=new JsonArray();for(String op:List.of("move_to","look_at","stop"))raw.add(op);
        o.add("raw_capabilities",raw);o.add("action_results",a.controls.observations());
        o.addProperty("schema",1); o.addProperty("agent",a.getGameProfile().getName()); o.addProperty("job",a.job);
        o.addProperty("tick",ticks); o.addProperty("dimension",a.level().dimension().location().toString());
        o.add("position",JSON.toJsonTree(new double[]{a.getX(),a.getY(),a.getZ()}));
        o.addProperty("health",a.getHealth()); o.addProperty("food",a.getFoodData().getFoodLevel());
        // Neutral schema-1 compatibility values: vanilla has neither mechanic.
        o.addProperty("thirst",20);
        o.addProperty("temperature",20);
        o.addProperty("night",a.level().isNight()); o.addProperty("raining",a.level().isRaining());
        o.addProperty("sheltered",!a.level().canSeeSky(a.blockPosition()));
        o.addProperty("last_action",lastAction.getOrDefault(a.getGameProfile().getName(),"starting"));
        ProgressionAdapter.metadata(a,o);
        JsonArray context=new JsonArray(); chat.forEach(context::add); o.add("chat",context);
        JsonArray teammates=new JsonArray(),humans=new JsonArray();
        for(ServerPlayer p:server.getPlayerList().getPlayers()) {
            if(p==a||p.level()!=a.level()) continue;
            JsonObject row=new JsonObject();row.addProperty("name",p.getGameProfile().getName());row.add("position",JSON.toJsonTree(new double[]{p.getX(),p.getY(),p.getZ()}));
            if(p instanceof AgentPlayer agent) { row.addProperty("job",agent.job); row.addProperty("action",lastAction.getOrDefault(agent.getGameProfile().getName(),"starting"));teammates.add(row); } else humans.add(row);
        }
        o.add("teammates",teammates);o.add("humans",humans);
        if(project!=null) o.add("project",project.observe(a));
        JsonArray inv=new JsonArray();
        for (int i=0;i<a.getInventory().items.size();i++) {
            ItemStack s=a.getInventory().getItem(i); if (s.isEmpty()) continue;
            JsonObject row=new JsonObject(); row.addProperty("slot",i); row.addProperty("item",BuiltInRegistries.ITEM.getKey(s.getItem()).toString()); row.addProperty("count",s.getCount());
            row.addProperty("food",s.has(DataComponents.FOOD));
            row.addProperty("damage",s.getDamageValue());row.addProperty("max_damage",s.getMaxDamage());
            row.addProperty("hydration",0);
            inv.add(row);
        }
        o.add("inventory",inv);
        JsonArray entities=new JsonArray();
        for (Entity ent:a.level().getEntities(a,a.getBoundingBox().inflate(16),ent->ent instanceof Monster&&(!(ent instanceof net.minecraft.world.entity.monster.EnderMan end)||end.getTarget()==a) || ent instanceof net.minecraft.world.entity.item.ItemEntity)) {
            JsonObject row=new JsonObject(); row.addProperty("id",ent.getId()); row.addProperty("type",BuiltInRegistries.ENTITY_TYPE.getKey(ent.getType()).toString());
            row.addProperty("hostile",ent instanceof Monster); row.add("position",JSON.toJsonTree(new double[]{ent.getX(),ent.getY(),ent.getZ()})); entities.add(row);
            if (entities.size()>=24) break;
        }
        o.add("entities",entities);
        JsonArray blocks=new JsonArray(),walkable=new JsonArray(),workstations=new JsonArray();
        List<JsonObject> resources=new ArrayList<>();
        BlockPos origin=a.blockPosition();
        for (int dx=-12;dx<=12;dx++) for(int dz=-12;dz<=12;dz++) for(int dy=-8;dy<=8;dy++) {
            BlockPos p=origin.offset(dx,dy,dz); if (!a.level().hasChunkAt(p)) continue;
            BlockState s=a.level().getBlockState(p);
            if(Math.abs(dx)<=8&&Math.abs(dz)<=8&&Math.abs(dy)<=6) {
                JsonObject workstation=ProgressionAdapter.workstation(a,p,s);if(workstation!=null&&workstations.size()<48)workstations.add(workstation);
            }
            boolean stone=s.is(Blocks.STONE)||s.is(Blocks.DEEPSLATE)||s.is(Blocks.ANDESITE);
            // Dense rock is exposed only when actually reachable; do not send entire underground volumes.
            boolean resource=ProgressionAdapter.resource(s)&&(!stone||a.getEyePosition().distanceToSqr(Vec3.atCenterOf(p))<=20.25&&reachable(a,p));
            if (Math.abs(dx)<=8&&Math.abs(dz)<=8&&Math.abs(dy)<=6&&(s.is(BlockTags.LOGS)||s.getBlock() instanceof CropBlock || s.getBlock() instanceof ChestBlock || resource||s.getFluidState().isSource())) {
                JsonObject row=new JsonObject(); row.add("pos",JSON.toJsonTree(new int[]{p.getX(),p.getY(),p.getZ()})); row.addProperty("block",BuiltInRegistries.BLOCK.getKey(s.getBlock()).toString());
                row.addProperty("mature",s.getBlock() instanceof CropBlock crop && crop.isMaxAge(s)); resources.add(row);
                row.addProperty("reachable",reachable(a,p));
                int tool=ProgressionAdapter.toolSlot(a,s);row.addProperty("harvestable",tool>=0);row.addProperty("tool_slot",tool);
                BlockPos obstruction=a.level().clip(new ClipContext(a.getEyePosition(),Vec3.atCenterOf(p),ClipContext.Block.COLLIDER,ClipContext.Fluid.NONE,a)).getBlockPos();
                if(s.is(BlockTags.LOGS)&&a.level().getBlockState(obstruction).is(BlockTags.LEAVES)&&reachable(a,obstruction)) row.add("clear_leaf",SettlementProject.pos(obstruction));
            }
            if (s.getCollisionShape(a.level(),p).isEmpty() && s.getFluidState().isEmpty() && a.level().getBlockState(p.above()).getCollisionShape(a.level(),p.above()).isEmpty() && a.level().getBlockState(p.below()).isFaceSturdy(a.level(),p.below(),Direction.UP) && !a.level().getBlockState(p.below()).is(Blocks.MAGMA_BLOCK) && !a.level().getBlockState(p.below()).is(Blocks.CAMPFIRE)) {
                JsonObject row=new JsonObject(); row.add("pos",JSON.toJsonTree(new int[]{p.getX(),p.getY(),p.getZ()})); row.addProperty("sheltered",!a.level().canSeeSky(p));row.addProperty("jump_room",a.level().getBlockState(p.above(2)).getCollisionShape(a.level(),p.above(2)).isEmpty()); walkable.add(row);
            }
        }
        resources.sort(Comparator.comparingDouble(row->{ JsonArray p=row.getAsJsonArray("pos");return a.position().distanceToSqr(p.get(0).getAsDouble()+.5,p.get(1).getAsDouble()+.5,p.get(2).getAsDouble()+.5); }));
        resources.stream().limit(192).forEach(blocks::add);
        o.add("blocks",blocks); o.add("walkable",walkable);o.add("workstations",workstations);
        o.addProperty("observation_ms",(System.nanoTime()-began)/1_000_000.0);
        return o;
    }
    private void request(AgentPlayer a) {
        String name=a.getGameProfile().getName(); inFlight.add(name);
        JsonObject snap=observation(a); long sourceTick=ticks;
        HttpRequest req=HttpRequest.newBuilder(URI.create("http://127.0.0.1:8767/v1/decide"))
            .timeout(Duration.ofSeconds(3)).header("Authorization","Bearer "+token).header("Content-Type","application/json")
            .POST(HttpRequest.BodyPublishers.ofString(JSON.toJson(snap))).build();
        http.sendAsync(req,HttpResponse.BodyHandlers.ofString()).whenComplete((response,error)->server.execute(()->{
            inFlight.remove(name);
            if (error!=null || response.statusCode()!=200 || response.body().length()>16384 || agents.get(name)!=a || ticks-sourceTick>100) return;
            try {
                JsonObject result=JSON.fromJson(response.body(),JsonObject.class);
                if (result.get("tick").getAsLong()!=sourceTick || !name.equals(result.get("agent").getAsString())) return;
                plans.put(name,result.getAsJsonObject("action")); expiries.put(name,ticks+100);
                if(result.has("say")&&result.has("announcement_id")) {
                    String id=result.get("announcement_id").getAsString();
                    if(!id.equals(lastSpeech.get(name))&&ticks-speechTicks.getOrDefault(name,-1000L)>=200) {
                        speak(name,result.get("say").getAsString());lastSpeech.put(name,id);speechTicks.put(name,ticks);
                    }
                }
            } catch(Exception ex) { LOG.warn("Rejected malformed agent proposal for {}",name); }
        }));
    }
    private void chat(ServerChatEvent e) { if(!(e.getPlayer() instanceof AgentPlayer)) server.execute(()->recordChat(e.getPlayer(),e.getRawText())); }
    private void recordChat(ServerPlayer player,String text) {
        recordOrder(player.getGameProfile().getName(),player.serverLevel(),player.blockPosition(),text);
    }
    private void recordOrder(String speaker,ServerLevel level,BlockPos near,String text) {
        text=text.replaceAll("[\\p{Cntrl}§]", " "); if(text.length()>256) text=text.substring(0,256);
        JsonObject row=new JsonObject();row.addProperty("id",UUID.randomUUID().toString());row.addProperty("speaker",speaker);row.addProperty("text",text);row.add("position",SettlementProject.pos(near));row.addProperty("dimension",level.dimension().location().toString());row.addProperty("at",System.currentTimeMillis()/1000);
        chat.add(row);while(chat.size()>24) chat.removeFirst();
        String lower=text.toLowerCase(Locale.ROOT);
        boolean team=lower.matches("(?s).*\\b(agents|all|everyone|team)\\b.*");
        boolean addressed=team;
        for(AgentPlayer a:agents.values()) {
            String name=a.getGameProfile().getName();
            if(team||AgentNames.addressed(lower,name)) {
                addressed=true;
                for(String job:JOBS) if(lower.contains("job "+job)||lower.contains("be a "+job)) { a.job=job;saveConfig();speak(name,"I'll take the "+job+" job."); }
            }
        }
        if(addressed&&(lower.contains("settlement")||lower.contains("build shelter")||lower.contains("build a shelter")||lower.contains("build a hut"))) startProject(level,near);
        if(addressed) { plans.clear();expiries.clear(); }
    }
    private void startProject(ServerLevel level,BlockPos near) {
        if(project!=null&&project.dimension.equals(level.dimension().location().toString())&&project.origin.distSqr(near)<64*64) { speak("Settlement","The shared shelter site is at "+project.origin.toShortString()+". Continuing it with gathered materials.");return; }
        SettlementProject proposed=SettlementProject.survey(level,near);
        if(proposed==null) { speak("Settlement","I couldn't find a safe soil site nearby. Move to flatter open ground, then say: Agents, build a settlement here.");return; }
        project=proposed;saveConfig();plans.clear();
        speak("Settlement","Starting our shared 5 by 5 shelter at "+project.origin.toShortString()+". We need wood; drop spare logs or planks beside us. The doorway stays open.");
    }
    private void speak(String name,String message) {
        message=message.replaceAll("[\\p{Cntrl}§]"," ");if(message.length()>220) message=message.substring(0,220);
        String line="["+name+"] "+message;
        server.getPlayerList().broadcastSystemMessage(Component.literal(line),false);LOG.info("{}",line);
        JsonObject row=new JsonObject();row.addProperty("id",UUID.randomUUID().toString());row.addProperty("speaker",name);row.addProperty("text",message);row.addProperty("agent",true);row.addProperty("at",System.currentTimeMillis()/1000);chat.add(row);while(chat.size()>24) chat.removeFirst();
    }
    private void craftPlanks(AgentPlayer a) {
        for(int i=0;i<36;i++) {
            ItemStack source=a.getInventory().getItem(i);if(source.isEmpty()||!(source.getItem() instanceof BlockItem b)||!b.getBlock().defaultBlockState().is(BlockTags.LOGS)) continue;
            CraftingInput input=CraftingInput.of(1,1,List.of(source.copyWithCount(1)));
            var recipe=a.level().getRecipeManager().getRecipeFor(RecipeType.CRAFTING,input,a.level());if(recipe.isEmpty()) continue;
            ItemStack output=recipe.get().value().assemble(input,a.registryAccess());
            if(output.isEmpty()||!(output.getItem() instanceof BlockItem plank)||!plank.getBlock().defaultBlockState().is(BlockTags.PLANKS)) continue;
            JsonObject action=new JsonObject();action.addProperty("width",1);action.addProperty("height",1);
            JsonArray slots=new JsonArray();slots.add(i);action.add("slots",slots);action.addProperty("output",BuiltInRegistries.ITEM.getKey(output.getItem()).toString());
            ProgressionAdapter.craft(a,action);
            return;
        }
    }
    private void consume(AgentPlayer a) {
        if (a.isUsingItem()) return;
        for(int i=0;i<36;i++) {
            ItemStack s=a.getInventory().getItem(i);
            if (s.has(DataComponents.FOOD)) {
                select(a,i); a.gameMode.useItem(a,a.level(),a.getMainHandItem(),InteractionHand.MAIN_HAND); return;
            }
        }
    }
    private void select(AgentPlayer a,int slot) {
        if (slot<0 || slot>=36) throw new IllegalArgumentException("slot");
        if(slot<9) a.getInventory().selected=slot;
        else { int selected=a.getInventory().selected; ItemStack s=a.getInventory().getItem(selected); a.getInventory().setItem(selected,a.getInventory().getItem(slot)); a.getInventory().setItem(slot,s); }
    }
    private void act(AgentPlayer a,JsonObject action) {
        String kind=action.get("kind").getAsString();
        if(kind.equals("control")) {abortMining(a);a.controls.accept(action);return;}
        a.controls.cancel("control_released");
        lastAction.put(a.getGameProfile().getName(),kind);
        if (!kind.equals("mine")&&!kind.equals("clear_site")) abortMining(a);
        if (!kind.equals("move")) { a.zza=0; a.xxa=0; }
        if(a.isUsingItem()) return;
        switch(kind) {
            case "idle" -> {}
            case "eat" -> consume(a);
            // Older controller proposals can arrive during an adapter upgrade.
            // Drinking is no longer a survival action and consumes no inventory.
            case "drink" -> {}
            case "craft_planks" -> { if(ticks%20==0) craftPlanks(a); }
            case "craft","furnace_insert","furnace_extract" -> {
                if(ticks%20!=0)return;
                // An atomic inventory action consumes its plan, including rejected attempts.
                plans.remove(a.getGameProfile().getName(),action);
                if(kind.equals("craft"))ProgressionAdapter.craft(a,action);
                else ProgressionAdapter.furnace(a,action,kind.equals("furnace_extract"));
            }
            case "use" -> { if(ticks%20==0) { select(a,action.get("slot").getAsInt()); a.gameMode.useItem(a,a.level(),a.getMainHandItem(),InteractionHand.MAIN_HAND); } }
            case "move" -> {
                JsonArray p=action.getAsJsonArray("target");
                if(action.has("path")) {
                    JsonArray path=action.getAsJsonArray("path");
                    while(path.size()>1) {
                        JsonArray step=path.get(0).getAsJsonArray();double dx=step.get(0).getAsDouble()-a.getX(),dz=step.get(2).getAsDouble()-a.getZ();
                        if(dx*dx+dz*dz>0.08) break;path.remove(0);
                    }
                    if(!path.isEmpty()) p=path.get(0).getAsJsonArray();
                }
                Vec3 target=new Vec3(p.get(0).getAsDouble(),p.get(1).getAsDouble(),p.get(2).getAsDouble());
                if(!Double.isFinite(target.x)||!Double.isFinite(target.y)||!Double.isFinite(target.z)||a.position().distanceToSqr(target)>256) return;
                if(!a.level().hasChunkAt(BlockPos.containing(target))||!a.level().getWorldBorder().isWithinBounds(BlockPos.containing(target))) return;
                Vec3 d=target.subtract(a.position());
                if(d.horizontalDistanceSqr()<0.08) { a.zza=0; return; }
                a.setYRot((float)(Math.atan2(-d.x,d.z)*180/Math.PI)); a.setYHeadRot(a.getYRot());
                a.setXRot(45); // Look at the route, avoiding accidental Enderman eye contact.
                a.zza=0.8f;
                if ((a.horizontalCollision || d.y>0.4) && a.onGround()) a.jumpFromGround();
            }
            case "attack" -> {
                Entity target=a.level().getEntity(action.get("entity").getAsInt());
                if(target instanceof Monster && a.distanceToSqr(target)<9 && a.hasLineOfSight(target) && a.getAttackStrengthScale(0)>=1) { a.attack(target); a.swing(InteractionHand.MAIN_HAND); }
            }
            case "mine","clear_site" -> {
                BlockPos p=pos(action); if(!reachable(a,p)) return;
                BlockState s=a.level().getBlockState(p);
                boolean site=kind.equals("clear_site")&&project!=null&&project.dimension.equals(a.level().dimension().location().toString())&&project.contains(p)&&SettlementProject.soil(s);
                if(s.hasBlockEntity() || p.equals(a.blockPosition().below()) || !(site||s.is(BlockTags.LOGS)||s.is(BlockTags.LEAVES)||ProgressionAdapter.resource(s)||s.getBlock() instanceof CropBlock)) return;
                if (s.getBlock() instanceof CropBlock crop && !crop.isMaxAge(s)) return;
                int tool=ProgressionAdapter.toolSlot(a,s);if(tool<0) { abortMining(a);return; }
                select(a,tool);
                if (!p.equals(breaking.get(a.getGameProfile().getName()))) {
                    a.gameMode.handleBlockBreakAction(p,ServerboundPlayerActionPacket.Action.START_DESTROY_BLOCK,Direction.UP,a.level().getMaxBuildHeight(),0);
                    breaking.put(a.getGameProfile().getName(),p);
                    miningStopped.remove(a.getGameProfile().getName());
                } else if(miningStopped.add(a.getGameProfile().getName())) {
                    // Vanilla delays completion until sufficient real break time has elapsed.
                    a.gameMode.handleBlockBreakAction(p,ServerboundPlayerActionPacket.Action.STOP_DESTROY_BLOCK,Direction.UP,a.level().getMaxBuildHeight(),0);
                }
                if (s.isAir()) breaking.remove(a.getGameProfile().getName());
                a.swing(InteractionHand.MAIN_HAND);
            }
            case "place","interact","place_workstation" -> {
                if(ticks%4!=0) return;
                BlockPos p=pos(action); if(!reachable(a,p)) return;
                if(action.has("slot")) select(a,action.get("slot").getAsInt());
                Direction face=action.has("face")?Direction.byName(action.get("face").getAsString()):Direction.UP;
                if(face==null) return;
                if(kind.equals("interact")&&a.getMainHandItem().getItem() instanceof BlockItem)return;
                if(kind.equals("place")&&(project==null||!project.dimension.equals(a.level().dimension().location().toString())||!project.buildCell(p.relative(face))||!(a.getMainHandItem().getItem() instanceof BlockItem block)||!block.getBlock().defaultBlockState().is(BlockTags.PLANKS)&&!(block.getBlock().defaultBlockState().is(Blocks.DIRT)&&p.relative(face).getY()==project.origin.getY()-1))) return;
                if(kind.equals("place_workstation")) {
                    if(!action.has("output")||!BuiltInRegistries.ITEM.getKey(a.getMainHandItem().getItem()).toString().equals(action.get("output").getAsString()))return;
                    if(!(a.getMainHandItem().getItem() instanceof BlockItem block)||!ProgressionAdapter.WORKSTATIONS.contains(BuiltInRegistries.BLOCK.getKey(block.getBlock()).toString()))return;
                    BlockPos target=p.relative(face);BlockState state=a.level().getBlockState(target);
                    if(!state.canBeReplaced()||state.hasBlockEntity()||!a.level().getWorldBorder().isWithinBounds(target)||!a.level().hasChunkAt(target))return;
                    if(a.getBoundingBox().intersects(new AABB(target))||!a.level().getEntities(a,new AABB(target),ent->ent instanceof LivingEntity).isEmpty())return;
                }
                Vec3 hit=Vec3.atCenterOf(p).relative(face,0.5);
                if(face==Direction.UP&&hit.y>a.getEyeY()&&a.onGround()) { a.jumpFromGround();return; }
                BlockHitResult trace=a.level().clip(new ClipContext(a.getEyePosition(),hit.relative(face,-0.001),ClipContext.Block.COLLIDER,ClipContext.Fluid.NONE,a));
                if(!trace.getBlockPos().equals(p)||trace.getDirection()!=face) return;
                a.gameMode.useItemOn(a,a.level(),a.getMainHandItem(),InteractionHand.MAIN_HAND,new BlockHitResult(Vec3.atCenterOf(p).relative(face,0.5),face,p,false));
                if(kind.equals("place_workstation"))plans.remove(a.getGameProfile().getName(),action);
            }
        }
    }
    private void abortMining(AgentPlayer a) {
        miningStopped.remove(a.getGameProfile().getName());
        BlockPos p=breaking.remove(a.getGameProfile().getName());
        if(p!=null) a.gameMode.handleBlockBreakAction(p,ServerboundPlayerActionPacket.Action.ABORT_DESTROY_BLOCK,Direction.UP,a.level().getMaxBuildHeight(),0);
    }
    private boolean reachable(AgentPlayer a,BlockPos p) { return a.level().hasChunkAt(p) && a.getEyePosition().distanceToSqr(Vec3.atCenterOf(p))<=20.25 && a.level().getWorldBorder().isWithinBounds(p) && a.level().clip(new ClipContext(a.getEyePosition(),Vec3.atCenterOf(p),ClipContext.Block.COLLIDER,ClipContext.Fluid.NONE,a)).getBlockPos().equals(p); }
    private BlockPos pos(JsonObject action) { JsonArray p=action.getAsJsonArray("pos"); return new BlockPos(p.get(0).getAsInt(),p.get(1).getAsInt(),p.get(2).getAsInt()); }
    private void saveConfig() {
        JsonArray rows=new JsonArray(); for(AgentPlayer a:agents.values()) { JsonObject row=new JsonObject(); row.addProperty("name",a.getGameProfile().getName()); row.addProperty("job",a.job); rows.add(row); }
        config.add("agents",rows);
        if(project!=null) config.add("settlement",project.save());
        try { Files.writeString(CONFIG,new GsonBuilder().setPrettyPrinting().create().toJson(config)); } catch(Exception ex) { LOG.error("Cannot save agent roster",ex); }
    }
    private void commands(RegisterCommandsEvent e) {
        var talk=Commands.literal("agent");
        talk.executes(c->{ c.getSource().sendSuccess(()->Component.literal("Chat: Forge, gather wood | Agents, stop | /agent all stop | /agent status. Drop supplies beside agents to give them items."),false); return 1; });
        talk.then(Commands.literal("status").executes(c->{ for(AgentPlayer a:agents.values()) c.getSource().sendSuccess(()->Component.literal(a.getGameProfile().getName()+" ("+a.job+"): "+lastAction.getOrDefault(a.getGameProfile().getName(),"starting")+" at "+a.blockPosition().toShortString()),false);return 1;}));
        talk.then(Commands.argument("name",com.mojang.brigadier.arguments.StringArgumentType.word()).then(Commands.argument("message",com.mojang.brigadier.arguments.StringArgumentType.greedyString()).executes(c->{ ServerPlayer p=c.getSource().getPlayerOrException(); if(p instanceof AgentPlayer) return 0; recordChat(p,com.mojang.brigadier.arguments.StringArgumentType.getString(c,"name")+", "+com.mojang.brigadier.arguments.StringArgumentType.getString(c,"message"));return 1;})));
        e.getDispatcher().register(talk);
        var root=Commands.literal("synagent").requires(s->s.hasPermission(2));
        root.then(Commands.literal("order").then(Commands.argument("message",com.mojang.brigadier.arguments.StringArgumentType.greedyString()).executes(c->{ recordOrder("Server",c.getSource().getLevel(),BlockPos.containing(c.getSource().getPosition()),com.mojang.brigadier.arguments.StringArgumentType.getString(c,"message"));return 1;})));
        root.then(Commands.literal("settle").executes(c->{ ServerPlayer p=server.getPlayerList().getPlayers().stream().filter(x->!(x instanceof AgentPlayer)).findFirst().orElse(null); BlockPos near=p==null?server.overworld().getSharedSpawnPos():p.blockPosition(); startProject(p==null?server.overworld():p.serverLevel(),near);return 1;}));
        root.then(Commands.literal("inspect").executes(c->{ JsonArray rows=new JsonArray();agents.values().forEach(a->rows.add(observation(a)));try { Files.writeString(Path.of("config/syn-agents-observations.json"),JSON.toJson(rows)); } catch(Exception ex) { LOG.warn("Cannot write agent observations",ex);return 0; }return 1;}));
        root.then(Commands.literal("list").executes(c->{ c.getSource().sendSuccess(()->Component.literal("Survival agents: "+agents.keySet()),false); return agents.size(); }));
        root.then(Commands.literal("spawn").then(Commands.argument("name",com.mojang.brigadier.arguments.StringArgumentType.word()).then(Commands.argument("job",com.mojang.brigadier.arguments.StringArgumentType.word()).executes(c->{ spawn(com.mojang.brigadier.arguments.StringArgumentType.getString(c,"name"),com.mojang.brigadier.arguments.StringArgumentType.getString(c,"job")); saveConfig(); return 1; }))));
        root.then(Commands.literal("remove").then(Commands.argument("name",com.mojang.brigadier.arguments.StringArgumentType.word()).executes(c->{ String n=com.mojang.brigadier.arguments.StringArgumentType.getString(c,"name"); AgentPlayer a=agents.remove(n); if(a!=null) { server.getPlayerList().remove(a); plans.remove(n); saveConfig(); return 1; } return 0; })));
        e.getDispatcher().register(root);
    }
}
