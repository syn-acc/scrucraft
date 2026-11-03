package gl.syn.minecraft;
import java.util.*;
public final class NavigationSearchTest {
    private static void check(boolean ok) {if(!ok)throw new AssertionError();}
    private static NavigationSearch search(Set<NavigationSearch.Cell> cells,int cap) {
        return new NavigationSearch(new NavigationSearch.Terrain(){
            public boolean standing(NavigationSearch.Cell c){return cells.contains(c);}
            public boolean traversable(NavigationSearch.Cell a,NavigationSearch.Cell b){return Math.abs(a.halfY()-b.halfY())<=2;}
        },new NavigationSearch.Cell(0,128,0),new NavigationSearch.Cell(4,128,0),cap);
    }
    public static void main(String[] args) {
        NavigationGroundTest.main(args);
        Set<NavigationSearch.Cell> cells=new HashSet<>();
        for(int x=0;x<=4;x++)for(int z=0;z<=1;z++)cells.add(new NavigationSearch.Cell(x,128,z));
        cells.remove(new NavigationSearch.Cell(2,128,0));
        var s=search(cells,100);s.step(1,Long.MAX_VALUE);check(s.state().equals("searching"));
        s.step(100,Long.MAX_VALUE);check(s.state().equals("ready"));check(s.path().size()==7);
        check(s.path().stream().allMatch(cells::contains));
        var capped=search(cells,2);capped.step(100,Long.MAX_VALUE);check(capped.state().equals("search_budget_exhausted"));
        cells.remove(new NavigationSearch.Cell(2,128,1));
        var blocked=search(cells,100);blocked.step(100,Long.MAX_VALUE);check(blocked.state().equals("unreachable"));
        var cancelled=search(cells,100);cancelled.cancel();cancelled.step(100,Long.MAX_VALUE);check(cancelled.state().equals("cancelled"));
        var deadline=search(cells,100);deadline.step(100,0);check(deadline.visited()==1);
        cells.remove(new NavigationSearch.Cell(4,128,0));check(search(cells,100).state().equals("invalid_endpoint"));
        System.out.println("9 navigation search assertions passed");
    }
}
