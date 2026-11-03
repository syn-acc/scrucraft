package gl.syn.minecraft;

import com.google.gson.*;
import com.mojang.serialization.JsonOps;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.Direction;
import net.minecraft.core.component.DataComponentMap;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.MenuProvider;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.*;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.ChestType;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;

/** Server-thread inventory transactions; no synthetic items, recipe policy or hidden goals. */
final class BodyInventory {
    private static final Map<String,String> PROCESSING_STATIONS=Map.ofEntries(
        Map.entry("minecraft:smelting","minecraft:furnace"),Map.entry("minecraft:blasting","minecraft:blast_furnace"),
        Map.entry("minecraft:smoking","minecraft:smoker"),Map.entry("minecraft:campfire_cooking","minecraft:campfire"),
        Map.entry("create:pressing","create:mechanical_press + create:depot"),Map.entry("create:mixing","create:mechanical_mixer + create:basin"),
        Map.entry("create:compacting","create:mechanical_press + create:basin"),Map.entry("create:milling","create:millstone"),
        Map.entry("create:crushing","create:crushing_wheel"),Map.entry("create:cutting","create:mechanical_saw"),
        Map.entry("create:splashing","create:encased_fan + water"),Map.entry("create:haunting","create:encased_fan + soul_fire"),
        Map.entry("create:smoking","create:encased_fan + fire"),Map.entry("create:blasting","create:encased_fan + lava"),
        Map.entry("create:filling","create:spout"),Map.entry("create:emptying","create:item_drain"),
        Map.entry("create:deploying","create:deployer"),Map.entry("create:mechanical_crafting","create:mechanical_crafter"),
        Map.entry("create:sequenced_assembly","see native_recipe.sequence"),
        Map.entry("farmersdelight:cooking","farmersdelight:cooking_pot"),Map.entry("farmersdelight:cutting","farmersdelight:cutting_board"));
    private final AgentPlayer body;
    private AbstractContainerMenu menu;
    private MachineItemPort machine;
    private Entity menuEntity;
    private boolean itemMenu;
    private BlockPos position,otherHalf;
    private BlockEntity entity,otherEntity;
    private BlockState openedState;
    private JsonObject lastArea;
    private String session,closedSession,closeReason="never_opened";
    private long revision;
    private List<ItemStack> snapshot=List.of();
    private ItemStack queriedStack;
    private byte[] queriedComponents;
    private String queriedRevision;
    private RecipeHolder<?> queriedRecipe;
    private byte[] queriedRecipeBytes;
    private String queriedRecipeRevision;
    BodyInventory(AgentPlayer body){this.body=body;}
    static boolean reviewedPortableItem(ItemStack item){return ReviewedModMenus.portableItem(item);}

