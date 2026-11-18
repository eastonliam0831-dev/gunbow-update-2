package com.gunbow.mixin;

import com.gunbow.GunState;
import net.minecraft.client.renderer.item.ItemModelResolver;
import net.minecraft.core.component.DataComponents;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

/**
 * Client-only: when the renderer is about to draw a bow, hand it a copy of the stack whose
 * item_model points at the selected gun. The real stack (and the server) is never touched.
 */
@Mixin(ItemModelResolver.class)
public abstract class ItemModelResolverMixin {

    @ModifyVariable(method = "appendItemLayers", at = @At("HEAD"), argsOnly = true, require = 0)
    private ItemStack gunbow$swapModel(ItemStack stack) {
        if (GunState.modelId() != null && stack.is(Items.BOW)) {
            ItemStack copy = stack.copy();
            copy.set(DataComponents.ITEM_MODEL, GunState.modelId());
            return copy;
        }
        return stack;
    }
}
