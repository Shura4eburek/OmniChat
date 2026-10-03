package org.mamoru.omnichat.client.network;

import org.mamoru.omnichat.network.VoiceChoice;
import org.mamoru.omnichat.voice.VoiceMeta;

import java.util.*;

public class VoiceCache {
    private static final VoiceCache INSTANCE = new VoiceCache();

    private volatile List<VoiceMeta> catalog = List.of();
    private final Map<UUID, VoiceChoice> voiceMap = new HashMap<>();

    private VoiceCache() {}

    public static VoiceCache getInstance() {
        return INSTANCE;
    }

    public void setCatalog(List<VoiceMeta> voices) {
        this.catalog = List.copyOf(voices);
    }

    public List<VoiceMeta> getCatalog() {
        return catalog;
    }

    public List<String> getServerModels() {
        return catalog.stream().map(VoiceMeta::model).toList();
    }

    public void setVoiceMap(Map<UUID, VoiceChoice> voices) {
        voiceMap.clear();
        voiceMap.putAll(voices);
    }

    public void setVoice(UUID playerUuid, VoiceChoice choice) {
        voiceMap.put(playerUuid, choice);
    }

    public void removeVoice(UUID playerUuid) {
        voiceMap.remove(playerUuid);
    }

    public VoiceChoice getVoice(UUID playerUuid) {
        return voiceMap.get(playerUuid);
    }

    public boolean isConnectedToOmnichatServer() {
        return !catalog.isEmpty();
    }

    public void clear() {
        catalog = List.of();
        voiceMap.clear();
    }
}
