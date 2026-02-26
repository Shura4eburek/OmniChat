package org.mamoru.omnichat.client.network;

import org.mamoru.omnichat.network.VoiceChoice;

import java.util.*;

public class VoiceCache {
    private static final VoiceCache INSTANCE = new VoiceCache();

    private List<String> serverModels = Collections.emptyList();
    private final Map<UUID, VoiceChoice> voiceMap = new HashMap<>();
    private boolean connectedToOmnichatServer = false;

    private VoiceCache() {}

    public static VoiceCache getInstance() {
        return INSTANCE;
    }

    public void setServerModels(List<String> models) {
        this.serverModels = List.copyOf(models);
        this.connectedToOmnichatServer = true;
    }

    public List<String> getServerModels() {
        return serverModels;
    }

    public void setVoiceMap(Map<UUID, VoiceChoice> voices) {
        voiceMap.clear();
        voiceMap.putAll(voices);
    }

    public void setVoice(UUID playerUuid, VoiceChoice choice) {
        voiceMap.put(playerUuid, choice);
    }

    public VoiceChoice getVoice(UUID playerUuid) {
        return voiceMap.get(playerUuid);
    }

    public boolean isConnectedToOmnichatServer() {
        return connectedToOmnichatServer;
    }

    public void clear() {
        serverModels = Collections.emptyList();
        voiceMap.clear();
        connectedToOmnichatServer = false;
    }
}
