package gl.syn.minecraft;

import com.google.gson.*;
import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.stats.Stats;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.*;
import net.minecraft.world.item.*;
import net.minecraft.world.item.crafting.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.entity.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.*;
import net.minecraft.world.level.ClipContext;

/** Bounded player mechanics only. Recipes, priorities and factory policy stay external. */
final class ProgressionAdapter {
    static final Set<String> WORKSTATIONS=Set.of(
        "minecraft:crafting_table","minecraft:furnace","minecraft:blast_furnace","minecraft:smoker",
        "minecraft:chest","minecraft:barrel","create:shaft","create:cogwheel","create:large_cogwheel",
        "create:andesite_casing","create:gearbox","create:water_wheel","create:large_water_wheel",
        "create:mechanical_press","create:basin","create:hand_crank");

    static void metadata(AgentPlayer a,JsonObject o) {
        o.addProperty("adapter_version","0.5.0-dev2");
        o.addProperty("survival_profile","vanilla");
        o.addProperty("advancement_tracking",a.getAdvancements() instanceof net.neoforged.neoforge.common.util.FakePlayer.FakePlayerAdvancements?"disabled_fake_player":"vanilla");
        o.add("capabilities",strings("move","mine","clear_site","place","interact","use","eat","attack","craft_planks","craft","place_workstation","furnace_insert","furnace_extract"));
        o.add("observation_support",strings("advancements","inventory","workstations","deaths","harvestability"));
        JsonArray completed=new JsonArray();
        // Recipe-unlock advancements are not gameplay milestones. Query displayed achievements only.
        for(var holder:a.server.getAdvancements().getAllAdvancements())
            if(holder.value().display().isPresent()&&a.getAdvancements().getOrStartProgress(holder).isDone()) completed.add(holder.id().toString());
        o.add("advancements",completed);
        o.addProperty("deaths",a.getStats().getValue(Stats.CUSTOM.get(Stats.DEATHS)));
    }
    private static JsonArray strings(String... values) { JsonArray a=new JsonArray();for(String v:values)a.add(v);return a; }

    static boolean resource(BlockState s) {
        String id=BuiltInRegistries.BLOCK.getKey(s.getBlock()).toString();
        return s.is(Blocks.STONE)||s.is(Blocks.DEEPSLATE)||s.is(Blocks.ANDESITE)||id.endsWith("_ore");
    }
    static int toolSlot(AgentPlayer a,BlockState s) {
        int best=-1;float speed=-1;
        for(int i=0;i<36;i++) {
            ItemStack stack=a.getInventory().getItem(i);
            if(s.requiresCorrectToolForDrops()&&!stack.isCorrectToolForDrops(s)) continue;
            float value=stack.getDestroySpeed(s);
            if(value>speed) { speed=value;best=i; }
        }
        return best;
    }
    static boolean reachable(AgentPlayer a,BlockPos p) {
        return a.level().hasChunkAt(p)&&a.level().getWorldBorder().isWithinBounds(p)
            &&a.getEyePosition().distanceToSqr(Vec3.atCenterOf(p))<=20.25
            &&a.level().clip(new ClipContext(a.getEyePosition(),Vec3.atCenterOf(p),ClipContext.Block.COLLIDER,ClipContext.Fluid.NONE,a)).getBlockPos().equals(p);
    }
    static JsonObject workstation(AgentPlayer a,BlockPos p,BlockState s) {
        String id=BuiltInRegistries.BLOCK.getKey(s.getBlock()).toString();if(!WORKSTATIONS.contains(id))return null;
        JsonObject row=new JsonObject();row.add("pos",SettlementProject.pos(p));row.addProperty("block",id);row.addProperty("reachable",reachable(a,p));
        if(a.level().getBlockEntity(p) instanceof AbstractFurnaceBlockEntity furnace) {
            JsonArray slots=new JsonArray();String[] sections={"input","fuel","output"};
            for(int i=0;i<3;i++) { JsonObject slot=stack(furnace.getItem(i));slot.addProperty("slot",i);slot.addProperty("section",sections[i]);slots.add(slot); }
            row.add("slots",slots);row.addProperty("lit",s.hasProperty(AbstractFurnaceBlock.LIT)&&s.getValue(AbstractFurnaceBlock.LIT));
        }
        return row;
    }
    static JsonObject stack(ItemStack item) {
        JsonObject row=new JsonObject();row.addProperty("item",BuiltInRegistries.ITEM.getKey(item.getItem()).toString());row.addProperty("count",item.getCount());return row;
    }
    private static boolean tableNearby(AgentPlayer a) {
        for(BlockPos p:BlockPos.betweenClosed(a.blockPosition().offset(-4,-3,-4),a.blockPosition().offset(4,3,4)))
            if(a.level().hasChunkAt(p)&&a.level().getBlockState(p).is(Blocks.CRAFTING_TABLE)&&reachable(a,p))return true;
        return false;
    }
    private static void receive(AgentPlayer a,ItemStack stack) { if(!stack.isEmpty()&&!a.getInventory().add(stack))a.drop(stack,false); }

