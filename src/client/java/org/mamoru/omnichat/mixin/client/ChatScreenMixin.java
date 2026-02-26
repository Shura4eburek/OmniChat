package org.mamoru.omnichat.mixin.client;

import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.minecraft.client.gui.screen.ChatScreen;
import org.mamoru.omnichat.network.TypingIndicatorC2SPayload;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(ChatScreen.class)
public class ChatScreenMixin {
    @Inject(method = "init", at = @At("TAIL"))
    private void onInit(CallbackInfo ci) {
        try {
            ClientPlayNetworking.send(new TypingIndicatorC2SPayload(true));
        } catch (Exception ignored) {
        }
    }

    @Inject(method = "removed", at = @At("HEAD"))
    private void onRemoved(CallbackInfo ci) {
        try {
            ClientPlayNetworking.send(new TypingIndicatorC2SPayload(false));
        } catch (Exception ignored) {
        }
    }
}
