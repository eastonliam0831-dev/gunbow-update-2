package com.gunbow;

import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.ImageWidget;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;

/**
 * Gun picker: category tabs on top, gun list on the left, a live preview of the selected gun on the right,
 * Vanilla Bow / Done at the bottom.
 */
public class GunMenuScreen extends Screen {
    private static int category = 0;

    public GunMenuScreen() {
        super(Component.translatable("gunbow.menu.title"));
    }

    @Override
    protected void init() {
        int total = Math.min(this.width - 12, 400);
        int left = (this.width - total) / 2;
        int cx = this.width / 2;

        Button title = Button.builder(this.title, b -> {}).bounds(cx - 80, 6, 160, 20).build();
        title.active = false;
        this.addRenderableWidget(title);

        // category tabs
        int tabs = Guns.CATEGORIES.length, gap = 2;
        int tabW = (total - gap * (tabs - 1)) / tabs;
        for (int i = 0; i < tabs; i++) {
            final int idx = i;
            String name = Guns.CATEGORIES[i];
            Component label = Component.literal(i == category ? "[" + name + "]" : name);
            this.addRenderableWidget(Button.builder(label, b -> { category = idx; this.rebuildWidgets(); })
                    .bounds(left + i * (tabW + gap), 30, tabW, 20).build());
        }

        // gun list (2 columns) on the left
        int previewW = 160, previewH = 80;
        int colW = (total - previewW - 10) / 2;
        int col = 0, row = 0, rowH = 22;
        Guns.Gun current = GunState.selected();
        for (Guns.Gun g : Guns.ALL) {
            if (!g.category().equals(Guns.CATEGORIES[category])) continue;
            boolean on = current != null && current.id().equals(g.id());
            Component label = Component.literal((on ? "> " : "") + g.name());
            this.addRenderableWidget(Button.builder(label, b -> {
                GunState.set(g, true);
                this.rebuildWidgets();
            }).bounds(left + col * (colW + 2), 56 + row * rowH, colW, 20).build());
            if (++col == 2) { col = 0; row++; }
        }

        // preview of the selected gun on the right
        int px = left + total - previewW, py = 60;
        if (current != null) {
            Identifier tex = Identifier.fromNamespaceAndPath("gunbow", "textures/preview/" + current.id() + ".png");
            ImageWidget img = ImageWidget.texture(previewW, previewH, tex, previewW, previewH);
            img.setPosition(px, py);
            this.addRenderableWidget(img);
            Button name = Button.builder(Component.literal(current.name()), b -> {}).bounds(px, py + previewH + 4, previewW, 20).build();
            name.active = false;
            this.addRenderableWidget(name);
        } else {
            Button none = Button.builder(Component.translatable("gunbow.menu.default"), b -> {}).bounds(px, py + 30, previewW, 20).build();
            none.active = false;
            this.addRenderableWidget(none);
        }

        int by = this.height - 28;
        this.addRenderableWidget(Button.builder(Component.translatable("gunbow.menu.default"), b -> {
            GunState.set(null, true);
            this.rebuildWidgets();
        }).bounds(cx - 155, by, 150, 20).build());
        this.addRenderableWidget(Button.builder(Component.translatable("gunbow.menu.done"), b -> this.onClose())
                .bounds(cx + 5, by, 150, 20).build());
    }
}
