package gl.syn.minecraft;

import com.google.gson.JsonObject;
import java.lang.reflect.InvocationTargetException;
import java.util.Optional;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.inventory.AbstractContainerMenu;
import net.minecraft.world.inventory.Slot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Block;

/** Optional-mod native menus, identified only after the mod itself authorizes and opens them. */
final class ReviewedModMenus {
    private static final String CORE="net.p3pp3rf1y.sophisticatedcore.common.gui.";
    private static final String STORAGE="net.p3pp3rf1y.sophisticatedstorage.";
    private static final String BACKPACK="net.p3pp3rf1y.sophisticatedbackpacks.";
    private static final String FARMER="vectorwing.farmersdelight.common.block.entity.container.";
    private static final String CORPSE="de.maxhenkel.corpse.gui.";

    static boolean blockCandidate(Block block) {
        return inherits(block,STORAGE+"block.ChestBlock")||inherits(block,STORAGE+"block.BarrelBlock")
            ||inherits(block,STORAGE+"block.ShulkerBoxBlock")||inherits(block,STORAGE+"block.LimitedBarrelBlock")
            ||inherits(block,BACKPACK+"backpack.BackpackBlock")
            ||inherits(block,"vectorwing.farmersdelight.common.block.CookingPotBlock");
    }
    private static boolean inherits(Object value,String name) {
        for(Class<?> type=value.getClass();type!=null;type=type.getSuperclass())if(type.getName().equals(name))return true;
        return false;
    }
    static boolean storage(AbstractContainerMenu menu){return inherits(menu,STORAGE+"common.gui.StorageContainerMenu");}
    static boolean backpack(AbstractContainerMenu menu){return menu.getClass().getName().equals(BACKPACK+"common.gui.BackpackContainer");}
    static boolean pot(AbstractContainerMenu menu){return menu.getClass().getName().equals(FARMER+"CookingPotMenu");}
    static boolean corpse(AbstractContainerMenu menu){return menu.getClass().getName().equals(CORPSE+"CorpseInventoryContainer")
        ||menu.getClass().getName().equals(CORPSE+"CorpseAdditionalContainer");}
    static boolean blockMenu(AbstractContainerMenu menu){return storage(menu)||backpack(menu)||pot(menu);}
    static boolean portableItem(ItemStack item){return inherits(item.getItem(),BACKPACK+"backpack.BackpackItem");}

    // Reflection keeps optional mods optional; these exact public APIs are pinned by pack.lock.
    private static Object call(Object value,String method) {
        try{return value.getClass().getMethod(method).invoke(value);}
        catch(InvocationTargetException ex){throw new IllegalStateException("native_menu_hook_failed",ex.getCause());}
        catch(ReflectiveOperationException ex){throw new IllegalStateException("native_menu_api_changed",ex);}
    }
    static void validatePolicy(AbstractContainerMenu menu,JsonObject area) {
        if((storage(menu)||backpack(menu))&&area!=null
            &&((Optional<?>)call(menu,"getLinkedStorageGroupId")).isPresent())
            throw new NativeActionException("linked_storage_area_not_supported");
        // History copies are never an inventory source. The real mod must grant edit access.
        if(corpse(menu)&&((Boolean)call(menu,"isHistory")||!(Boolean)call(menu,"isEditable")))
            throw new NativeActionException("native_menu_read_only");
    }
    static void validateBlock(AbstractContainerMenu menu,BlockPos position,JsonObject area) {
        validatePolicy(menu,area);
        if(storage(menu)||backpack(menu)) {
            Optional<?> actual=(Optional<?>)call(menu,"getBlockPosition");
            if(actual.isEmpty()||!position.equals(actual.get()))throw new NativeActionException("container_binding_changed");
        }
    }
    static void validateItem(AbstractContainerMenu menu,JsonObject area) {
        if(!backpack(menu))throw new NativeActionException("unsupported_item_container");
        validatePolicy(menu,area);
        if(((Optional<?>)call(menu,"getBlockPosition")).isPresent()||((Optional<?>)call(menu,"getEntity")).isPresent())
            throw new NativeActionException("container_binding_changed");
    }
    static void validateEntity(AbstractContainerMenu menu,Entity target,JsonObject area) {
        if(!corpse(menu))throw new NativeActionException("unsupported_entity_container");
        validatePolicy(menu,area);
        if(call(menu,"getCorpse")!=target)throw new NativeActionException("container_binding_changed");
    }
    static boolean transferable(AbstractContainerMenu menu,Slot slot,boolean playerSlot) {
        if(playerSlot)return true;
        if(storage(menu)||backpack(menu)) {
            // Upgrade recipe/configuration/ghost slots have separate click semantics.
            // Actual storage slots retain native filter/capacity/upgrade-response hooks.
            return inherits(slot,CORE+"StorageInventorySlot");
        }
        return true;
    }
    static String role(AbstractContainerMenu menu,Slot slot) {
        if(pot(menu))return switch(slot.getContainerSlot()){case 6->"meal_preview";case 7->"serving_container";case 8->"output";default->"ingredient";};
        if(storage(menu)||backpack(menu))return inherits(slot,CORE+"StorageInventorySlot")?"storage":"upgrade_or_configuration";
        if(corpse(menu))return "recovery";
        return "storage";
    }
}
