package gl.syn.minecraft.mixin;

import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerPlayerGameMode;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/** Only the native block-breaking state needed for truthful completion and hard cancellation. */
@Mixin(ServerPlayerGameMode.class)
public interface ServerPlayerGameModeAccessor {
    @Accessor("gameTicks") int scru$gameTicks();
    @Accessor("destroyProgressStart") int scru$destroyProgressStart();
    @Accessor("destroyPos") BlockPos scru$destroyPos();
    @Accessor("isDestroyingBlock") boolean scru$isDestroyingBlock();
    @Accessor("isDestroyingBlock") void scru$setDestroyingBlock(boolean active);
    @Accessor("hasDelayedDestroy") boolean scru$hasDelayedDestroy();
    @Accessor("hasDelayedDestroy") void scru$setDelayedDestroy(boolean active);
    @Accessor("lastSentState") void scru$setLastSentState(int state);
}
