package gl.syn.minecraft;

import java.util.Arrays;

/** Bounded exact matching: broad ingredient alternatives cannot steal a scarce input. */
final class IngredientAssignment {
    static int[] assign(boolean[][] matches, int[] counts) {
        int units=0;for(int count:counts)units+=Math.min(Math.max(0,count),matches.length);
        int[] slots=new int[units],owners=new int[units];Arrays.fill(owners,-1);
        int next=0;for(int slot=0;slot<counts.length;slot++)for(int n=0;n<Math.min(counts[slot],matches.length);n++)slots[next++]=slot;
        for(int row=0;row<matches.length;row++)if(!augment(row,matches,slots,owners,new boolean[units]))return null;
        int[] answer=new int[matches.length];Arrays.fill(answer,-1);
        for(int unit=0;unit<units;unit++)if(owners[unit]>=0)answer[owners[unit]]=slots[unit];
        return answer;
    }
    private static boolean augment(int row,boolean[][] matches,int[] slots,int[] owners,boolean[] visited) {
        for(int unit=0;unit<slots.length;unit++)if(!visited[unit]&&matches[row][slots[unit]]) {
            visited[unit]=true;
            if(owners[unit]<0||augment(owners[unit],matches,slots,owners,visited)){owners[unit]=row;return true;}
        }
        return false;
    }
}
