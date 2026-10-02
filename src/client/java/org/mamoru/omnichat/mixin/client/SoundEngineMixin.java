package org.mamoru.omnichat.mixin.client;

import net.minecraft.client.sound.SoundEngine;
import org.mamoru.omnichat.client.tts.SpatialAudioPlayer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * {@code SoundEngine.close()} destroys the AL context and device; it runs from
 * {@code SoundSystem.stop()} (reloadSounds / F3+T, audio-device change) and {@code stopAbruptly()}.
 * Free OmniChat's raw AL sources first, while the context is still current.
 */
@Mixin(SoundEngine.class)
public abstract class SoundEngineMixin {
    @Inject(method = "close", at = @At("HEAD"))
    private void omnichat$releaseTtsSources(CallbackInfo ci) {
        SpatialAudioPlayer.onSoundEngineClosing();
    }
}
