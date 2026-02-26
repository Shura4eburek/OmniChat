package org.mamoru.omnichat.client.screen;

import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.client.gui.widget.CyclingButtonWidget;
import net.minecraft.client.gui.widget.SliderWidget;
import net.minecraft.screen.ScreenTexts;
import net.minecraft.text.Text;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.network.ModelDownloadManager;
import org.mamoru.omnichat.client.network.VoiceCache;
import org.mamoru.omnichat.network.VoiceSelectionC2SPayload;

import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;

public class OmnichatSettingsScreen extends Screen {
    private final Screen parent;

    private boolean enabled;
    private boolean readOwnMessages;
    private String selectedModel;
    private boolean robotEffect;
    private float speed;
    private float volume;
    private boolean showChatBubbles;
    private float bubbleTextSpeed;

    private List<String> availableModels;
    private final boolean connectedToServer;

    public OmnichatSettingsScreen(Screen parent) {
        super(Text.literal("OmniChat Settings"));
        this.parent = parent;

        OmnichatConfig config = OmnichatClient.getConfig();
        this.enabled = config.isEnabled();
        this.readOwnMessages = config.isReadOwnMessages();
        this.selectedModel = config.getModelPath();
        this.robotEffect = config.isRobotEffect();
        this.speed = config.getSpeed();
        this.volume = config.getVolume();
        this.showChatBubbles = config.isShowChatBubbles();
        this.bubbleTextSpeed = config.getBubbleTextSpeed();

        VoiceCache cache = VoiceCache.getInstance();
        this.connectedToServer = cache.isConnectedToOmnichatServer();

        // Merge server models with local models
        if (connectedToServer) {
            this.availableModels = new ArrayList<>(cache.getServerModels());
        } else {
            this.availableModels = new ArrayList<>(OmnichatConfig.listAvailableModels());
        }

        if (!availableModels.contains(selectedModel) && !availableModels.isEmpty()) {
            selectedModel = availableModels.get(0);
        }
    }

    private boolean isModelLocal(String modelName) {
        return Files.isDirectory(OmnichatConfig.getModelsDir().resolve(modelName));
    }

    private String modelDisplayName(String modelName) {
        if (connectedToServer && !isModelLocal(modelName)) {
            return modelName + " [↓]";
        }
        return modelName;
    }

