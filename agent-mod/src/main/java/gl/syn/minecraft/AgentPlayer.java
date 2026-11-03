package gl.syn.minecraft;

import com.mojang.authlib.GameProfile;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.util.UUID;
import net.minecraft.network.Connection;
import net.minecraft.network.PacketListener;
import net.minecraft.network.ProtocolInfo;
import net.minecraft.network.PacketSendListener;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.Packet;
import net.minecraft.network.protocol.PacketFlow;
import net.minecraft.server.level.ClientInformation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.network.CommonListenerCookie;
import net.minecraft.server.network.ServerGamePacketListenerImpl;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.portal.DimensionTransition;

/** A full survival ServerPlayer. Only client networking is replaced. */
public final class AgentPlayer extends ServerPlayer {
    public String job;
    public final PrimitiveControl controls;
    BodyStream stream;
    long terrainDue;
    String terrainDimension="";
    public AgentPlayer(ServerLevel level, String name, String job) {
        super(level.getServer(), level, new GameProfile(UUID.nameUUIDFromBytes(("syn-agent:"+name).getBytes(java.nio.charset.StandardCharsets.UTF_8)),name),ClientInformation.createDefault());
        this.job=job;
        controls=new PrimitiveControl(this);
        connection=new LocalListener(this,new LocalConnection());
        setGameMode(GameType.SURVIVAL);
    }
    public void attachListener(LocalConnection c) { connection=new LocalListener(this,c); }
    @Override public boolean isFakePlayer() { return true; }
    @Override public Entity changeDimension(DimensionTransition transition) {
        Entity result=super.changeDimension(transition);
        // A real client acknowledges the teleport after the native transition.
        // This local body has no client packet; leaving that flag set makes
        // ServerPlayer immune to all damage, including genericKill, indefinitely.
        if(result==this&&!isRemoved()&&serverLevel()==transition.newLevel())hasChangedDimension();
        return result;
    }
    @Override public void tick() {
        // Disarm old-world native breaking before ServerPlayer advances its game mode.
        if(controls!=null)controls.beforeNativeTick();
        super.tick();
        // Network listeners normally drive the full Player tick. There is no
        // remote client for these agents, so drive it here exactly once.
        if (!isRemoved()) super.doTick();
    }
    public static final class LocalConnection extends Connection {
        public LocalConnection() { super(PacketFlow.SERVERBOUND); new io.netty.channel.embedded.EmbeddedChannel(this); }
        @Override public void setListenerForServerboundHandshake(PacketListener listener) {}
        @Override public <T extends PacketListener> void setupInboundProtocol(ProtocolInfo<T> protocol, T listener) {
            if(listener instanceof ServerGamePacketListenerImpl handler && handler.player instanceof AgentPlayer agent) agent.attachListener(this);
        }
        @Override public boolean isConnected() { return true; }
        @Override public SocketAddress getRemoteAddress() { return new InetSocketAddress("127.0.0.1",0); }
        @Override public boolean isMemoryConnection() { return true; }
        @Override public void send(Packet<?> p) {}
        @Override public void send(Packet<?> p, PacketSendListener l) {}
        @Override public void send(Packet<?> p, PacketSendListener l, boolean flush) {}
    }
    private static final class LocalListener extends ServerGamePacketListenerImpl {
        LocalListener(AgentPlayer player, Connection c) {
            super(player.server,c,player,CommonListenerCookie.createInitial(player.getGameProfile(),false));
        }
        @Override public void tick() {}
        @Override public void send(Packet<?> p) {}
        @Override public void send(Packet<?> p, PacketSendListener l) {}
        @Override public void disconnect(Component message) {}
        @Override public void resetPosition() {}
    }
}
