from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import UserProfile, Referral


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Perfil'
    readonly_fields = ('promo_code',)
    fields = ('full_name', 'phone_number', 'credits', 'total_points', 'promo_code')


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'get_credits', 'get_promo_code', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active')

    def get_credits(self, obj):
        try:
            return obj.profile.credits
        except UserProfile.DoesNotExist:
            return 0
    get_credits.short_description = 'Créditos'
    get_credits.admin_order_field = 'profile__credits'

    def get_promo_code(self, obj):
        try:
            return obj.profile.promo_code
        except UserProfile.DoesNotExist:
            return '-'
    get_promo_code.short_description = 'Código promo'


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = (
        'referrer', 'referred', 'get_referred_credits',
        'signup_reward_given', 'referred_signup_reward_given', 'created_at',
    )
    list_filter = ('signup_reward_given', 'referred_signup_reward_given')
    readonly_fields = ('referrer', 'referred', 'created_at')

    def get_referred_credits(self, obj):
        try:
            return obj.referred.profile.credits
        except Exception:
            return 0
    get_referred_credits.short_description = 'Créditos del referido'


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
