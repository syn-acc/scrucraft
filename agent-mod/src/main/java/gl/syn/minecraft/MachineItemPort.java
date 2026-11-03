package gl.syn.minecraft;

import com.google.gson.*;
import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.block.state.BlockState;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.items.IItemHandler;
import net.neoforged.neoforge.items.wrapper.InvWrapper;

/** Explicit, nearby access to reviewed native Create item ports; never a fabricated GUI. */
final class MachineItemPort {
    static final Set<String> BLOCKS=Set.of("create:depot","create:basin","create:millstone","create:fluid_tank","create:spout","create:item_drain");
    final String session=UUID.randomUUID().toString();
    final BlockPos position;
    final String block;
    long revision;
    private final AgentPlayer body;
    private final BlockEntity entity;
    private final IItemHandler port,player;
    private final Direction face;
    private final FluidPortView fluids;
    private final int slots;
    private List<ItemStack> snapshot=List.of();

    static boolean supports(BlockState state){return BLOCKS.contains(BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString());}
    MachineItemPort(AgentPlayer body,BlockPos pos,JsonObject area,Direction face) {
        this.body=body;position=pos;block=BuiltInRegistries.BLOCK.getKey(body.level().getBlockState(pos).getBlock()).toString();
        this.face=face;
        if(block.equals("create:item_drain")&&face!=null&&!face.getAxis().isHorizontal())throw reject("unsupported_item_port_face");
        entity=body.level().getBlockEntity(pos);
        port=body.level().getCapability(Capabilities.ItemHandler.BLOCK,pos,face);
        fluids=FluidPortView.BLOCKS.contains(block)?new FluidPortView(body,pos,area):null;
        if(entity==null||port==null&&fluids==null)throw reject("machine_item_port_unavailable");
        if(face!=null&&port==null)throw reject("item_port_unavailable_on_face");
        slots=port==null?0:port.getSlots();
        int expected=switch(block){case "create:depot"->9;case "create:basin"->18;case "create:millstone"->10;case "create:item_drain"->face==null?0:1;default->0;};
        if(slots!=expected)throw reject("unsupported_machine_port_layout");
        player=new InvWrapper(body.getInventory());validate(area);
    }
    private static NativeActionException reject(String reason){return new NativeActionException(reason);}
    private static int number(JsonObject value,String key,int min,int max) {
        double v=value.get(key).getAsDouble();
        if(!Double.isFinite(v)||v!=Math.rint(v)||v<min||v>max)throw reject("invalid_"+key);return(int)v;
    }
    void validate(JsonObject area) {
        BodyAccess.require(body,position,area);
        if(!body.isAlive()||body.isRemoved())throw reject("body_unavailable");
        if(!BodyAccess.reachable(body,position))throw reject("out_of_reach_or_occluded");
        if(body.containerMenu!=body.inventoryMenu||body.level().getBlockEntity(position)!=entity
            ||!block.equals(BuiltInRegistries.BLOCK.getKey(body.level().getBlockState(position).getBlock()).toString())
            ||body.level().getCapability(Capabilities.ItemHandler.BLOCK,position,face)!=port||port!=null&&port.getSlots()!=slots)
            throw reject("container_changed");
        if(fluids!=null)fluids.validate(area);
        refresh();
    }
    private void refresh() {
        List<ItemStack> current=new ArrayList<>();
        for(int i=0;i<slots;i++)current.add(port.getStackInSlot(i).copy());
        for(int i=0;i<36;i++)current.add(player.getStackInSlot(i).copy());
        boolean changed=current.size()!=snapshot.size();
        if(!changed)for(int i=0;i<current.size();i++)if(!ItemStack.matches(current.get(i),snapshot.get(i))){changed=true;break;}
        boolean fluidChanged=fluids!=null&&fluids.refresh();changed|=fluidChanged;
        if(changed){revision++;snapshot=current;}
    }
    void requireHandle(JsonObject action) {
        refresh();
        if(!action.has("session_id")||!session.equals(action.get("session_id").getAsString()))throw reject("stale_container_session");
        if(!action.has("revision")||action.get("revision").getAsDouble()!=revision)throw reject("stale_container_revision");
    }
    ItemStack stack(int index){if(index<0||index>=slots)throw reject("invalid_slot");return port.getStackInSlot(index);}
    private record Ref(IItemHandler inventory,int slot){}
    private Ref reference(JsonObject value) {
        String inventory=value.get("inventory").getAsString();
        if(inventory.equals("player"))return new Ref(player,number(value,"slot",0,35));
        if(inventory.equals("container"))return new Ref(port,number(value,"slot",0,slots-1));
        throw reject("invalid_inventory");
    }
    private void preserve(ItemStack remainder) {
        if(!remainder.isEmpty()&&!body.getInventory().add(remainder))body.drop(remainder,false);
    }
    JsonObject move(JsonObject action,JsonObject area) {
        validate(area);requireHandle(action);
        Ref source=reference(action.getAsJsonObject("from")),dest=reference(action.getAsJsonObject("to"));
        if(source.equals(dest))throw reject("same_slot");
        int count=number(action,"count",1,64);
        ItemStack before=source.inventory.getStackInSlot(source.slot).copy();
        if(before.isEmpty()||before.getCount()<count)throw reject("insufficient_items");
        ItemStack simulated=source.inventory.extractItem(source.slot,count,true);
        if(simulated.getCount()!=count||!ItemStack.isSameItemSameComponents(before,simulated))throw reject("slot_rule_rejected");
        ItemStack target=dest.inventory.getStackInSlot(dest.slot);
        if(!target.isEmpty()&&!ItemStack.isSameItemSameComponents(simulated,target))throw reject("incompatible_stack");
        if(!dest.inventory.isItemValid(dest.slot,simulated))throw reject("slot_rule_rejected");
        if(Math.min(dest.inventory.getSlotLimit(dest.slot),simulated.getMaxStackSize())-target.getCount()<count)throw reject("insufficient_slot_capacity");
        if(!dest.inventory.insertItem(dest.slot,simulated.copy(),true).isEmpty())throw reject("slot_rule_rejected");
        // No other game tick can intervene. Use the actual handler contracts, never setStackInSlot.
        ItemStack extracted=source.inventory.extractItem(source.slot,count,false);
        if(extracted.getCount()!=count||!ItemStack.isSameItemSameComponents(extracted,simulated)) {
            preserve(extracted);throw new IllegalStateException("native_port_extraction_changed");
        }
        ItemStack remainder=dest.inventory.insertItem(dest.slot,extracted.copy(),false);
        if(!remainder.isEmpty()) {
            preserve(remainder);throw new IllegalStateException("native_port_insertion_changed");
        }
        entity.setChanged();body.getInventory().setChanged();body.inventoryMenu.broadcastChanges();refresh();
        JsonObject result=observe();result.addProperty("moved",count);return result;
    }
    JsonObject observe() {
        refresh();JsonObject result=new JsonObject();result.addProperty("open",true);result.addProperty("kind",port==null?"machine_fluid_port":"machine_item_port");
        result.addProperty("session_id",session);result.addProperty("revision",revision);result.addProperty("block",block);
        result.add("position",SettlementProject.pos(position));result.addProperty("dimension",body.level().dimension().location().toString());
        if(face!=null)result.addProperty("item_port_face",face.getName());
        JsonArray rows=new JsonArray();
        for(int i=0;i<slots+36;i++) {
            boolean local=i>=slots;int index=local?i-slots:i;IItemHandler handler=local?player:port;
            ItemStack item=handler.getStackInSlot(index);JsonObject row=BodyInventory.describeStack(item,body.registryAccess());
            row.addProperty("inventory",local?"player":"container");row.addProperty("slot",index);
            row.addProperty("capacity",Math.min(handler.getSlotLimit(index),item.isEmpty()?64:item.getMaxStackSize()));
            row.addProperty("can_take",!handler.extractItem(index,1,true).isEmpty());
            row.addProperty("role",local?(index<9?"hotbar":"main"):switch(block){
                case "create:depot"->index==0?"input_or_held":"output";
                case "create:millstone"->index==0?"input":"output";
                case "create:item_drain"->"input_or_held";
                default->index<9?"input":"output";});
            rows.add(row);
        }
        result.add("slots",rows);result.add("cursor",BodyInventory.describeStack(body.containerMenu.getCarried(),body.registryAccess()));
        if(fluids!=null){result.add("fluids",fluids.observe());result.add("fluid_structure",fluids.members());result.addProperty("fluid_amount_unit","mB");}
        result.addProperty("processing_executor","native_world_ticks");return result;
    }
}
