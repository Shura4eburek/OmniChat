package org.mamoru.omnichat.client.screen;

import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.tooltip.Tooltip;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.client.gui.widget.CyclingButtonWidget;
import net.minecraft.client.gui.widget.SliderWidget;
import net.minecraft.screen.ScreenTexts;
import net.minecraft.text.Text;
import net.minecraft.util.math.MathHelper;
import org.mamoru.omnichat.client.OmnichatClient;
import org.mamoru.omnichat.client.config.OmnichatConfig;
import org.mamoru.omnichat.client.network.ModelDownloadManager;
import org.mamoru.omnichat.client.network.VoiceCache;
import org.mamoru.omnichat.client.tts.SpeakerCounts;
import org.mamoru.omnichat.network.VoiceSelectionC2SPayload;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class OmnichatSettingsScreen extends Screen {
    private final Screen parent;

    private boolean enabled;
    private boolean readOwnMessages;
    private String selectedModel;
    private int speakerId;
    // Set when the speaker selector has to appear/disappear (model changed or its count loaded)
    private volatile boolean needsReinit;
    private boolean robotEffect;
    private float speed;
    private float volume;
    private boolean showChatBubbles;
    private float bubbleTextSpeed;

    private List<String> availableModels;
    private ButtonWidget applyButton;
    private final boolean connectedToServer;

    public OmnichatSettingsScreen(Screen parent) {
        super(Text.literal("OmniChat Settings"));
        this.parent = parent;

        OmnichatConfig config = OmnichatClient.getConfig();
        this.enabled = config.isEnabled();
        this.readOwnMessages = config.isReadOwnMessages();
        this.selectedModel = config.getModelPath();
        this.speakerId = config.getSpeakerId();
        this.robotEffect = config.isRobotEffect();
        this.speed = config.getSpeed();
        this.volume = config.getVolume();
        this.showChatBubbles = config.isShowChatBubbles();
        this.bubbleTextSpeed = config.getBubbleTextSpeed();

        VoiceCache cache = VoiceCache.getInstance();
        this.connectedToServer = cache.isConnectedToOmnichatServer();

        // Union of server and local models; the configured model is kept even if it's missing
        Set<String> models = new LinkedHashSet<>();
        if (connectedToServer) {
            models.addAll(cache.getServerModels());
        }
        models.addAll(OmnichatConfig.listAvailableModels());
        if (selectedModel != null && !selectedModel.isEmpty()) {
            models.add(selectedModel);
        }
        this.availableModels = new ArrayList<>(models);
    }

    private boolean isModelLocal(String modelName) {
        Path dir = OmnichatConfig.resolveModelDir(modelName);
        return dir != null && Files.isDirectory(dir);
    }

    private String modelDisplayName(String modelName) {
        if (!isModelLocal(modelName)) {
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
            // Speaker selector only for local multi-speaker models (hidden for GLaDOS/single-speaker)
            int speakers = SpeakerCounts.get(initialModel, () -> needsReinit = true);
            boolean multiSpeaker = speakers > 1;
            int modelWidth = multiSpeaker ? widgetWidth - 84 : widgetWidth;
            this.addDrawableChild(CyclingButtonWidget.<String>builder(
                            value -> Text.literal("Voice: " + modelDisplayName(value)), initialModel)
                    .values(availableModels)
                    .build(centerX - widgetWidth / 2, startY + 52, modelWidth, 20,
                            Text.literal("Voice Model"),
                            (button, value) -> {
                                selectedModel = value;
                                // Speaker ids are per model: keep the saved one only for the saved model
                                speakerId = isModelChanged() ? 0 : OmnichatClient.getConfig().getSpeakerId();
                                needsReinit = true;
                                updateApplyButton();
                            }));

            if (multiSpeaker) {
                int maxId = speakers - 1;
                speakerId = MathHelper.clamp(speakerId, 0, maxId);
                SliderWidget speakerSlider = new SliderWidget(
                        centerX - widgetWidth / 2 + modelWidth + 4, startY + 52, 80, 20,
                        Text.literal("Speaker: " + speakerId), (double) speakerId / maxId) {
                    @Override
                    protected void updateMessage() {
                        this.setMessage(Text.literal("Speaker: " + (int) Math.round(this.value * maxId)));
                    }

                    @Override
                    protected void applyValue() {
                        speakerId = (int) Math.round(this.value * maxId);
                    }
                };
                speakerSlider.setTooltip(Tooltip.of(Text.literal("Speaker of this model (0-" + maxId + ")")));
                this.addDrawableChild(speakerSlider);
            }
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
                MathHelper.clamp((speed - 0.5) / 1.5, 0.0, 1.0)) {
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
                MathHelper.clamp(volume / 2.0, 0.0, 1.0)) {
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
                MathHelper.clamp(bubbleTextSpeed / 100.0, 0.0, 1.0)) {
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
        this.applyButton = this.addDrawableChild(ButtonWidget.builder(Text.literal("Apply"), button -> {
            OmnichatConfig config = OmnichatClient.getConfig();
            config.setEnabled(enabled);
            config.setReadOwnMessages(readOwnMessages);
            // Only touch the model when the user actually picked another one
            if (isModelChanged()) {
                config.setModelPath(selectedModel);
            }
            config.setSpeakerId(speakerId);
            config.setRobotEffect(robotEffect);
            config.setSpeed(speed);
            config.setVolume(volume);
            config.setShowChatBubbles(showChatBubbles);
            config.setBubbleTextSpeed(bubbleTextSpeed);
            config.save();
            // Rebuilds the engine (off-thread) only if the model or enabled state changed
            OmnichatClient.getTts().applySettings();

            if (connectedToServer && ClientPlayNetworking.canSend(VoiceSelectionC2SPayload.ID)) {
                ClientPlayNetworking.send(new VoiceSelectionC2SPayload(config.getModelPath(), config.getSpeakerId()));
            }

            close();
        }).dimensions(centerX - widgetWidth / 2, buttonY, 96, 20).build());
        updateApplyButton();

        // Cancel button
        this.addDrawableChild(ButtonWidget.builder(ScreenTexts.CANCEL, button -> close())
                .dimensions(centerX - widgetWidth / 2 + 104, buttonY, 96, 20).build());
    }

    @Override
    public void tick() {
        super.tick();
        if (needsReinit) {
            needsReinit = false;
            clearAndInit(); // all widget state lives in fields, so rebuilding keeps it
        }
    }

    private boolean isModelChanged() {
        return selectedModel != null && !selectedModel.equals(OmnichatClient.getConfig().getModelPath());
    }

    /** A model that isn't downloaded can't become the local engine; download it first. */
    private void updateApplyButton() {
        if (applyButton == null) return;
        boolean blocked = isModelChanged() && !isModelLocal(selectedModel);
        applyButton.active = !blocked;
        applyButton.setTooltip(blocked ? Tooltip.of(Text.literal("Download this model before applying it")) : null);
    }

    @Override
    public void close() {
        this.client.setScreen(parent);
    }
}
