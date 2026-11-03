package gl.syn.minecraft;

import java.util.Arrays;

/** Dependency-free executable conservation checks, wired into Gradle check. */
public final class InventoryPlanTest {
    private static void require(boolean condition,String message) { if(!condition)throw new AssertionError(message); }
    public static void main(String[] args) {
        int[] counts=new int[36];counts[0]=3;counts[35]=2;
        int[] before=counts.clone();
        int[] pickaxe={0,0,0,-1,35,-1,-1,35,-1};
        int[] reserved=InventoryPlan.reserve(3,3,pickaxe,counts);
        require(reserved!=null&&reserved[0]==3&&reserved[35]==2,"wooden pickaxe consumes three planks and two sticks");
        require(Arrays.equals(counts,before),"validation must never mutate inventory");
        counts[0]=2;
        require(InventoryPlan.reserve(3,3,pickaxe,counts)==null,"repeated source cannot supply three ingredients from two items");
        require(InventoryPlan.reserve(2,2,new int[]{0,0,0,0},counts)==null,"table recipe cannot overdraw one source stack");
        require(InventoryPlan.reserve(1,1,new int[]{36},counts)==null,"out-of-range source rejected");
        require(InventoryPlan.reserve(1,1,new int[]{-2},counts)==null,"only -1 means empty");
        require(InventoryPlan.reserve(1,1,new int[]{2},counts)==null,"empty source rejected");
        require(InventoryPlan.reserve(3,3,new int[]{0},counts)==null,"truncated grid rejected");
        require(InventoryPlan.reserve(4,1,new int[]{0,0,35,35},counts)==null,"oversized grid rejected");
        require(InventoryPlan.reserve(0,1,new int[]{},counts)==null,"zero-sized grid rejected");
        require(InventoryPlan.reserve(1,2,new int[]{35,35},counts)[35]==2,"last inventory slot may be used twice with sufficient stock");
        System.out.println("Inventory conservation checks passed (11 assertions).");
    }
}
