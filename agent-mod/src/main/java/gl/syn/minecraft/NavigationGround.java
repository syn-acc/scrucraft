package gl.syn.minecraft;

/** Maps real collision surfaces to search cells without inventing floating support. */
final class NavigationGround {
    record Box(double minX,double minY,double minZ,double maxX,double maxY,double maxZ) {}
    static double resolve(double x,int halfY,double z,Iterable<Box> collisions) {
        double highest=Double.NaN;
        for(Box box:collisions) {
            if(box.maxX()<=x-.3||box.minX()>=x+.3||box.maxZ()<=z-.3||box.minZ()>=z+.3)continue;
            double top=box.maxY();
            // Exactly the same quantization as the search cell. Adjacent half-height
            // cells never acquire the same floor, and a quarter-block void is not support.
            if(!Double.isFinite(top)||Math.round(top*2)!=halfY)continue;
            if(Double.isNaN(highest)||top>highest)highest=top;
        }
        return highest;
    }
}