    @Override
    protected void init() {
        int centerX = this.width / 2;
        int startY = this.height / 6;
        int widgetWidth = 200;

        // Enabled toggle
        this.addDrawableChild(CyclingButtonWidget.onOffBuilder(
                        ScreenTexts.ON, ScreenTexts.OFF, enabled)
                .build(centerX - widgetWidth / 2, startY, widgetWidth, 20,
                        Text.literal("TTS Enabled"),
                        (button, value) -> enabled = value));

        // Read own messages toggle
        this.addDrawableChild(CyclingButtonWidget.onOffBuilder(
                        ScreenTexts.ON, ScreenTexts.OFF, readOwnMessages)
                .build(centerX - widgetWidth / 2, startY + 26, widgetWidth, 20,
                        Text.literal("Read Own Messages"),
                        (button, value) -> readOwnMessages = value));

        // Voice model selector
        if (!availableModels.isEmpty()) {
            int initialIndex = Math.max(0, availableModels.indexOf(selectedModel));
            String initialModel = availableModels.get(initialIndex);
            this.addDrawableChild(CyclingButtonWidget.<String>builder(
                            value -> Text.literal("Voice: " + modelDisplayName(value)), initialModel)
                    .values(availableModels)
                    .build(centerX - widgetWidth / 2, startY + 52, widgetWidth, 20,
                            Text.literal("Voice Model"),
                            (button, value) -> selectedModel = value));
        }

        // Robot Effect toggle
        this.addDrawableChild(CyclingButtonWidget.onOffBuilder(
                        ScreenTexts.ON, ScreenTexts.OFF, robotEffect)
                .build(centerX - widgetWidth / 2, startY + 78, widgetWidth, 20,
                        Text.literal("Robot Effect"),
                        (button, value) -> robotEffect = value));

        // Speed slider (0.5 - 2.0)
        this.addDrawableChild(new SliderWidget(
                centerX - widgetWidth / 2, startY + 104, widgetWidth, 20,
                Text.literal("Speed: " + String.format("%.1f", speed)),
                (speed - 0.5) / 1.5) {
            @Override
            protected void updateMessage() {
                float val = (float) (this.value * 1.5 + 0.5);
                this.setMessage(Text.literal("Speed: " + String.format("%.1f", val)));
            }

            @Override
            protected void applyValue() {
                speed = (float) (this.value * 1.5 + 0.5);
            }
        });

        // Volume slider (0.0 - 2.0)
        this.addDrawableChild(new SliderWidget(
                centerX - widgetWidth / 2, startY + 130, widgetWidth, 20,
                Text.literal("Volume: " + String.format("%.1f", volume)),
                volume / 2.0) {
            @Override
            protected void updateMessage() {
                float val = (float) (this.value * 2.0);
                this.setMessage(Text.literal("Volume: " + String.format("%.1f", val)));
            }

            @Override
            protected void applyValue() {
                volume = (float) (this.value * 2.0);
            }
        });

        // Chat Bubbles toggle
        this.addDrawableChild(CyclingButtonWidget.onOffBuilder(
                        ScreenTexts.ON, ScreenTexts.OFF, showChatBubbles)
                .build(centerX - widgetWidth / 2, startY + 156, widgetWidth, 20,
                        Text.literal("Chat Bubbles"),
                        (button, value) -> showChatBubbles = value));

        // Bubble Text Speed slider (0 - 100)
        this.addDrawableChild(new SliderWidget(
                centerX - widgetWidth / 2, startY + 182, widgetWidth, 20,
                Text.literal("Bubble Speed: " + (bubbleTextSpeed <= 0 ? "Instant" : String.format("%.0f", bubbleTextSpeed))),
                bubbleTextSpeed / 100.0) {
            @Override
            protected void updateMessage() {
                float val = (float) (this.value * 100.0);
                this.setMessage(Text.literal("Bubble Speed: " + (val <= 0 ? "Instant" : String.format("%.0f", val))));
            }

            @Override
            protected void applyValue() {
                bubbleTextSpeed = (float) (this.value * 100.0);
            }
        });

        int buttonY = startY + 218;

        // Download button (only when connected to server)
        if (connectedToServer) {
            this.addDrawableChild(ButtonWidget.builder(Text.literal("Download"), button -> {
                if (selectedModel != null && !isModelLocal(selectedModel)) {
                    ModelDownloadManager.getInstance().requestDownload(selectedModel);
                    button.setMessage(Text.literal("Downloading..."));
                    button.active = false;
                }
            }).dimensions(centerX - widgetWidth / 2, buttonY, 96, 20).build());

            this.addDrawableChild(ButtonWidget.builder(Text.literal("Download All"), button -> {
                for (String model : availableModels) {
                    if (!isModelLocal(model)) {
                        ModelDownloadManager.getInstance().requestDownload(model);
                    }
                }
                button.setMessage(Text.literal("Downloading..."));
                button.active = false;
            }).dimensions(centerX - widgetWidth / 2 + 104, buttonY, 96, 20).build());

            buttonY += 26;
        }

        // Apply button
        this.addDrawableChild(ButtonWidget.builder(Text.literal("Apply"), button -> {
            OmnichatConfig config = OmnichatClient.getConfig();
            config.setEnabled(enabled);
            config.setReadOwnMessages(readOwnMessages);
            config.setModelPath(selectedModel);
            config.setRobotEffect(robotEffect);
            config.setSpeed(speed);
            config.setVolume(volume);
            config.setShowChatBubbles(showChatBubbles);
            config.setBubbleTextSpeed(bubbleTextSpeed);
            config.save();
            OmnichatClient.reinitializeTts();

            // Send voice selection to server if connected
            if (connectedToServer) {
                try {
                    ClientPlayNetworking.send(new VoiceSelectionC2SPayload(selectedModel, config.getSpeakerId()));
                } catch (Exception e) {
                    // Server might not support it, ignore
                }
            }

            close();
        }).dimensions(centerX - widgetWidth / 2, buttonY, 96, 20).build());

        // Cancel button
        this.addDrawableChild(ButtonWidget.builder(ScreenTexts.CANCEL, button -> close())
                .dimensions(centerX - widgetWidth / 2 + 104, buttonY, 96, 20).build());
    }

    @Override
    public void close() {
        this.client.setScreen(parent);
    }
}
