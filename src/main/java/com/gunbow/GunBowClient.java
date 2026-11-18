package com.gunbow;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.resources.Identifier;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.item.Items;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class GunBowClient implements ClientModInitializer {
    public static final Logger LOGGER = LoggerFactory.getLogger("gunbow");

    private static final KeyMapping.Category CATEGORY =
            KeyMapping.Category.register(Identifier.fromNamespaceAndPath("gunbow", "main"));

    private static KeyMapping menuKey;
    private static KeyMapping reloadKey;

    // bow-release detection (client only, so it works on any server)
    private boolean wasDrawing;
    private int drawTicks;
    private int cycleDelay = -1;   // pump / bolt sound after a shot

    @Override
    public void onInitializeClient() {
        GunState.load();

        menuKey = KeyMappingHelper.registerKeyMapping(new KeyMapping("key.gunbow.menu", 71 /* G */, CATEGORY));
        reloadKey = KeyMappingHelper.registerKeyMapping(new KeyMapping("key.gunbow.reload", 82 /* R */, CATEGORY));

        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            while (menuKey.consumeClick()) {
                if (client.gui.screen() == null) client.gui.setScreen(new GunMenuScreen());
            }
            while (reloadKey.consumeClick()) {
                if (GunState.selected() != null) play(client, "reload." + GunState.selected().id());
            }
            if (cycleDelay > 0 && --cycleDelay == 0 && GunState.selected() != null) {
                play(client, "reload." + GunState.selected().id());   // pump / bolt clip
            }
            tickShot(client);
        });
    }

    private static void play(Minecraft client, String event) {
        LocalPlayer p = client.player;
        if (p == null || client.level == null) return;
        SoundEvent ev = SoundEvent.createVariableRangeEvent(Identifier.fromNamespaceAndPath("gunbow", event));
        client.level.playLocalSound(p.getX(), p.getY(), p.getZ(), ev, SoundSource.PLAYERS, 1.0F, 1.0F, false);
    }

    private void tickShot(Minecraft client) {
        LocalPlayer p = client.player;
        if (p == null || client.level == null) { wasDrawing = false; return; }
        boolean drawing = p.isUsingItem() && p.getUseItem().is(Items.BOW);
        if (drawing) {
            drawTicks++;
        } else if (wasDrawing) {
            boolean holdingBow = p.getMainHandItem().is(Items.BOW) || p.getOffhandItem().is(Items.BOW);
            // a bow needs ~3 ticks of draw to actually release an arrow
            Guns.Gun gun = GunState.selected();
            if (holdingBow && drawTicks >= 3 && gun != null) {
                play(client, "shot." + gun.id());
                cycleDelay = gun.cycles() ? 12 : -1;
            }
            drawTicks = 0;
        } else {
            drawTicks = 0;
        }
        wasDrawing = drawing;
    }
}
