package gl.syn.minecraft;

import java.util.Arrays;

public final class IngredientAssignmentTest {
    private static void check(boolean value){if(!value)throw new AssertionError();}
    private static boolean possible(boolean[][] matches,int[] counts,int row) {
        if(row==matches.length)return true;
        for(int slot=0;slot<counts.length;slot++)if(counts[slot]>0&&matches[row][slot]) {
            counts[slot]--;boolean okay=possible(matches,counts,row+1);counts[slot]++;if(okay)return true;
        }return false;
    }
    public static void main(String[] args) {
        check(Arrays.equals(IngredientAssignment.assign(new boolean[][]{{true,true},{true,false}},new int[]{1,1}),new int[]{1,0}));
        check(IngredientAssignment.assign(new boolean[][]{{true},{true}},new int[]{1})==null);
        check(Arrays.equals(IngredientAssignment.assign(new boolean[][]{{true},{true}},new int[]{2}),new int[]{0,0}));
        check(IngredientAssignment.assign(new boolean[][]{{false,false}},new int[]{2,2})==null);
        check(IngredientAssignment.assign(new boolean[0][0],new int[]{2}).length==0);
        int[] counts={2,1};IngredientAssignment.assign(new boolean[][]{{true,true}},counts);check(Arrays.equals(counts,new int[]{2,1}));
        int cases=0;
        for(int mask=0;mask<512;mask++)for(int stock=0;stock<27;stock++) {
            boolean[][] matches=new boolean[3][3];for(int i=0;i<9;i++)matches[i/3][i%3]=(mask&(1<<i))!=0;
            int[] available={stock%3,stock/3%3,stock/9};int[] answer=IngredientAssignment.assign(matches,available);
            check((answer!=null)==possible(matches,available.clone(),0));
            if(answer!=null){int[] used=new int[3];for(int i=0;i<3;i++){check(matches[i][answer[i]]);used[answer[i]]++;}for(int i=0;i<3;i++)check(used[i]<=available[i]);}
            cases++;
        }
        System.out.println("6 ingredient assertions and "+cases+" exhaustive matching cases passed");
    }
}
