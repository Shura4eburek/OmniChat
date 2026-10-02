package org.mamoru.omnichat.client.network;

import net.fabricmc.fabric.api.client.networking.v1.C2SPlayChannelEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.fabricmc.fabric.api.networking.v1.PacketSender;
import net.minecraft.client.MinecraftClient;
import net.minecraft.network.packet.CustomPayload;
import net.minecraft.text.Text;
import net.minecraft.util.Formatting;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.chat.ChatBubbleManager;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.network.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

public class ClientNetworkHandler {
    private static final Logger LOGGER = LoggerFactory.getLogger("OmniChat");

    /** Handshake state with the current server; OmniChat payloads flow only when COMPATIBLE. */
    private enum ServerProtocol { NONE, PENDING, COMPATIBLE, INCOMPATIBLE }

    private static volatile ServerProtocol serverProtocol = ServerProtocol.NONE;
    private static volatile boolean joined;

    public static void registerHandlers() {
        ClientPlayNetworking.registerGlobalReceiver(ProtocolVersionPayload.ID, ClientNetworkHandler::onProtocolVersion);
        receive(ModelListS2CPayload.ID, ClientNetworkHandler::onModelList);
        receive(VoiceInfoS2CPayload.ID, ClientNetworkHandler::onVoiceInfo);
        receive(VoiceMapS2CPayload.ID, ClientNetworkHandler::onVoiceMap);
        receive(ModelFileChunkS2CPayload.ID, ClientNetworkHandler::onModelFileChunk);
        receive(ModelDownloadStatusS2CPayload.ID,
                (payload, context) -> ModelDownloadManager.getInstance().onStatusReceived(payload));
        receive(TypingIndicatorS2CPayload.ID, ClientNetworkHandler::onTypingIndicator);
        receive(VoiceRemoveS2CPayload.ID, ClientNetworkHandler::onVoiceRemove);

        // INIT runs before the server's channels are known, so every connection starts clean
        ClientPlayConnectionEvents.INIT.register((handler, client) -> {
            serverProtocol = ServerProtocol.NONE;
            joined = false;
        });
        ClientPlayConnectionEvents.JOIN.register((handler, sender, client) -> onJoin(sender));
        // Fallback in case the server announces its channels after JOIN. It also fires during the
        // configuration phase, where a play payload can't be encoded (disconnects) — JOIN covers that case
        C2SPlayChannelEvents.REGISTER.register((handler, sender, client, channels) -> {
            if (joined && serverProtocol == ServerProtocol.NONE && channels.contains(ProtocolVersionPayload.ID.id())) {
                sendHandshake(sender);
            }
        });
        ClientPlayConnectionEvents.DISCONNECT.register((handler, client) -> {
            serverProtocol = ServerProtocol.NONE;
            joined = false;
        });
        LOGGER.info("Client network handlers registered");
    }

    /** True when OmniChat may send {@code id} to the current server (handshake passed, channel known). */
    public static boolean canSend(CustomPayload.Id<?> id) {
        return serverProtocol == ServerProtocol.COMPATIBLE && ClientPlayNetworking.canSend(id);
    }

    /** Registers a receiver that drops payloads unless the handshake succeeded. */
    private static <T extends CustomPayload> void receive(CustomPayload.Id<T> id,
                                                          ClientPlayNetworking.PlayPayloadHandler<T> handler) {
        ClientPlayNetworking.registerGlobalReceiver(id, (payload, context) -> {
            if (serverProtocol == ServerProtocol.COMPATIBLE) handler.receive(payload, context);
        });
    }

    private static void onJoin(PacketSender sender) {
        joined = true;
        if (ClientPlayNetworking.canSend(ProtocolVersionPayload.ID)) {
            sendHandshake(sender);
        } else if (ClientPlayNetworking.canSend(VoiceSelectionC2SPayload.ID)) {
            // OmniChat channels without the handshake: a server from before protocol versioning
            markIncompatible("server runs an older OmniChat without protocol versioning");
        }
        // Neither: the server has no OmniChat; local TTS of chat keeps working
    }

    private static void sendHandshake(PacketSender sender) {
        serverProtocol = ServerProtocol.PENDING;
        sender.sendPacket(new ProtocolVersionPayload(ProtocolVersionPayload.PROTOCOL_VERSION));
    }

    private static void onProtocolVersion(ProtocolVersionPayload payload, ClientPlayNetworking.Context context) {
        if (payload.version() == ProtocolVersionPayload.PROTOCOL_VERSION) {
            serverProtocol = ServerProtocol.COMPATIBLE;
            LOGGER.info("Server OmniChat protocol {} matches", payload.version());
        } else if (serverProtocol != ServerProtocol.INCOMPATIBLE) {
            markIncompatible("server protocol " + payload.version() + ", client protocol "
                    + ProtocolVersionPayload.PROTOCOL_VERSION);
        }
    }

    private static void markIncompatible(String reason) {
        serverProtocol = ServerProtocol.INCOMPATIBLE;
        LOGGER.warn("OmniChat version mismatch with this server ({}): voice sync, model downloads and "
                + "typing indicators are disabled", reason);
        MinecraftClient client = MinecraftClient.getInstance();
        if (client.player != null) {
            client.player.sendMessage(Text.literal("[OmniChat] This server runs a different OmniChat version; "
                    + "voice sync and model downloads are disabled here.").formatted(Formatting.YELLOW), false);
        }
    }

    private static void onModelList(ModelListS2CPayload payload, ClientPlayNetworking.Context context) {
        VoiceCache.getInstance().setServerModels(payload.models());
        LOGGER.info("Received server model list: {}", payload.models());
        syncVoiceSelection(payload.models());
    }

    /** Tells the server which voice this client has configured, so others hear the right one. */
    private static void syncVoiceSelection(List<String> serverModels) {
        OmnichatConfig config = OmnichatClient.getConfig();
        String model = config.getModelPath();
        if (!serverModels.contains(model) || !canSend(VoiceSelectionC2SPayload.ID)) {
            return;
        }
        ClientPlayNetworking.send(new VoiceSelectionC2SPayload(model, config.getSpeakerId()));
        LOGGER.info("Sent configured voice to server: {} (speaker {})", model, config.getSpeakerId());
    }

    private static void onVoiceInfo(VoiceInfoS2CPayload payload, ClientPlayNetworking.Context context) {
        VoiceCache.getInstance().setVoice(payload.playerUuid(),
                new VoiceChoice(payload.modelName(), payload.speakerId()));
        LOGGER.debug("Voice update: {} -> {} (speaker {})",
                payload.playerUuid(), payload.modelName(), payload.speakerId());
    }

    private static void onVoiceMap(VoiceMapS2CPayload payload, ClientPlayNetworking.Context context) {
        VoiceCache.getInstance().setVoiceMap(payload.voices());
        LOGGER.info("Received voice map with {} entries", payload.voices().size());
    }

    private static void onModelFileChunk(ModelFileChunkS2CPayload payload, ClientPlayNetworking.Context context) {
        ModelDownloadManager.getInstance().onChunkReceived(payload);
    }

    private static void onTypingIndicator(TypingIndicatorS2CPayload payload, ClientPlayNetworking.Context context) {
        ChatBubbleManager.getInstance().setTyping(payload.playerUuid(), payload.typing());
    }

    private static void onVoiceRemove(VoiceRemoveS2CPayload payload, ClientPlayNetworking.Context context) {
        VoiceCache.getInstance().removeVoice(payload.playerUuid());
        LOGGER.debug("Voice removed: {}", payload.playerUuid());
    }
}
