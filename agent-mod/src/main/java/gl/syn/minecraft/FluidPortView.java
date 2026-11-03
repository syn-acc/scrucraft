package gl.syn.minecraft;

import com.google.gson.*;
import com.mojang.serialization.JsonOps;
import java.lang.reflect.InvocationTargetException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.core.component.DataComponentMap;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.neoforged.neoforge.capabilities.Capabilities;
import net.neoforged.neoforge.fluids.FluidStack;
import net.neoforged.neoforge.fluids.capability.IFluidHandler;

/** Read-only native fluid capabilities. All fluid mutations remain actual game interactions/ticks. */
final class FluidPortView {
    static final Set<String> BLOCKS=Set.of("create:basin","create:fluid_tank","create:spout","create:item_drain");
    private final AgentPlayer body;
    private final BlockPos position;
    private final String block;
    private final IFluidHandler handler;
    private final Map<BlockPos,BlockEntity> members;
    private List<FluidStack> snapshot=List.of();
    private List<Integer> capacities=List.of();

    FluidPortView(AgentPlayer body,BlockPos position,JsonObject area) {
        this.body=body;this.position=position;
        block=BuiltInRegistries.BLOCK.getKey(body.level().getBlockState(position).getBlock()).toString();
        if(!BLOCKS.contains(block))throw reject("unsupported_fluid_port");
        handler=body.level().getCapability(Capabilities.FluidHandler.BLOCK,position,null);
        if(handler==null)throw reject("machine_fluid_port_unavailable");
        int expected=block.equals("create:basin")?4:1;
        if(handler.getTanks()!=expected)throw reject("unsupported_fluid_port_layout");
        members=footprint(body,position,area);validate(area);
    }
    private static NativeActionException reject(String reason){return new NativeActionException(reason);}
    private static Object call(Object target,String method) {
        try{return target.getClass().getMethod(method).invoke(target);}
        catch(InvocationTargetException ex){throw new IllegalStateException("native_fluid_hook_failed",ex.getCause());}
        catch(ReflectiveOperationException ex){throw new IllegalStateException("native_fluid_api_changed",ex);}
    }
    private static Map<BlockPos,BlockEntity> footprint(AgentPlayer body,BlockPos position,JsonObject area) {
        BodyAccess.require(body,position,area);
        BlockEntity entity=body.level().getBlockEntity(position);
        if(entity==null)throw reject("container_changed");
        String block=BuiltInRegistries.BLOCK.getKey(body.level().getBlockState(position).getBlock()).toString();
        if(!block.equals("create:fluid_tank"))return Map.of(position,entity);
        Object value=call(entity,"getControllerBE");
        if(!(value instanceof BlockEntity controller))throw reject("machine_structure_not_ready");
        int width=((Number)call(controller,"getWidth")).intValue(),height=((Number)call(controller,"getHeight")).intValue();
        int maxWidth=((Number)call(controller,"getMaxSize")).intValue(),maxHeight=((Number)call(controller,"getMaxHeight")).intValue();
        if(width<1||width>maxWidth||height<1||height>maxHeight||(long)width*width*height>4096)throw reject("unsupported_fluid_tank_dimensions");
        Map<BlockPos,BlockEntity> cells=new LinkedHashMap<>();
        BlockPos origin=controller.getBlockPos();
        for(int x=0;x<width;x++)for(int y=0;y<height;y++)for(int z=0;z<width;z++) {
            BlockPos cell=origin.offset(x,y,z);BodyAccess.require(body,cell,area);
            BlockEntity member=body.level().getBlockEntity(cell);
            if(member==null||!BuiltInRegistries.BLOCK.getKey(body.level().getBlockState(cell).getBlock()).toString().equals("create:fluid_tank")
                ||call(member,"getControllerBE")!=controller)throw reject("machine_structure_not_ready");
            cells.put(cell,member);
        }
        if(!cells.containsKey(position))throw reject("machine_structure_not_ready");
        return cells;
    }
    void validate(JsonObject area) {
        if(body.level().getCapability(Capabilities.FluidHandler.BLOCK,position,null)!=handler
            ||!footprint(body,position,area).equals(members))throw reject("container_changed");
    }
    boolean refresh() {
        List<FluidStack> fluids=new ArrayList<>();List<Integer> limits=new ArrayList<>();
        for(int tank=0;tank<handler.getTanks();tank++) {
            fluids.add(handler.getFluidInTank(tank).copy());limits.add(handler.getTankCapacity(tank));
        }
        boolean changed=fluids.size()!=snapshot.size()||!limits.equals(capacities);
        if(!changed)for(int i=0;i<fluids.size();i++)if(!FluidStack.matches(fluids.get(i),snapshot.get(i))){changed=true;break;}
        if(changed){snapshot=fluids;capacities=limits;}
        return changed;
    }
    JsonArray observe() {
        JsonArray rows=new JsonArray();
        for(int tank=0;tank<handler.getTanks();tank++) {
            FluidStack fluid=handler.getFluidInTank(tank);JsonObject row=new JsonObject();
            row.addProperty("tank",tank);row.addProperty("fluid",BuiltInRegistries.FLUID.getKey(fluid.getFluid()).toString());
            row.addProperty("empty",fluid.isEmpty());row.addProperty("amount_mB",fluid.getAmount());row.addProperty("capacity_mB",handler.getTankCapacity(tank));
            // Basin exposes its output wrapper first, then its input wrapper (unlike item slots).
            row.addProperty("role",block.equals("create:basin")?(tank<2?"output":"input"):
                block.equals("create:spout")?"input":block.equals("create:item_drain")?"output":"storage");
            JsonElement components=DataComponentMap.CODEC.encodeStart(body.registryAccess().createSerializationContext(JsonOps.INSTANCE),fluid.getComponents())
                .result().orElseThrow(()->reject("fluid_components_unavailable"));
            byte[] encoded=components.toString().getBytes(StandardCharsets.UTF_8);row.addProperty("component_bytes",encoded.length);
            if(encoded.length<=2048)row.add("components",components);
            else {
                row.addProperty("components_truncated",true);
                try{row.addProperty("components_sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(encoded)));}
                catch(NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}
            }
            rows.add(row);
        }
        return rows;
    }
    JsonArray members() {JsonArray cells=new JsonArray();members.keySet().forEach(p->cells.add(SettlementProject.pos(p)));return cells;}
    static boolean reviewedBucketUse(AgentPlayer body,BlockPos position,ItemStack held,JsonObject area) {
        if(!BuiltInRegistries.BLOCK.getKey(body.level().getBlockState(position).getBlock()).toString().equals("create:basin"))return false;
        if(!(held.is(Items.BUCKET)||held.is(Items.WATER_BUCKET)||held.is(Items.LAVA_BUCKET)||held.is(Items.MILK_BUCKET)))return false;
        BodyAccess.require(body,position,area);
        if(!BodyAccess.reachable(body,position))throw reject("out_of_reach_or_occluded");
        return true;
    }
}
