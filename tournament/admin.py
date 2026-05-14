from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import path
from django.utils.html import format_html
from .models import (
    Team, Group, Round, Match, GroupResult,
    GroupPrediction, KnockoutPrediction,
    CreditPackage, CreditPurchase, SandboxLog,
)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('flag_emoji', 'name', 'code', 'confederation', 'fifa_ranking')
    list_filter = ('confederation',)
    search_fields = ('name', 'code')
    ordering = ('fifa_ranking',)


class GroupResultInline(admin.TabularInline):
    model = GroupResult
    extra = 0
    fields = ('team', 'position', 'is_advancing')


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'team_list')
    filter_horizontal = ('teams',)
    inlines = [GroupResultInline]

    def team_list(self, obj):
        return ', '.join(t.name for t in obj.teams.all())
    team_list.short_description = 'Equipos'


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ('name', 'order', 'base_points', 'is_active', 'is_locked')
    list_editable = ('is_active', 'is_locked')


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('round', 'match_number', 'team1', 'team2', 'winner', 'match_date')
    list_filter = ('round',)
    list_editable = ('winner',)
    raw_id_fields = ('team1', 'team2', 'winner')
    ordering = ('round__order', 'match_number')
    actions = ['action_reset_all_results']

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.winner:
            from .signals import score_knockout_predictions
            score_knockout_predictions(obj)

    def action_reset_all_results(self, request, queryset):
        """Reset completo: borra ganadores, resetea predicciones y puntos de todos los usuarios reales."""
        from .sandbox import reset_test_data
        try:
            result = reset_test_data()
            self.message_user(
                request,
                "Reset completo OK: {} ganadores borrados, {} pred. eliminatorias reseteadas, "
                "{} pred. grupos reseteadas, {} perfiles a 0 pts.".format(
                    result['cleared_winners'], result['reset_knockout'],
                    result['reset_groups'], result['reset_profiles'],
                ),
                messages.SUCCESS,
            )
        except Exception as exc:
            self.message_user(request, "Error en reset: {}".format(exc), messages.ERROR)

    action_reset_all_results.short_description = "⚠️ RESET COMPLETO: borrar ganadores, pred. y puntos"


@admin.register(GroupResult)
class GroupResultAdmin(admin.ModelAdmin):
    list_display = ('group', 'position', 'team', 'is_advancing')
    list_filter = ('group',)
    ordering = ('group__name', 'position')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from .signals import score_group_predictions
        score_group_predictions(obj.group)


@admin.register(GroupPrediction)
class GroupPredictionAdmin(admin.ModelAdmin):
    list_display = ('user', 'group', 'predicted_first', 'predicted_second', 'points_earned', 'is_scored')
    list_filter = ('group', 'is_scored')
    search_fields = ('user__username',)


@admin.register(KnockoutPrediction)
class KnockoutPredictionAdmin(admin.ModelAdmin):
    list_display = ('user', 'match', 'predicted_winner', 'points_earned', 'is_correct')
    list_filter = ('match__round', 'is_correct')
    search_fields = ('user__username',)


@admin.register(CreditPackage)
class CreditPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'cop_price_formatted', 'credits_amount', 'bonus_credits', 'total_credits', 'is_featured', 'is_active', 'order')
    list_editable = ('is_active', 'is_featured', 'order')
    list_display_links = ('name',)
    ordering = ('order', 'cop_price')

    def cop_price_formatted(self, obj):
        return obj.cop_price_formatted
    cop_price_formatted.short_description = 'Precio COP'

    def total_credits(self, obj):
        return obj.total_credits
    total_credits.short_description = 'Total creditos'


@admin.register(CreditPurchase)
class CreditPurchaseAdmin(admin.ModelAdmin):
    list_display = ('user', 'package', 'credits_applied', 'cop_paid', 'status', 'created_at')
    list_filter = ('status', 'package')
    search_fields = ('user__username',)
    readonly_fields = ('user', 'package', 'credits_applied', 'cop_paid', 'created_at')
    ordering = ('-created_at',)


# -- Area de Pruebas (Sandbox) --------------------------------------------------

@admin.register(SandboxLog)
class SandboxLogAdmin(admin.ModelAdmin):
    change_list_template = 'admin/tournament/sandboxlog/change_list.html'
    list_display = ('created_at', 'action_badge', 'n_users', 'notes')
    readonly_fields = ('action', 'n_users', 'notes', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def action_badge(self, obj):
        color = '#4CAF50' if obj.action == 'generate' else '#F44336'
        label = obj.get_action_display()
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:bold;">{}</span>',
            color, label,
        )
    action_badge.short_description = 'Accion'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                'run/',
                self.admin_site.admin_view(self.sandbox_action_view),
                name='tournament_sandbox_run',
            ),
        ]
        return custom + urls

    def sandbox_action_view(self, request):
        from .sandbox import generate_test_data, reset_test_data

        if request.method != 'POST':
            return HttpResponseRedirect('../')

        action = request.POST.get('sandbox_action', '')

        if action == 'generate':
            try:
                n = max(1, min(50, int(request.POST.get('n_users', 10))))
            except (ValueError, TypeError):
                n = 10
            try:
                result = generate_test_data(n)
                SandboxLog.objects.create(
                    action='generate',
                    n_users=n,
                    notes=(
                        "Bots: {} | Grupos: {} | Eliminatorias: {} | Resultados: {}".format(
                            result['n_users'], result['n_group_preds'],
                            result['n_knockout_preds'], result['n_group_results'],
                        )
                    ),
                )
                messages.success(
                    request,
                    "Generados: {} bots, {} pred. grupos, {} pred. eliminatorias.".format(
                        n, result['n_group_preds'], result['n_knockout_preds'],
                    ),
                )
            except Exception as exc:
                messages.error(request, "Error al generar: {}".format(exc))

        elif action == 'reset':
            try:
                result = reset_test_data()
                SandboxLog.objects.create(
                    action='reset',
                    notes="Bots: {} | Matches sandbox: {} | Resultados grupo: {} | Winners borrados: {} | Pred. elim. reset: {} | Pred. grupos reset: {} | Perfiles reset: {}".format(
                        result['deleted_users'], result['deleted_matches'], result['deleted_results'],
                        result['cleared_winners'], result['reset_knockout'],
                        result['reset_groups'], result['reset_profiles'],
                    ),
                )
                messages.success(
                    request,
                    "Reset completo: {} bots eliminados, {} ganadores borrados, "
                    "{} pred. eliminatorias reseteadas, {} pred. grupos reseteadas, "
                    "{} perfiles a 0 pts.".format(
                        result['deleted_users'], result['cleared_winners'],
                        result['reset_knockout'], result['reset_groups'],
                        result['reset_profiles'],
                    ),
                )
            except Exception as exc:
                messages.error(request, "Error al resetear: {}".format(exc))

        return HttpResponseRedirect('../')

    def changelist_view(self, request, extra_context=None):
        from .sandbox import sandbox_stats
        extra_context = extra_context or {}
        extra_context['sandbox_stats'] = sandbox_stats()
        return super().changelist_view(request, extra_context=extra_context)
