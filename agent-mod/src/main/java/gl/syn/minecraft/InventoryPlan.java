package gl.syn.minecraft;

/** Inventory reservations validated before any crafting ingredient is removed. */
final class InventoryPlan {
    static int[] reserve(int width,int height,int[] slots,int[] counts) {
        if(width<1||width>3||height<1||height>3||slots.length!=width*height||counts.length!=36)return null;
        int[] required=new int[36];
        for(int slot:slots) {
            if(slot==-1)continue;
            if(slot<0||slot>=36||++required[slot]>counts[slot])return null;
        }
        return required;
    }
}