    static boolean craft(AgentPlayer a,JsonObject action) {
        int width=action.get("width").getAsInt(),height=action.get("height").getAsInt();
        if(width<1||width>3||height<1||height>3||(width>2||height>2)&&!tableNearby(a))return false;
        JsonArray slots=action.getAsJsonArray("slots");int[] sourceSlots=new int[slots.size()],counts=new int[36];
        for(int i=0;i<slots.size();i++)sourceSlots[i]=slots.get(i).getAsInt();
        for(int i=0;i<36;i++)counts[i]=a.getInventory().getItem(i).getCount();
        if(InventoryPlan.reserve(width,height,sourceSlots,counts)==null)return false;
        List<ItemStack> ingredients=new ArrayList<>();
        for(int slot:sourceSlots) {
            if(slot==-1) { ingredients.add(ItemStack.EMPTY);continue; }
            ItemStack source=a.getInventory().getItem(slot);
            ingredients.add(source.copyWithCount(1));
        }
        CraftingInput input=CraftingInput.of(width,height,ingredients);
        var recipe=a.level().getRecipeManager().getRecipeFor(RecipeType.CRAFTING,input,a.level());if(recipe.isEmpty())return false;
        ItemStack output=recipe.get().value().assemble(input,a.registryAccess());if(output.isEmpty())return false;
        if(!action.has("output")||!BuiltInRegistries.ITEM.getKey(output.getItem()).toString().equals(action.get("output").getAsString()))return false;
        ResultContainer result=new ResultContainer();
        if(!result.setRecipeUsed(a.level(),a,recipe.get()))return false;
        AbstractContainerMenu menu=new AbstractContainerMenu(null,-1) {
            @Override public ItemStack quickMoveStack(Player player,int slot) { return ItemStack.EMPTY; }
            @Override public boolean stillValid(Player player) { return player==a; }
        };
        TransientCraftingContainer grid=new TransientCraftingContainer(menu,width,height);
        for(int i=0;i<slots.size();i++) {
            int slot=slots.get(i).getAsInt();if(slot>=0)grid.setItem(i,a.getInventory().removeItem(slot,1));
        }
        // The ordinary result slot fires crafting events, recipe criteria and consumes ingredients/remainders.
        result.setItem(0,output);ResultSlot resultSlot=new ResultSlot(a,grid,result,0,0,0);
        ItemStack crafted=resultSlot.remove(output.getCount());resultSlot.onTake(a,crafted);receive(a,crafted);
        for(int i=0;i<grid.getContainerSize();i++)receive(a,grid.removeItemNoUpdate(i));
        a.getInventory().setChanged();a.inventoryMenu.broadcastChanges();return true;
    }
    static boolean furnace(AgentPlayer a,JsonObject action,boolean extract) {
        JsonArray at=action.getAsJsonArray("pos");if(at.size()!=3)return false;
        BlockPos p=new BlockPos(at.get(0).getAsInt(),at.get(1).getAsInt(),at.get(2).getAsInt());
        if(!reachable(a,p)||!(a.level().getBlockEntity(p) instanceof AbstractFurnaceBlockEntity furnace)||!furnace.stillValid(a)||!furnace.canOpen(a))return false;
        String section=action.get("section").getAsString();int amount=action.get("count").getAsInt();if(amount<1||amount>64)return false;
        if(extract) {
            if(!section.equals("output")||furnace.getItem(2).isEmpty())return false;
            if(!action.has("output")||!BuiltInRegistries.ITEM.getKey(furnace.getItem(2).getItem()).toString().equals(action.get("output").getAsString()))return false;
            FurnaceResultSlot slot=new FurnaceResultSlot(a,furnace,2,0,0);
            ItemStack output=slot.remove(amount);slot.onTake(a,output);receive(a,output);
        } else {
            int target=section.equals("input")?0:section.equals("fuel")?1:-1;
            int source=action.get("slot").getAsInt();if(target<0||source<0||source>=36)return false;
            ItemStack item=a.getInventory().getItem(source),existing=furnace.getItem(target);
            if(!action.has("item")||!BuiltInRegistries.ITEM.getKey(item.getItem()).toString().equals(action.get("item").getAsString()))return false;
            if(item.isEmpty()||!furnace.canPlaceItem(target,item)||!existing.isEmpty()&&!ItemStack.isSameItemSameComponents(item,existing))return false;
            int transfer=Math.min(amount,Math.min(item.getCount(),Math.min(item.getMaxStackSize(),furnace.getMaxStackSize())-existing.getCount()));
            if(transfer<=0)return false;
            ItemStack moved=a.getInventory().removeItem(source,transfer);
            if(existing.isEmpty())furnace.setItem(target,moved);else existing.grow(transfer);
        }
        furnace.setChanged();a.getInventory().setChanged();a.inventoryMenu.broadcastChanges();return true;
    }
}
