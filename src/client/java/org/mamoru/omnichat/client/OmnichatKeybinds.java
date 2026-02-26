package org.mamoru.omnichat.client;

import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.minecraft.client.option.KeyBinding;
import net.minecraft.client.util.InputUtil;
import net.minecraft.util.Identifier;
import org.lwjgl.glfw.GLFW;
import org.mamoru.omnichat.client.screen.OmnichatSettingsScreen;

public class OmnichatKeybinds {
    private static final KeyBinding.Category OMNICHAT_CATEGORY =
            KeyBinding.Category.create(Identifier.of("omnichat", "settings"));

    private static KeyBinding settingsKey;

    public static void register() {
        settingsKey = KeyBindingHelper.registerKeyBinding(new KeyBinding(
                "key.omnichat.settings",
                InputUtil.Type.KEYSYM,
                GLFW.GLFW_KEY_O,
                OMNICHAT_CATEGORY
        ));

        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            while (settingsKey.wasPressed()) {
                client.setScreen(new OmnichatSettingsScreen(null));
            }
        });
    }
}
