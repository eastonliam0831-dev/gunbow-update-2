package com.gunbow.mixin;

import com.gunbow.GunState;
import net.minecraft.core.component.DataComponents;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Client-only: shows the selected gun's name for bows (hover, tooltip, held-item popup). */
@Mixin(ItemStack.class)
public abstract class ItemStackMixin {

    @Inject(method = "getHoverName", at = @At("HEAD"), cancellable = true, require = 0)
    private void gunbow$name(CallbackInfoReturnable<Component> cir) {
        if (GunState.name() == null) return;
        ItemStack self = (ItemStack) (Object) this;
        if (self.is(Items.BOW) && self.get(DataComponents.CUSTOM_NAME) == null) cir.setReturnValue(GunState.name());
    }
}