    JsonObject execute(JsonObject action,JsonObject area) {
        return switch(action.get("op").getAsString()) {
            case "open_container" -> open(at(action.getAsJsonArray("target")),area,action.has("face")?action.get("face").getAsString():null);
            case "move_item" -> move(action,area);
            case "close_container" -> {requireHandle(action);close("explicit_close");yield observe();}
            case "craft" -> craft(action,area);
            case "query_recipes" -> queryRecipes(action);
            case "query_inventory" -> queryInventory(action,area);
            case "query_recipe" -> queryRecipe(action);
            default -> throw failure("unsupported_operation");
        };
    }
    private static IllegalArgumentException failure(String why){return new NativeActionException(why);}
    private static BlockPos at(JsonArray value) {
        if(value==null||value.size()!=3)throw failure("invalid_target");
        int[] c=new int[3];for(int i=0;i<3;i++) {
            double n=value.get(i).getAsDouble();if(!Double.isFinite(n)||n!=Math.rint(n)||Math.abs(n)>30000000)throw failure("invalid_target");c[i]=(int)n;
        }return new BlockPos(c[0],c[1],c[2]);
    }
    private static int integer(JsonObject value,String key,int min,int max) {
        double n=value.get(key).getAsDouble();if(!Double.isFinite(n)||n!=Math.rint(n)||n<min||n>max)throw failure("invalid_"+key);return (int)n;
    }
    private void access(BlockPos pos,JsonObject area) {
        BodyAccess.require(body,pos,area);
        if(!BodyAccess.reachable(body,pos))throw failure("out_of_reach_or_occluded");
    }
    void prepareOpen(BlockPos pos,JsonObject area) {
        access(pos,area);BlockState state=body.level().getBlockState(pos);
        if(state.getBlock() instanceof ChestBlock&&state.getValue(ChestBlock.TYPE)!=ChestType.SINGLE)
            BodyAccess.require(body,pos.relative(ChestBlock.getConnectedDirection(state)),area);
    }
    /** Adopt the menu created by a native use_on, without invoking the block a second time. */
    JsonObject adoptOpened(BlockPos pos,JsonObject area) {
        prepareOpen(pos,area);
        AbstractContainerMenu opened=body.containerMenu;
        if(opened==body.inventoryMenu)throw failure("container_not_opened");
        if(!(opened instanceof ChestMenu||opened instanceof ShulkerBoxMenu||opened instanceof AbstractFurnaceMenu
            ||opened instanceof HopperMenu||opened instanceof DispenserMenu||opened instanceof BrewingStandMenu||ReviewedModMenus.blockMenu(opened))) {
            body.closeContainer();close("unsupported_container");throw failure("unsupported_container");
        }
        try{ReviewedModMenus.validateBlock(opened,pos,area);}
        catch(IllegalArgumentException ex){body.closeContainer();close(ex.getMessage());throw ex;}
        BlockState state=body.level().getBlockState(pos);
        BlockPos other=state.getBlock() instanceof ChestBlock&&state.getValue(ChestBlock.TYPE)!=ChestType.SINGLE
            ?pos.relative(ChestBlock.getConnectedDirection(state)):null;
        // The new native menu already replaced the previous one. Do not close it here.
        machine=null;menuEntity=null;itemMenu=false;menu=opened;position=pos;openedState=state;entity=body.level().getBlockEntity(pos);
        otherHalf=other;otherEntity=other==null?null:body.level().getBlockEntity(other);
        lastArea=area==null?null:area.deepCopy();session=UUID.randomUUID().toString();revision=0;snapshot=List.of();
        queriedStack=null;queriedComponents=null;queriedRevision=null;refresh();return observe();
    }
    private void entityAccess(Entity target,JsonObject area) {
        if(target==null||!target.isAlive()||target.isRemoved()||target.level()!=body.level()
            ||body.serverLevel().getEntity(target.getId())!=target)throw failure("container_changed");
        var box=target.getBoundingBox();
        BodyAccess.require(body,BlockPos.containing(box.minX,box.minY,box.minZ),area);
        BodyAccess.require(body,BlockPos.containing(Math.nextDown(box.maxX),Math.nextDown(box.maxY),Math.nextDown(box.maxZ)),area);
        if(body.getEyePosition().distanceToSqr(box.getCenter())>9||!body.hasLineOfSight(target))throw failure("out_of_reach_or_occluded");
    }
    JsonObject adoptEntityOpened(Entity target,JsonObject area) {
        AbstractContainerMenu opened=body.containerMenu;
        if(opened==body.inventoryMenu)throw failure("container_not_opened");
        try{entityAccess(target,area);ReviewedModMenus.validateEntity(opened,target,area);}
        catch(IllegalArgumentException ex){body.closeContainer();close(ex.getMessage());throw ex;}
        return adoptUnanchored(opened,target,false,area);
    }
    JsonObject adoptItemOpened(JsonObject area) {
        AbstractContainerMenu opened=body.containerMenu;
        if(opened==body.inventoryMenu)throw failure("container_not_opened");
        try{BodyAccess.require(body,body.blockPosition(),area);ReviewedModMenus.validateItem(opened,body,area);}
        catch(IllegalArgumentException ex){body.closeContainer();close(ex.getMessage());throw ex;}
        return adoptUnanchored(opened,null,true,area);
    }
    private JsonObject adoptUnanchored(AbstractContainerMenu opened,Entity target,boolean portable,JsonObject area) {
        machine=null;menu=opened;menuEntity=target;itemMenu=portable;position=null;entity=null;otherHalf=null;otherEntity=null;openedState=null;
        lastArea=area==null?null:area.deepCopy();session=UUID.randomUUID().toString();revision=0;snapshot=List.of();
        queriedStack=null;queriedComponents=null;queriedRevision=null;refresh();return observe();
    }
    private JsonObject open(BlockPos pos,JsonObject area,String requestedFace) {
        access(pos,area);
        BlockState state=body.level().getBlockState(pos);
        Direction face=requestedFace==null?null:Direction.byName(requestedFace);
        if(requestedFace!=null&&face==null)throw failure("invalid_face");
        if(MachineItemPort.supports(state)) {
            close("replaced");machine=new MachineItemPort(body,pos,area,face);
            lastArea=area==null?null:area.deepCopy();session=machine.session;revision=machine.revision;
            return observe();
        }
        if(face!=null)throw failure("container_face_not_supported");
        // Only menus with native storage/furnace/brewing slots; no machine/recipe-output shortcuts.
        Block block=state.getBlock();
        if(!(block instanceof ChestBlock||block instanceof BarrelBlock||block instanceof ShulkerBoxBlock
            ||block instanceof AbstractFurnaceBlock||block instanceof HopperBlock||block instanceof DispenserBlock
            ||block instanceof BrewingStandBlock||ReviewedModMenus.blockCandidate(block)))throw failure("unsupported_container");
        BlockPos other=null;
        if(block instanceof ChestBlock&&state.getValue(ChestBlock.TYPE)!=ChestType.SINGLE) {
            other=pos.relative(ChestBlock.getConnectedDirection(state));BodyAccess.require(body,other,area);
        }
        MenuProvider provider=state.getMenuProvider(body.level(),pos);
        if(provider==null&&!ReviewedModMenus.blockCandidate(block))throw failure("container_blocked");
        boolean pot=block.getClass().getName().equals("vectorwing.farmersdelight.common.block.CookingPotBlock");
        if(pot&&(!body.getMainHandItem().isEmpty()||body.isShiftKeyDown()))throw failure("container_requires_empty_hand_not_sneaking");
        close("replaced");
        // Follow native opening rules (blocked lids, locks, statistics and piglin reactions).
        BlockHitResult click=new BlockHitResult(Vec3.atCenterOf(pos),Direction.UP,pos,false);
        if(pot)body.gameMode.useItemOn(body,body.level(),body.getMainHandItem(),InteractionHand.MAIN_HAND,click);
        else state.useWithoutItem(body.level(),body,click);
        if(body.containerMenu==body.inventoryMenu)throw failure("container_locked_or_blocked");
        AbstractContainerMenu opened=body.containerMenu;
        if(!(opened instanceof ChestMenu||opened instanceof ShulkerBoxMenu||opened instanceof AbstractFurnaceMenu
            ||opened instanceof HopperMenu||opened instanceof DispenserMenu||opened instanceof BrewingStandMenu||ReviewedModMenus.blockMenu(opened))) {
            body.closeContainer();throw failure("unsupported_container");
        }
        try{ReviewedModMenus.validateBlock(opened,pos,area);}
        catch(IllegalArgumentException ex){body.closeContainer();throw ex;}
        menuEntity=null;itemMenu=false;menu=opened;position=pos;openedState=state;entity=body.level().getBlockEntity(pos);
        otherHalf=other;otherEntity=other==null?null:body.level().getBlockEntity(other);
        lastArea=area==null?null:area.deepCopy();session=UUID.randomUUID().toString();revision=0;snapshot=List.of();refresh();
        return observe();
    }
    private void validate(JsonObject area) {
        if(machine!=null) {
            try{machine.validate(area);lastArea=area==null?null:area.deepCopy();session=machine.session;revision=machine.revision;return;}
            catch(IllegalArgumentException ex){close(ex.getMessage());throw ex;}
        }
        if(menu==null)throw failure("container_closed");
        try {
            if(!body.isAlive()||body.isRemoved())throw failure("body_unavailable");
            if(menuEntity!=null||itemMenu) {
                if(body.containerMenu!=menu||!menu.stillValid(body))throw failure("container_changed");
                if(menuEntity!=null){entityAccess(menuEntity,area);ReviewedModMenus.validateEntity(menu,menuEntity,area);}
                else{BodyAccess.require(body,body.blockPosition(),area);ReviewedModMenus.validateItem(menu,body,area);}
                lastArea=area==null?null:area.deepCopy();refresh();return;
            }
            access(position,area);
            ReviewedModMenus.validateBlock(menu,position,area);
            if(otherHalf!=null) {
                BodyAccess.require(body,otherHalf,area);
                if(body.level().getBlockEntity(otherHalf)!=otherEntity)throw failure("container_changed");
            }
            if(body.containerMenu!=menu||!menu.stillValid(body)||body.level().getBlockEntity(position)!=entity
                ||body.level().getBlockState(position).getBlock()!=openedState.getBlock())throw failure("container_changed");
            if(openedState.getBlock() instanceof ChestBlock && !body.level().getBlockState(position).equals(openedState))throw failure("container_changed");
            lastArea=area==null?null:area.deepCopy();refresh();
        } catch(IllegalArgumentException ex) {close(ex.getMessage());throw ex;}
    }
    private void requireSession(JsonObject action,JsonObject area) {
        validate(area);
        requireHandle(action);
    }
    private void requireHandle(JsonObject action) {
        if(machine!=null){machine.requireHandle(action);revision=machine.revision;return;}
        if(menu==null)throw failure("container_closed");
        refresh();
        if(!action.has("session_id")||!session.equals(action.get("session_id").getAsString()))throw failure("stale_container_session");
        if(!action.has("revision")||action.get("revision").getAsDouble()!=revision)throw failure("stale_container_revision");
    }
    private void refresh() {
        boolean changed=snapshot.size()!=menu.slots.size();
        if(!changed)for(int i=0;i<snapshot.size();i++)if(!ItemStack.matches(snapshot.get(i),menu.slots.get(i).getItem())){changed=true;break;}
        if(changed){revision++;snapshot=new ArrayList<>();for(Slot slot:menu.slots)snapshot.add(slot.getItem().copy());}
    }
    private Slot resolve(JsonObject ref) {
        String inventory=ref.get("inventory").getAsString();int index=integer(ref,"slot",0,255);
        if(inventory.equals("player")) {
            if(index>=36)throw failure("unsupported_player_slot");
            for(Slot slot:menu.slots)if(slot.container==body.getInventory()&&slot.getContainerSlot()==index)return slot;
        } else if(inventory.equals("container")) {
            int n=0;for(Slot slot:menu.slots)if(slot.container!=body.getInventory()){if(n++==index)return slot;}
        }throw failure("invalid_slot");
    }
    private JsonObject move(JsonObject action,JsonObject area) {
        if(machine!=null){requireSession(action,area);return machine.move(action,area);}
        requireSession(action,area);
        int count=integer(action,"count",1,64);Slot source=resolve(action.getAsJsonObject("from")),dest=resolve(action.getAsJsonObject("to"));
        if(source==dest)throw failure("same_slot");
        ItemStack before=source.getItem(),target=dest.getItem();
        if(!ReviewedModMenus.transferable(menu,source,source.container==body.getInventory())
            ||!ReviewedModMenus.transferable(menu,dest,dest.container==body.getInventory()))throw failure("unsupported_menu_slot_operation");
        if(before.isEmpty()||before.getCount()<count)throw failure("insufficient_items");
        if(!source.isActive()||!dest.isActive()||!source.mayPickup(body)||!dest.mayPlace(before))throw failure("slot_rule_rejected");
        if(!target.isEmpty()&&!ItemStack.isSameItemSameComponents(before,target))throw failure("incompatible_stack");
        if(dest.getMaxStackSize(before)-target.getCount()<count)throw failure("insufficient_slot_capacity");
        // All checks precede mutation on the game thread; native removal fires furnace XP/slot hooks.
        ItemStack moved=source.safeTake(count,before.getCount(),body);
        if(moved.getCount()!=count) {
            // Unexpected modded slot behaviour must not strand the removed stack in a local variable.
            if(!moved.isEmpty()&&!body.getInventory().add(moved))body.drop(moved,false);
            throw new IllegalStateException("native_slot_transfer_mismatch");
        }
        ItemStack remainder=dest.safeInsert(moved);
        if(!remainder.isEmpty()) { // Defensive recovery for a mod hook that changed a validated slot.
            if(!body.getInventory().add(remainder))body.drop(remainder,false);
            throw new IllegalStateException("slot_changed_during_transfer");
        }
        source.setChanged();dest.setChanged();body.getInventory().setChanged();menu.broadcastChanges();refresh();
        JsonObject answer=observe();answer.addProperty("moved",count);return answer;
    }
    void close(){close("control_closed");}
    void validateArea(JsonObject area) {
        if(menu!=null||machine!=null)try{validate(area);}catch(IllegalArgumentException ignored){}
    }
    void close(String reason) {
        if(machine!=null){closedSession=machine.session;closeReason=reason;machine=null;}
        if(menu!=null) {
            closedSession=session;closeReason=reason;
            // Vanilla removed() returns any carried stack or drops it safely if the player cannot receive it.
            if(body.containerMenu==menu)body.closeContainer();
        }
        menu=null;menuEntity=null;itemMenu=false;session=null;snapshot=List.of();
        queriedStack=null;queriedComponents=null;queriedRevision=null;
        queriedRecipe=null;queriedRecipeBytes=null;queriedRecipeRevision=null;
    }
    JsonObject observe() {
        if(menu!=null||machine!=null)try{validate(lastArea);}catch(IllegalArgumentException ignored){}
        if(machine!=null)return machine.observe();
        JsonObject value=new JsonObject();value.addProperty("open",menu!=null);
        if(menu==null) {
            if(closedSession!=null)value.addProperty("closed_session_id",closedSession);
            value.addProperty("reason",closeReason);return value;
        }
        value.addProperty("session_id",session);value.addProperty("revision",revision);
        value.addProperty("dimension",body.level().dimension().location().toString());
        if(menuEntity!=null) {
            value.addProperty("kind","entity_menu");value.addProperty("entity_id",menuEntity.getId());value.addProperty("entity_uuid",menuEntity.getUUID().toString());
            value.addProperty("entity_type",BuiltInRegistries.ENTITY_TYPE.getKey(menuEntity.getType()).toString());
            JsonArray at=new JsonArray();at.add(menuEntity.getX());at.add(menuEntity.getY());at.add(menuEntity.getZ());value.add("position",at);
        } else if(itemMenu){value.addProperty("kind","item_menu");value.addProperty("item_container","sophisticatedbackpacks:backpack");}
        else{value.addProperty("kind","block_menu");value.add("position",SettlementProject.pos(position));value.addProperty("block",BuiltInRegistries.BLOCK.getKey(openedState.getBlock()).toString());}
        JsonArray slots=new JsonArray();int containerSlot=0;
        for(Slot slot:menu.slots) {
            boolean player=slot.container==body.getInventory();JsonObject row=stack(slot.getItem());
            row.addProperty("inventory",player?"player":"container");row.addProperty("slot",player?slot.getContainerSlot():containerSlot++);
            row.addProperty("capacity",slot.getItem().isEmpty()?slot.getMaxStackSize():slot.getMaxStackSize(slot.getItem()));
            boolean transferable=ReviewedModMenus.transferable(menu,slot,player);
            row.addProperty("can_take",transferable&&slot.mayPickup(body));row.addProperty("transfer_supported",transferable);row.addProperty("role",role(slot,player));slots.add(row);
        }
        value.add("slots",slots);value.add("cursor",stack(menu.getCarried()));return value;
    }
    private String role(Slot slot,boolean player) {
        if(player)return slot.getContainerSlot()<9?"hotbar":"main";
        int n=slot.getContainerSlot();
        if(menu instanceof AbstractFurnaceMenu)return n==0?"input":n==1?"fuel":"output";
        if(menu instanceof BrewingStandMenu)return n<3?"bottle":n==3?"ingredient":"fuel";
        return ReviewedModMenus.role(menu,slot);
    }
    private JsonObject stack(ItemStack item) {return describeStack(item,body.registryAccess());}
    private static JsonObject basicStack(ItemStack item) {
        JsonObject row=ProgressionAdapter.stack(item);row.addProperty("empty",item.isEmpty());
        row.addProperty("max_stack_size",item.getMaxStackSize());row.addProperty("damage",item.getDamageValue());row.addProperty("max_damage",item.getMaxDamage());
        return row;
    }
    static JsonObject describeStack(ItemStack item,HolderLookup.Provider registry) {
        JsonObject row=basicStack(item);
        var encoded=DataComponentMap.CODEC.encodeStart(registry.createSerializationContext(JsonOps.INSTANCE),item.getComponents());
        encoded.result().ifPresent(value->{
            byte[] serialized=value.toString().getBytes(StandardCharsets.UTF_8);
            row.addProperty("component_bytes",serialized.length);
            if(serialized.length<=2048)row.add("components",value);
            else {
                row.addProperty("components_truncated",true);
                try{row.addProperty("components_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(serialized)));}
                catch(NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}
            }
        });
        if(encoded.result().isEmpty())row.addProperty("components_unavailable",true);
        return row;
    }

    private JsonObject queryInventory(JsonObject action,JsonObject area) {
        String inventory=action.has("inventory")?action.get("inventory").getAsString():"player";
        int index=integer(action,"slot",-1,255);
        ItemStack item;
        if(inventory.equals("player")) {
            if(index>40)throw failure("invalid_slot");
            item=index==-1?body.containerMenu.getCarried():body.getInventory().getItem(index);
        } else if(inventory.equals("container")) {
            requireSession(action,area);
            if(machine!=null)item=machine.stack(index);
            else {JsonObject ref=new JsonObject();ref.addProperty("inventory",inventory);ref.addProperty("slot",index);item=resolve(ref).getItem();}
        } else throw failure("invalid_inventory");
        int offset=action.has("offset")?integer(action,"offset",0,16777216):0;
        int limit=action.has("limit")?integer(action,"limit",1,16384):16384;
        if(queriedStack==null||!ItemStack.matches(queriedStack,item)) {
            var encoded=DataComponentMap.CODEC.encodeStart(body.registryAccess().createSerializationContext(JsonOps.INSTANCE),item.getComponents());
            JsonElement components=encoded.result().orElseThrow(()->failure("components_unavailable"));
            byte[] serialized=components.toString().getBytes(StandardCharsets.UTF_8);
            if(serialized.length>16777216)throw failure("component_metadata_too_large");
            try {
                MessageDigest digest=MessageDigest.getInstance("SHA-256");
                digest.update((BuiltInRegistries.ITEM.getKey(item.getItem())+"\0"+item.getCount()+"\0").getBytes(StandardCharsets.UTF_8));
                queriedRevision=HexFormat.of().formatHex(digest.digest(serialized));
            } catch(NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}
            queriedStack=item.copy();queriedComponents=serialized;
        }
        if(offset>0&&!action.has("stack_revision"))throw failure("stack_revision_required");
        if(action.has("stack_revision")&&!queriedRevision.equals(action.get("stack_revision").getAsString()))throw failure("stale_inventory_revision");
        if(offset>queriedComponents.length)throw failure("invalid_offset");
        int end=Math.min(queriedComponents.length,offset+limit);
        JsonObject page=new JsonObject();page.addProperty("inventory",inventory);page.addProperty("slot",index);
        JsonObject description=basicStack(item);description.addProperty("component_bytes",queriedComponents.length);
        page.add("stack",description);page.addProperty("stack_revision",queriedRevision);
        page.addProperty("components_encoding","utf-8/base64");
        page.addProperty("components_chunk",Base64.getEncoder().encodeToString(Arrays.copyOfRange(queriedComponents,offset,end)));
        page.addProperty("offset",offset);page.addProperty("total_bytes",queriedComponents.length);
        if(end<queriedComponents.length)page.addProperty("next_offset",end);
        if(inventory.equals("container")){page.addProperty("session_id",session);page.addProperty("revision",revision);}
        return page;
    }

    private static boolean supported(Recipe<?> recipe) {
        return (recipe.getClass()==ShapedRecipe.class||recipe.getClass()==ShapelessRecipe.class)&&recipe.canCraftInDimensions(3,3)&&!recipe.isSpecial();
    }
    private static String type(Recipe<?> recipe){return BuiltInRegistries.RECIPE_TYPE.getKey(recipe.getType()).toString();}
    private static boolean discoverable(Recipe<?> recipe){return supported(recipe)||PROCESSING_STATIONS.containsKey(type(recipe));}
    private JsonObject recipeStack(ItemStack item,boolean full) {
        if(!full)return stack(item);
        JsonObject row=basicStack(item);
        var encoded=DataComponentMap.CODEC.encodeStart(body.registryAccess().createSerializationContext(JsonOps.INSTANCE),item.getComponents());
        row.add("components",encoded.result().orElseThrow(()->failure("components_unavailable")));return row;
    }
    private JsonObject recipeDescription(RecipeHolder<?> holder,boolean full) {
        if(!supported(holder.value()))return processingDescription(holder,full);
        CraftingRecipe recipe=(CraftingRecipe)holder.value();
        JsonObject row=new JsonObject();row.addProperty("recipe_id",holder.id().toString());row.addProperty("supported",true);
        row.addProperty("craft_supported",true);row.addProperty("execution","craft");row.addProperty("recipe_type",type(recipe));
        row.addProperty("workstation",recipe.canCraftInDimensions(2,2)?"inventory_2x2":"minecraft:crafting_table");
        row.addProperty("width",recipe instanceof ShapedRecipe shape?shape.getWidth():recipe.canCraftInDimensions(2,2)?2:3);
        row.addProperty("height",recipe instanceof ShapedRecipe shape?shape.getHeight():recipe.canCraftInDimensions(2,2)?2:3);
        row.addProperty("shapeless",recipe instanceof ShapelessRecipe);row.add("output",recipeStack(recipe.getResultItem(body.registryAccess()),full));
        JsonArray ingredients=new JsonArray();
        for(Ingredient ingredient:recipe.getIngredients()) {
            JsonArray alternatives=new JsonArray();for(ItemStack option:ingredient.getItems()) {
                JsonObject item=recipeStack(option,full);
                if(option.hasCraftingRemainingItem())item.add("remainder",recipeStack(option.getCraftingRemainingItem(),full));
                alternatives.add(item);
            }ingredients.add(alternatives);
        }
        row.add("ingredients",ingredients);row.addProperty("count_semantics","recipe_executions");return row;
    }
    private JsonObject processingDescription(RecipeHolder<?> holder,boolean full) {
        Recipe<?> recipe=holder.value();String kind=type(recipe);
        JsonObject row=new JsonObject();row.addProperty("recipe_id",holder.id().toString());row.addProperty("recipe_type",kind);
        row.addProperty("supported",false);row.addProperty("metadata_supported",true);row.addProperty("craft_supported",false);
        row.addProperty("execution","native_world_ticks");row.addProperty("workstation",PROCESSING_STATIONS.get(kind));
        // Preserve serializer-defined fluid amounts, probabilistic outputs, heat, timing and sequences.
        // assemble()/rollResults() must NEVER be called to synthesize a machine's output.
        var encoded=Recipe.CODEC.encodeStart(body.registryAccess().createSerializationContext(JsonOps.INSTANCE),recipe);
        row.add("native_recipe",encoded.result().orElseThrow(()->failure("recipe_metadata_unavailable")));
        JsonArray ingredients=new JsonArray();
        for(Ingredient ingredient:recipe.getIngredients()) {
            JsonArray alternatives=new JsonArray();for(ItemStack item:ingredient.getItems())alternatives.add(recipeStack(item,full));
            ingredients.add(alternatives);
        }
        row.add("ingredients",ingredients);row.addProperty("processing_status",
            Set.of("create:pressing","create:mixing","create:compacting","create:milling").contains(kind)?"candidate_machine_ports_unverified":"planned_or_native_container_processing_unverified");
        return row;
    }
    private JsonObject queryRecipe(JsonObject action) {
        ResourceLocation id=ResourceLocation.tryParse(action.get("recipe_id").getAsString());if(id==null)throw failure("invalid_recipe_id");
        RecipeHolder<?> untyped=body.level().getRecipeManager().byKey(id).orElseThrow(()->failure("unknown_recipe"));
        if(!discoverable(untyped.value()))throw failure("unsupported_recipe_type");
        RecipeHolder<?> holder=untyped;
        int offset=action.has("offset")?integer(action,"offset",0,16777216):0;
        int limit=action.has("limit")?integer(action,"limit",1,16384):16384;
        if(queriedRecipe!=holder) {
            byte[] bytes=recipeDescription(holder,true).toString().getBytes(StandardCharsets.UTF_8);
            if(bytes.length>16777216)throw failure("recipe_metadata_too_large");
            try{queriedRecipeRevision=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));}
            catch(NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}
            queriedRecipe=holder;queriedRecipeBytes=bytes;
        }
        if(offset>0&&!action.has("recipe_revision"))throw failure("recipe_revision_required");
        if(action.has("recipe_revision")&&!queriedRecipeRevision.equals(action.get("recipe_revision").getAsString()))throw failure("stale_recipe_revision");
        if(offset>queriedRecipeBytes.length)throw failure("invalid_offset");
        int end=Math.min(queriedRecipeBytes.length,offset+limit);
        JsonObject page=new JsonObject();page.addProperty("recipe_id",id.toString());page.addProperty("encoding","utf-8/base64");
        page.addProperty("recipe_revision",queriedRecipeRevision);
        page.addProperty("recipe_chunk",Base64.getEncoder().encodeToString(Arrays.copyOfRange(queriedRecipeBytes,offset,end)));
        page.addProperty("offset",offset);page.addProperty("total_bytes",queriedRecipeBytes.length);
        if(end<queriedRecipeBytes.length)page.addProperty("next_offset",end);return page;
    }
    JsonArray recipes() {return queryRecipes(new JsonObject()).getAsJsonArray("recipes");}
    private JsonObject queryRecipes(JsonObject query) {
        int offset=query.has("offset")?integer(query,"offset",0,100000):0;
        int limit=query.has("limit")?integer(query,"limit",1,64):32;
        List<RecipeHolder<?>> available=new ArrayList<>();
        for(RecipeHolder<?> holder:body.level().getRecipeManager().getRecipes())if(discoverable(holder.value()))available.add(holder);
        available.sort(Comparator.comparing(holder->holder.id().toString()));
        JsonArray rows=new JsonArray();int metadataBytes=0;
        for(int index=offset;index<Math.min(available.size(),offset+limit);index++) {
            JsonObject row=recipeDescription(available.get(index),false);
            int bytes=row.toString().getBytes(StandardCharsets.UTF_8).length;
            if(bytes>98304) {
                row.remove("ingredients");row.remove("native_recipe");row.addProperty("ingredients_truncated",true);row.addProperty("metadata_truncated",true);
                row.addProperty("ingredient_metadata_bytes",bytes);bytes=row.toString().getBytes(StandardCharsets.UTF_8).length;
            }
            if(!rows.isEmpty()&&metadataBytes+bytes>98304)break;
            rows.add(row);metadataBytes+=bytes;
        }
        JsonObject page=new JsonObject();page.add("recipes",rows);page.addProperty("offset",offset);page.addProperty("total",available.size());
        if(offset+rows.size()<available.size())page.addProperty("next_offset",offset+rows.size());
        JsonArray supportedTypes=new JsonArray();supportedTypes.add("minecraft:crafting_shaped");supportedTypes.add("minecraft:crafting_shapeless");page.add("supported_types",supportedTypes);
        JsonArray processingTypes=new JsonArray();PROCESSING_STATIONS.keySet().stream().sorted().forEach(processingTypes::add);page.add("processing_metadata_types",processingTypes);
        page.addProperty("count_semantics","recipe_executions");page.addProperty("metadata_byte_limit",98304);return page;
    }
    private BlockPos table(JsonObject action,JsonObject area) {
        if(action.has("target")) {
            BlockPos pos=at(action.getAsJsonArray("target"));access(pos,area);
            if(!body.level().getBlockState(pos).is(Blocks.CRAFTING_TABLE))throw failure("crafting_table_required");return pos;
        }
        for(BlockPos pos:BlockPos.betweenClosed(body.blockPosition().offset(-4,-3,-4),body.blockPosition().offset(4,3,4))) {
            if(!body.level().hasChunkAt(pos)||!body.level().getBlockState(pos).is(Blocks.CRAFTING_TABLE))continue;
            try{access(pos,area);return pos.immutable();}catch(IllegalArgumentException ignored){}
        }
        throw failure("reachable_work_area_crafting_table_required");
    }
    private static boolean insert(List<ItemStack> inventory,ItemStack value) {
        ItemStack remaining=value.copy();
        for(int pass=0;pass<2;pass++)for(int i=0;i<inventory.size()&&!remaining.isEmpty();i++) {
            ItemStack current=inventory.get(i);
            if(pass==0&&(current.isEmpty()||!ItemStack.isSameItemSameComponents(current,remaining)))continue;
            if(pass==1&&!current.isEmpty())continue;
            int count=Math.min(remaining.getCount(),Math.min(64,remaining.getMaxStackSize())-current.getCount());
            if(count<=0)continue;
            if(current.isEmpty())inventory.set(i,remaining.copyWithCount(count));else current.grow(count);remaining.shrink(count);
        }return remaining.isEmpty();
    }
    private record Craft(CraftingInput input,ItemStack output){}
    private JsonObject craft(JsonObject action,JsonObject area) {
        int count=integer(action,"count",1,64);
        ResourceLocation id=ResourceLocation.tryParse(action.get("recipe_id").getAsString());if(id==null)throw failure("invalid_recipe_id");
        RecipeHolder<?> untyped=body.level().getRecipeManager().byKey(id).orElseThrow(()->failure("unknown_recipe"));
        if(!supported(untyped.value()))throw failure(PROCESSING_STATIONS.containsKey(type(untyped.value()))?"machine_processing_required":"unsupported_recipe_type");
        CraftingRecipe recipe=(CraftingRecipe)untyped.value();
        @SuppressWarnings("unchecked") RecipeHolder<CraftingRecipe> holder=(RecipeHolder<CraftingRecipe>)(RecipeHolder<?>)untyped;
        if(!recipe.canCraftInDimensions(2,2))table(action,area);
        ResultContainer result=new ResultContainer();if(!result.setRecipeUsed(body.level(),body,holder))throw failure("recipe_not_unlocked");
        List<ItemStack> planned=new ArrayList<>();for(int i=0;i<36;i++)planned.add(body.getInventory().getItem(i).copy());
        List<Craft> executions=new ArrayList<>();
        for(int execution=0;execution<count;execution++) {
            List<Ingredient> all=recipe.getIngredients();List<Ingredient> required=new ArrayList<>();for(Ingredient ingredient:all)if(!ingredient.isEmpty())required.add(ingredient);
            if(required.isEmpty()||required.size()>9)throw failure("unsupported_recipe_type");
            boolean[][] matches=new boolean[required.size()][36];int[] available=new int[36];
            for(int j=0;j<36;j++){available[j]=planned.get(j).getCount();for(int i=0;i<required.size();i++)matches[i][j]=required.get(i).test(planned.get(j));}
            int[] source=IngredientAssignment.assign(matches,available);if(source==null)throw failure("insufficient_ingredients");
            int width=recipe instanceof ShapedRecipe shape?shape.getWidth():recipe.canCraftInDimensions(2,2)?2:3;
            int height=recipe instanceof ShapedRecipe shape?shape.getHeight():(required.size()+width-1)/width;
            List<ItemStack> grid=new ArrayList<>(Collections.nCopies(width*height,ItemStack.EMPTY));int index=0;
            for(int i=0;i<all.size();i++)if(!all.get(i).isEmpty())grid.set(i,planned.get(source[index++]).copyWithCount(1));
            CraftingInput input=CraftingInput.of(width,height,grid);
            if(!recipe.matches(input,body.level()))throw failure("recipe_input_mismatch");
            ItemStack output=recipe.assemble(input,body.registryAccess());if(output.isEmpty())throw failure("empty_recipe_output");
            List<ItemStack> remainders;
            net.neoforged.neoforge.common.CommonHooks.setCraftingPlayer(body);
            try{remainders=recipe.getRemainingItems(input);}finally{net.neoforged.neoforge.common.CommonHooks.setCraftingPlayer(null);}
            for(int slot:source)planned.get(slot).shrink(1);
            if(!insert(planned,output))throw failure("inventory_full");
            for(ItemStack remainder:remainders)if(!insert(planned,remainder))throw failure("inventory_full_for_remainder");
            executions.add(new Craft(input,output.copy()));
        }
        // The complete batch (including every remainder) was validated before the first mutation.
        for(int i=0;i<36;i++)body.getInventory().setItem(i,planned.get(i));
        for(Craft execution:executions) {
            execution.output.onCraftedBy(body.level(),body,execution.output.getCount());
            AbstractContainerMenu temporary=new AbstractContainerMenu(null,-1) {
                @Override public ItemStack quickMoveStack(Player player,int slot){return ItemStack.EMPTY;}
                @Override public boolean stillValid(Player player){return player==body;}
            };
            TransientCraftingContainer grid=new TransientCraftingContainer(temporary,execution.input.width(),execution.input.height());
            for(int i=0;i<execution.input.size();i++)grid.setItem(i,execution.input.getItem(i).copy());
            net.neoforged.neoforge.event.EventHooks.firePlayerCraftingEvent(body,execution.output,grid);
            result.awardUsedRecipes(body,grid.getItems());result.setRecipeUsed(holder);
        }
        body.getInventory().setChanged();body.inventoryMenu.broadcastChanges();if(menu!=null){menu.broadcastChanges();refresh();}
        JsonObject answer=new JsonObject();answer.addProperty("recipe_id",id.toString());answer.addProperty("executions",count);
        answer.addProperty("output_count",executions.stream().mapToInt(v->v.output.getCount()).sum());return answer;
    }
}
