package gl.syn.minecraft;

import com.google.gson.*;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.Vec3;

/** Optional owner-selected bounds from the current short-lived gateway grant. */
final class BodyAccess {
    static void require(AgentPlayer body,BlockPos pos,JsonObject area) {
        if(area!=null) {
        if(!area.has("dimension")||!area.has("min")||!area.has("max"))throw new NativeActionException("invalid_work_area");
        if(!body.level().dimension().location().toString().equals(area.get("dimension").getAsString()))throw new NativeActionException("wrong_dimension");
        JsonArray min=area.getAsJsonArray("min"),max=area.getAsJsonArray("max");
        if(min.size()!=3||max.size()!=3)throw new NativeActionException("invalid_work_area");
        int[] p={pos.getX(),pos.getY(),pos.getZ()};
        for(int i=0;i<3;i++) {
            double lo=min.get(i).getAsDouble(),hi=max.get(i).getAsDouble();
            if(!Double.isFinite(lo)||!Double.isFinite(hi)||lo>=hi)throw new NativeActionException("invalid_work_area");
            if(p[i]<lo||p[i]>=hi)throw new NativeActionException("outside_work_area");
        }
        }
        if(!body.level().hasChunkAt(pos))throw new NativeActionException("chunk_unloaded");
        if(!body.level().getWorldBorder().isWithinBounds(pos)||body.level().isOutsideBuildHeight(pos))throw new NativeActionException("outside_world_bounds");
    }
    static boolean reachable(AgentPlayer body,BlockPos pos) {
        if(!body.level().hasChunkAt(pos))return false;
        var shape=body.level().getBlockState(pos).getShape(body.level(),pos);
        if(shape.isEmpty())return false;
        Vec3 target=shape.bounds().getCenter().add(pos.getX(),pos.getY(),pos.getZ());
        var trace=body.level().clip(new ClipContext(body.getEyePosition(),target,ClipContext.Block.OUTLINE,ClipContext.Fluid.NONE,body));
        return body.getEyePosition().distanceToSqr(target)<=20.25
            &&trace.getType()==net.minecraft.world.phys.HitResult.Type.BLOCK&&trace.getBlockPos().equals(pos);
    }
}
