package org.mamoru.omnichat.mixin.client;

import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.ChatScreen;
import net.minecraft.client.gui.widget.TextFieldWidget;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.network.TypingIndicatorC2SPayload;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Drives the typing indicator from what the player actually does in the chat field:
 * "typing" means non-empty, non-command text edited within the last few seconds.
 * Only state changes are sent; merely opening the chat (or the bed chat) sends nothing.
 */
@Mixin(ChatScreen.class)
public class ChatScreenMixin {
    /** Stop showing "..." after this long without an edit, even if text remains. */
    @Unique
    private static final long OMNICHAT_TYPING_IDLE_MS = 5000;

    @Shadow
    protected TextFieldWidget chatField;

    @Unique
    private boolean omnichat$typingSent;
    @Unique
    private long omnichat$lastEditMs;

    @Inject(method = "onChatFieldUpdate", at = @At("HEAD"))
    private void omnichat$onChatFieldUpdate(String text, CallbackInfo ci) {
        omnichat$lastEditMs = System.currentTimeMillis();
        omnichat$updateTyping();
    }

    // Per-frame check so the idle timeout fires without further input
    @Inject(method = "render", at = @At("TAIL"))
    private void omnichat$onRender(DrawContext context, int mouseX, int mouseY, float deltaTicks, CallbackInfo ci) {
        omnichat$updateTyping();
    }

    @Inject(method = "removed", at = @At("HEAD"))
    private void omnichat$onRemoved(CallbackInfo ci) {
        omnichat$send(false);
    }

    @Unique
    private void omnichat$updateTyping() {
        omnichat$send(omnichat$isTyping());
    }

    @Unique
    private boolean omnichat$isTyping() {
        if (!OmnichatClient.getConfig().isSendTypingIndicator() || chatField == null) return false;
        String text = chatField.getText().trim();
        if (text.isEmpty() || text.startsWith("/")) return false; // commands don't produce a chat bubble
        return System.currentTimeMillis() - omnichat$lastEditMs < OMNICHAT_TYPING_IDLE_MS;
    }

    @Unique
    private void omnichat$send(boolean typing) {
        if (typing == omnichat$typingSent) return;
        omnichat$typingSent = typing;
        try {
            if (ClientPlayNetworking.canSend(TypingIndicatorC2SPayload.ID)) {
                ClientPlayNetworking.send(new TypingIndicatorC2SPayload(typing));
            }
        } catch (Exception ignored) {
            // not connected
        }
    }
}
