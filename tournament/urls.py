from django.urls import path
from . import views
from . import admin_views

app_name = 'tournament'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('grupos/', views.groups_view, name='groups'),
    path('grupos/predecir/<str:group_name>/', views.group_predict_view, name='group_predict'),
    path('eliminatorias/', views.bracket_view, name='bracket'),
    path('eliminatorias/predecir/<str:round_slug>/', views.round_predict_view, name='round_predict'),
    path('clasificacion/', views.leaderboard_view, name='leaderboard'),
    path('creditos/', views.credits_view, name='credits'),
    path('creditos/comprar/', views.buy_credits_view, name='buy_credits'),
    # Mercado Pago — retornos y webhook
    path('creditos/comprar/exito/', views.mp_success_view, name='mp_success'),
    path('creditos/comprar/fallido/', views.mp_failure_view, name='mp_failure'),
    path('creditos/comprar/pendiente/', views.mp_pending_view, name='mp_pending'),
    path('creditos/webhook/mp/', views.mp_webhook_view, name='mp_webhook'),
    # PWA
    path('manifest.json', views.manifest_view, name='manifest'),
    path('info/', views.underdog_info_view, name='info'),
    # ── Panel de administración ───────────────────────────────────────────────
    path('panel/', admin_views.panel_home, name='panel_home'),
    path('panel/usuarios/', admin_views.panel_users, name='panel_users'),
    path('panel/usuarios/<int:user_id>/', admin_views.panel_user_detail, name='panel_user_detail'),
    path('panel/rondas/', admin_views.panel_rounds, name='panel_rounds'),
    path('panel/partidos/', admin_views.panel_matches, name='panel_matches'),
    path('panel/grupos/', admin_views.panel_groups, name='panel_groups'),
    path('panel/simulador/', admin_views.panel_simulate, name='panel_simulate'),
]
