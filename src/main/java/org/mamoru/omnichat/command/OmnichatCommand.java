package org.mamoru.omnichat.command;

import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.minecraft.server.command.CommandManager;
import net.minecraft.text.Text;
import org.mamoru.omnichat.server.ServerNetworkHandler;

import java.util.function.Supplier;

/** {@code /omnichat reload}: rescans the server's models directory without a restart (ops only). */
public final class OmnichatCommand {
    private OmnichatCommand() {}

    /** Call ONCE from onInitialize; the command delegates to the current per-server handler. */
    public static void register(Supplier<ServerNetworkHandler> current) {
        CommandRegistrationCallback.EVENT.register((dispatcher, registryAccess, environment) ->
                dispatcher.register(CommandManager.literal("omnichat")
                        .requires(CommandManager.requirePermissionLevel(CommandManager.GAMEMASTERS_CHECK))
                        .then(CommandManager.literal("reload").executes(ctx -> {
                            ServerNetworkHandler handler = current.get();
                            if (handler == null) {
                                ctx.getSource().sendError(Text.literal("OmniChat server is not running"));
                                return 0;
                            }
                            int count = handler.reloadModels();
                            ctx.getSource().sendFeedback(
                                    () -> Text.literal("OmniChat: reloaded " + count + " model(s)"), true);
                            return count;
                        }))));
    }
}
