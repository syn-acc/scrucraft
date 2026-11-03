package gl.syn.minecraft.mixin;

import gl.syn.minecraft.AgentPlayer;

import com.mojang.authlib.GameProfile;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ClientInformation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.players.PlayerList;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

/** Persistent Syn players keep ordinary respawn and earned advancement lifecycles. */
@Mixin(PlayerList.class)
public abstract class PlayerListMixin {
    // NeoForge's ephemeral FakePlayerAdvancements intentionally disables all criteria.
    // These persistent registered players need the normal UUID-keyed lifecycle;
    // preserve their fake-player classification for every other caller.
    @Redirect(method="getPlayerAdvancements",at=@At(value="INVOKE",target="Lnet/minecraft/server/level/ServerPlayer;isFakePlayer()Z"),require=1,expect=1,allow=1)
    private boolean syn$normalAgentAdvancements(ServerPlayer player) {
        return !(player instanceof AgentPlayer)&&player.isFakePlayer();
    }

    @Redirect(method="respawn",at=@At(value="NEW",target="net/minecraft/server/level/ServerPlayer"))
    private ServerPlayer syn$respawnAgent(MinecraftServer server,ServerLevel level,GameProfile profile,ClientInformation information,ServerPlayer old,boolean keepInventory,Entity.RemovalReason reason) {
        return old instanceof AgentPlayer a ? new AgentPlayer(level,profile.getName(),a.job) : new ServerPlayer(server,level,profile,information);
    }
}
