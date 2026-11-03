package gl.syn.minecraft;
import java.util.*;
public final class NavigationGroundTest {
    private static void check(boolean ok){if(!ok)throw new AssertionError();}
    private static NavigationGround.Box block(double top){return new NavigationGround.Box(0,63,0,1,top,1);}
    public static void main(String[] args) {
        check(NavigationGround.resolve(.5,128,.5,List.of(block(64)))==64);
        check(NavigationGround.resolve(.5,128,.5,List.of(block(63.9375)))==63.9375); // native farmland/path
        check(NavigationGround.resolve(.5,128,.5,List.of(block(64.0625)))==64.0625); // carpet
        check(NavigationGround.resolve(.5,128,.5,List.of(block(64.125)))==64.125); // snow layer
        check(Double.isNaN(NavigationGround.resolve(.5,128,.5,List.of(block(63.5))))); // no floating half-cell
        check(NavigationGround.resolve(.5,127,.5,List.of(block(63.5)))==63.5);
        check(Double.isNaN(NavigationGround.resolve(.5,128,.5,List.of(block(63.749)))));
        check(Double.isNaN(NavigationGround.resolve(.5,128,.5,List.of())));
        check(Double.isNaN(NavigationGround.resolve(1.3,128,.5,List.of(block(64))))); // touching side isn't support
        check(NavigationGround.resolve(.5,128,.5,List.of(block(64),block(64.0625)))==64.0625);
        System.out.println("10 native-ground geometry assertions passed");
    }
}
