from django.urls import path
from . import views

app_name = 'tournament'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('grupos/', views.groups_view, name='groups'),
    path('grupos/predecir/<str:group_name>/', views.group_predict_view, name='group_predict'),
    path('eliminatorias/', views.bracket_view, name='bracket'),
    path('eliminatorias/predecir/<str:round_slug>/', views.round_predict_view, name='round_predict'),
    path('clasificacion/', views.leaderboard_view, name='leaderboard'),
    path('creditos/', views.credits_view, name='credits'),
]
