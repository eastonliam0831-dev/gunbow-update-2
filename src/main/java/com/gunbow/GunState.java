package com.gunbow;

import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/** Client-side selection: which gun the bow currently looks/sounds like. null = vanilla bow. */
public final class GunState {
    private static Guns.Gun selected;
    private static Identifier modelId;
    private static Component name;

    private static Path file() {
        return FabricLoader.getInstance().getConfigDir().resolve("gunbow.txt");
    }

    public static void load() {
        try {
            Path f = file();
            if (Files.exists(f)) set(Guns.byId(Files.readString(f).trim()), false);
        } catch (IOException e) {
            GunBowClient.LOGGER.warn("Could not read gunbow.txt", e);
        }
    }

    public static void set(Guns.Gun gun, boolean save) {
        selected = gun;
        modelId = gun == null ? null : Identifier.fromNamespaceAndPath("gunbow", gun.id());
        name = gun == null ? null : Component.literal(gun.name());
        if (save) {
            try {
                Files.writeString(file(), gun == null ? "" : gun.id());
            } catch (IOException e) {
                GunBowClient.LOGGER.warn("Could not write gunbow.txt", e);
            }
        }
    }

    public static Guns.Gun selected() { return selected; }
    public static Identifier modelId() { return modelId; }
    public static Component name() { return name; }

    private GunState() {}
}
