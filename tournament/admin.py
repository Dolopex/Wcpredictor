from django.contrib import admin
from django.utils.html import format_html
from .models import Team, Group, Round, Match, GroupResult, GroupPrediction, KnockoutPrediction


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

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.winner:
            from .signals import score_knockout_predictions
            score_knockout_predictions(obj)


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
