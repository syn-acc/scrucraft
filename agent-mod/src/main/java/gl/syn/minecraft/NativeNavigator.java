package gl.syn.minecraft;

import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

/** Collision-aware locomotion only. Never mines, places, teleports or loads chunks. */
public final class NativeNavigator implements NavigationSearch.Terrain {
    private final AgentPlayer body;
    private NavigationSearch search;
    private NavigationSearch.Cell goal;
    private List<NavigationSearch.Cell> path=List.of();
    private int index, stalled, replans, remaining;
    private Vec3 checkpoint;
    private String state="idle", reason="";
    public NativeNavigator(AgentPlayer body) {this.body=body;}
    private NavigationSearch.Cell cell(Vec3 p) {
        return new NavigationSearch.Cell((int)Math.floor(p.x),(int)Math.round(p.y*2),(int)Math.floor(p.z));
    }
    private Vec3 point(NavigationSearch.Cell c) {return new Vec3(c.x()+.5,c.halfY()/2.0,c.z()+.5);}
    private AABB bounds(Vec3 p) {return new AABB(p.x-.3,p.y+.001,p.z-.3,p.x+.3,p.y+1.8,p.z+.3);}
    private boolean clear(Vec3 p) {
        var world=body.serverLevel();
        for(double dx:new double[]{-.3,.3})for(double dz:new double[]{-.3,.3}) {
            BlockPos at=BlockPos.containing(p.x+dx,p.y,p.z+dz);
            if(!world.hasChunkAt(at)||!world.getWorldBorder().isWithinBounds(at))return false;
            for(int dy=-1;dy<=2;dy++) {
                var s=world.getBlockState(at.above(dy));
                if(!s.getFluidState().isEmpty()||s.is(Blocks.MAGMA_BLOCK)||s.is(Blocks.CAMPFIRE)
                    ||s.is(Blocks.SOUL_CAMPFIRE)||s.is(Blocks.FIRE)||s.is(Blocks.SOUL_FIRE)
                    ||s.is(Blocks.CACTUS)||s.is(Blocks.SWEET_BERRY_BUSH)||s.is(Blocks.POWDER_SNOW))return false;
            }
        }
        return world.noCollision(body,bounds(p));
    }
    public boolean standing(NavigationSearch.Cell c) {
        Vec3 p=point(c);
        return clear(p)&&!body.serverLevel().noCollision(body,bounds(p).move(0,-.05,0));
    }
    public boolean traversable(NavigationSearch.Cell from,NavigationSearch.Cell to) {
        Vec3 a=point(from),b=point(to);
        if(b.y-a.y>1 || a.y-b.y>3)return false;
        double upper=Math.max(a.y,b.y);
        if(!clear(new Vec3(a.x,upper,a.z)))return false;
        for(int i=1;i<=5;i++) {
            double t=i/5.0;
            if(!clear(new Vec3(a.x+(b.x-a.x)*t,upper,a.z+(b.z-a.z)*t)))return false;
        }
        // A drop must have a clear landing column, not just a clear end cell.
        for(double y=upper;y>b.y;y-=.25)if(!clear(new Vec3(b.x,y,b.z)))return false;
        return standing(to);
    }
    public void start(double x,double y,double z,int timeoutTicks) {
        cancel("replaced");
        if(!Double.isFinite(x)||!Double.isFinite(y)||!Double.isFinite(z)
                ||body.position().distanceToSqr(new Vec3(x,y,z))>64*64) {
            state="failed";reason="target_out_of_range";return;
        }
        goal=cell(new Vec3(x,y,z));remaining=Math.min(1200,Math.max(20,timeoutTicks));
        stalled=0;replans=0;checkpoint=body.position();begin();
    }
    private void begin() {
        body.zza=0;body.xxa=0;path=List.of();index=1;
        search=new NavigationSearch(this,cell(body.position()),goal,4096);state="started";
    }
    public void cancel(String why) {
        if(search!=null)search.cancel();
        body.zza=0;body.xxa=0;state="cancelled";reason=why;
    }
    public String state() {return state;}
    public String reason() {return reason;}
    public void tick(long deadlineNanos) {
        if(!state.equals("started"))return;
        if(--remaining<=0) {cancel("timeout");state="failed";return;}
        if(!body.isAlive()) {cancel("dead");state="failed";return;}
        if(search.state().equals("searching"))search.step(16,deadlineNanos);
        if(search.state().equals("searching"))return;
        if(!search.state().equals("ready")) {cancel(search.state());state="failed";return;}
        if(path.isEmpty())path=search.path();
        if(index>=path.size()) {
            if(body.position().distanceToSqr(point(goal))<.25&&body.onGround()) {
                body.zza=0;body.xxa=0;state="done";reason="arrived";return;
            }
            index=path.size()-1;
        }
        Vec3 target=point(path.get(index));
        if(body.position().distanceToSqr(target)<.16 && body.onGround() && index<path.size()-1) {
            target=point(path.get(++index));
        }
        boolean obstructed=!standing(path.get(index))
            ||(index>0&&!traversable(path.get(index-1),path.get(index)));
        if(++stalled>=30) {
            obstructed|=body.position().distanceToSqr(checkpoint)<.16;
            stalled=0;checkpoint=body.position();
        }
        if(obstructed) {
            if(++replans>3) {cancel("blocked");state="failed";} else begin();
            return;
        }
        Vec3 delta=target.subtract(body.position());
        body.setYRot((float)(Math.atan2(-delta.x,delta.z)*180/Math.PI));body.setYHeadRot(body.getYRot());
        body.zza=.8f;body.xxa=0;
        if(body.onGround()&&(delta.y>.4||body.horizontalCollision))body.jumpFromGround();
    }
}
