package gl.syn.minecraft;

import java.util.*;

/** Incremental, bounded A*. Terrain access stays on the Minecraft tick thread. */
public final class NavigationSearch {
    public record Cell(int x, int halfY, int z) {}
    public interface Terrain {
        boolean standing(Cell at);
        boolean traversable(Cell from, Cell to);
    }
    private record Entry(Cell cell, double score, double cost) {}
    private final Terrain terrain;
    private final Cell start, goal;
    private final int maxNodes;
    private final PriorityQueue<Entry> open = new PriorityQueue<>(Comparator.comparingDouble(Entry::score));
    private final Map<Cell, Double> costs = new HashMap<>();
    private final Map<Cell, Cell> parents = new HashMap<>();
    private List<Cell> path = List.of();
    private String state = "searching";
    public NavigationSearch(Terrain terrain, Cell start, Cell goal, int maxNodes) {
        this.terrain=terrain; this.start=start; this.goal=goal; this.maxNodes=maxNodes;
        if (!terrain.standing(start) || !terrain.standing(goal)) { state="invalid_endpoint"; return; }
        costs.put(start,0.0); open.add(new Entry(start,heuristic(start),0));
    }
    private double heuristic(Cell cell) {
        // Vertical movement can accompany horizontal movement; horizontal Manhattan is admissible.
        return Math.abs(cell.x-goal.x)+Math.abs(cell.z-goal.z);
    }
    public String state() { return state; }
    public List<Cell> path() { return path; }
    public int visited() { return costs.size(); }
    public void cancel() { if(state.equals("searching")) state="cancelled"; open.clear(); }
    public void step(int expansions, long deadlineNanos) {
        while (state.equals("searching") && expansions-->0 && System.nanoTime()<deadlineNanos) {
            if(open.isEmpty()) { state="unreachable"; return; }
            Entry current=open.remove();
            if(current.cost!=costs.get(current.cell)) continue;
            if(current.cell.equals(goal)) {
                LinkedList<Cell> route=new LinkedList<>();
                for(Cell c=goal;c!=null;c=parents.get(c))route.addFirst(c);
                path=List.copyOf(route);state="ready";open.clear();return;
            }
            for(int[] d:new int[][]{{1,0},{-1,0},{0,1},{0,-1}}) {
                for(int dy:new int[]{0,1,2,-1,-2,-3,-4,-5,-6}) {
                    Cell next=new Cell(current.cell.x+d[0],current.cell.halfY+dy,current.cell.z+d[1]);
                    if(Math.abs(next.x-start.x)>64 || Math.abs(next.z-start.z)>64
                            || Math.abs(next.halfY-start.halfY)>32)continue;
                    if(!terrain.standing(next)||!terrain.traversable(current.cell,next))continue;
                    double cost=current.cost+1+Math.abs(dy)*.25;
                    if(cost>=costs.getOrDefault(next,Double.POSITIVE_INFINITY))continue;
                    if(!costs.containsKey(next)&&costs.size()>=maxNodes) {state="search_budget_exhausted";return;}
                    costs.put(next,cost);parents.put(next,current.cell);
                    open.add(new Entry(next,cost+heuristic(next),cost));
                }
            }
        }
    }
}
