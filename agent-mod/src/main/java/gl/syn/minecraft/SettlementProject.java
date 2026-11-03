package gl.syn.minecraft;

import com.google.gson.*;
import java.util.*;
import net.minecraft.core.*;
import net.minecraft.server.level.*;
import net.minecraft.world.level.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.phys.*;

/** One shared, bounded starter shelter. All construction uses player actions. */
final class SettlementProject {
    final BlockPos origin;
    final String dimension;
    SettlementProject(BlockPos origin,String dimension) { this.origin=origin; this.dimension=dimension; }
    static boolean soil(BlockState s) { return s.is(Blocks.DIRT)||s.is(Blocks.GRASS_BLOCK)||s.is(Blocks.COARSE_DIRT)||s.is(Blocks.PODZOL)||s.is(Blocks.ROOTED_DIRT); }
    static SettlementProject survey(ServerLevel level,BlockPos near) {
        BlockPos best=null; int score=Integer.MAX_VALUE;
        for(int dx=-16;dx<=16;dx+=2) for(int dz=-16;dz<=16;dz+=2) {
            BlockPos center=near.offset(dx,0,dz);
            if(!level.hasChunkAt(center)) continue;
            int y=level.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES,center.getX(),center.getZ());
            if(Math.abs(y-near.getY())>6) continue;
            BlockPos base=new BlockPos(center.getX()-2,y,center.getZ()-2);
            int cost=dx*dx+dz*dz; boolean valid=true;
            for(int x=-2;x<5&&valid;x++) for(int z=0;z<5&&valid;z++) {
                if(x<0&&z!=2) continue;
                BlockPos p=base.offset(x,0,z);
                int top=level.getHeight(Heightmap.Types.MOTION_BLOCKING_NO_LEAVES,p.getX(),p.getZ());
                if(Math.abs(top-y)>1||!level.getWorldBorder().isWithinBounds(p)||!soil(level.getBlockState(new BlockPos(p.getX(),top-1,p.getZ())))) { valid=false; break; }
                cost+=Math.abs(top-y)*4;
                for(int h=0;h<4;h++) { BlockState s=level.getBlockState(p.above(h)); if(!(s.isAir()||s.canBeReplaced()||soil(s))||!s.getFluidState().isEmpty()||s.hasBlockEntity()) valid=false; }
            }
            if(valid&&cost<score) { score=cost; best=base; }
        }
        return best==null?null:new SettlementProject(best,level.dimension().location().toString());
    }
    JsonObject save() { JsonObject o=new JsonObject(); o.addProperty("dimension",dimension); o.add("origin",pos(origin)); return o; }
    static SettlementProject load(JsonObject o) { JsonArray p=o.getAsJsonArray("origin"); return new SettlementProject(new BlockPos(p.get(0).getAsInt(),p.get(1).getAsInt(),p.get(2).getAsInt()),o.get("dimension").getAsString()); }
    static JsonArray pos(BlockPos p) { JsonArray a=new JsonArray(); a.add(p.getX());a.add(p.getY());a.add(p.getZ());return a; }
    boolean contains(BlockPos p) { int x=p.getX()-origin.getX(),z=p.getZ()-origin.getZ(),h=p.getY()-origin.getY();return (x>=0&&x<5&&z>=0&&z<5||x>=-2&&x<0&&z==2)&&h>=0&&h<4; }
    boolean buildCell(BlockPos p) {
        int x=p.getX()-origin.getX(),z=p.getZ()-origin.getZ(),h=p.getY()-origin.getY();
        return x>=-2&&x<0&&z==2&&h>=-1&&h<=(x==-2?0:1)||x>=0&&x<5&&z>=0&&z<5&&(h==-1||h==2||h>=0&&h<=1&&(x==0||x==4||z==0||z==4)&&!(z==0&&x==2));
    }
    JsonObject observe(AgentPlayer a) {
        JsonObject o=save(); o.addProperty("name","shared starter shelter"); JsonArray clear=new JsonArray(),cells=new JsonArray(); int done=0,total=0;
        if(!dimension.equals(a.level().dimension().location().toString())) { o.addProperty("wrong_dimension",true); return o; }
        for(int x=-2;x<5;x++) for(int z=0;z<5;z++) {
            if(x<0&&z!=2) continue;
            for(int h=0;h<4;h++) {
                BlockPos p=origin.offset(x,h,z); BlockState s=a.level().getBlockState(p);
                if(soil(s)) { JsonObject row=new JsonObject(); row.add("pos",pos(p)); row.addProperty("reachable",reachable(a,p)); clear.add(row); }
            }
            for(int h=-1;h<=2;h++) {
                boolean wall=(x==0||x==4||z==0||z==4)&&h>=0&&h<=1&&!(z==0&&x==2);
                if(!buildCell(origin.offset(x,h,z))) continue;
                BlockPos p=origin.offset(x,h,z); BlockState state=a.level().getBlockState(p);
                JsonObject row=new JsonObject(); row.add("pos",pos(p)); row.addProperty("stage",h==-1?0:h==2?2:1);
                boolean built=state.isFaceSturdy(a.level(),p,Direction.UP); row.addProperty("done",built); total++; if(built) done++;
                row.addProperty("occupied",a.getBoundingBox().intersects(new AABB(p))||!a.level().getEntities(a,new AABB(p),ent->ent instanceof net.minecraft.world.entity.LivingEntity).isEmpty());
                if(!built) for(Direction d:Direction.values()) {
                    BlockPos support=p.relative(d); Direction face=d.getOpposite();
                    if(a.level().getBlockState(support).isFaceSturdy(a.level(),support,face)) {
                        row.addProperty("supported",true);
                        if(reachable(a,support)) { row.add("support",pos(support));row.addProperty("face",face.getName());break; }
                    }
                }
                cells.add(row);
            }
        }
        o.add("clear",clear);o.add("cells",cells);o.addProperty("done",done);o.addProperty("total",total);o.addProperty("complete",done==total&&clear.isEmpty());return o;
    }
    static boolean reachable(AgentPlayer a,BlockPos p) { return a.level().hasChunkAt(p)&&a.getEyePosition().distanceToSqr(Vec3.atCenterOf(p))<=20.25&&a.level().getWorldBorder().isWithinBounds(p)&&a.level().clip(new ClipContext(a.getEyePosition(),Vec3.atCenterOf(p),ClipContext.Block.COLLIDER,ClipContext.Fluid.NONE,a)).getBlockPos().equals(p); }
}
