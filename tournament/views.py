import json
import hmac
import hashlib
import logging
import mercadopago

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import F, Sum
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Group, Round, Match, GroupPrediction, KnockoutPrediction, GroupResult, Team, CreditPackage, CreditPurchase
from .utils import get_group_team_multiplier

logger = logging.getLogger(__name__)


def home_view(request):
    groups = Group.objects.prefetch_related('teams').all()
    active_round = Round.objects.filter(is_active=True).order_by('order').first()
    top_users = (
        User.objects.filter(is_active=True, is_staff=False, is_superuser=False)
        .select_related('profile')
        .order_by(F('profile__total_points').desc(nulls_last=True))[:5]
    )

    user_group_preds = set()
    if request.user.is_authenticated:
        preds = GroupPrediction.objects.filter(user=request.user).values_list('group_id', flat=True)
        user_group_preds = set(preds)

    # World Cup champion (set once admin records the final match winner)
    world_cup_winner = None
    final_match = Match.objects.filter(
        round__slug='final', winner__isnull=False
    ).select_related('winner').first()
    if final_match:
        world_cup_winner = final_match.winner

    context = {
        'groups': groups,
        'active_round': active_round,
        'top_users': top_users,
        'user_group_preds': user_group_preds,
        'world_cup_winner': world_cup_winner,
    }
    return render(request, 'tournament/home.html', context)


def groups_view(request):
    groups = Group.objects.prefetch_related('teams', 'results__team').all()

    is_locked = False
    groups_round = Round.objects.filter(slug='groups').first()
    if groups_round:
        is_locked = groups_round.is_locked

    user_preds = {}
    if request.user.is_authenticated:
        preds = GroupPrediction.objects.filter(user=request.user).select_related(
            'predicted_first', 'predicted_second', 'predicted_third', 'group'
        )
        user_preds = {p.group_id: p for p in preds}

    groups_data = []
    for group in groups:
        pred = user_preds.get(group.id)
        all_teams = list(group.teams.all())  # already ordered by fifa_ranking

        if pred:
            ordered = []
            seen = set()
            for t in [pred.predicted_first, pred.predicted_second, pred.predicted_third]:
                if t is not None and t.id not in seen:
                    ordered.append(t)
                    seen.add(t.id)
            for t in all_teams:
                if t.id not in seen:
                    ordered.append(t)
                    seen.add(t.id)
        else:
            ordered = all_teams

        results_by_pos = {r.position: r.team for r in group.results.all()}
        groups_data.append({
            'group': group,
            'teams_ordered': ordered,
            'prediction': pred,
            'actual_first': results_by_pos.get(1),
            'actual_second': results_by_pos.get(2),
        })

    context = {
        'groups_data': groups_data,
        'is_locked': is_locked,
    }
    return render(request, 'tournament/groups.html', context)


@login_required
def group_predict_view(request, group_name):
    group = get_object_or_404(Group, name=group_name.upper())
    groups_round = Round.objects.filter(slug='groups').first()

    if groups_round and groups_round.is_locked:
        messages.warning(request, 'Las predicciones de la Fase de Grupos ya están cerradas.')
        return redirect('tournament:groups')

    existing = GroupPrediction.objects.filter(user=request.user, group=group).first()
    teams = list(group.teams.order_by('fifa_ranking'))
    user_credits = request.user.profile.credits

    # Mejores terceros usados globalmente (sin contar este grupo)
    thirds_count = GroupPrediction.objects.filter(
        user=request.user, predicted_third_advances=True
    ).exclude(group=group).count()
    thirds_remaining = max(0, 8 - thirds_count)

    # Multiplicadores por equipo
    mult_map = {t.id: get_group_team_multiplier(t) for t in teams}

    # Si ya existe predicción, ordenar equipos según el orden guardado
    if existing:
        ordered = []
        seen = set()
        for t in [existing.predicted_first, existing.predicted_second, existing.predicted_third]:
            if t is not None and t.id not in seen:
                ordered.append(t)
                seen.add(t.id)
        for t in teams:
            if t.id not in seen:
                ordered.append(t)
                seen.add(t.id)
        teams_data = [{'team': t, 'net_mult': mult_map[t.id]} for t in ordered]
    else:
        teams_data = [{'team': t, 'net_mult': mult_map[t.id]} for t in teams]

    GROUP_BET = 1000

    context = {
        'group': group,
        'teams_data': teams_data,
        'existing': existing,
        'user_credits': user_credits,
        'thirds_count': thirds_count,
        'thirds_remaining': thirds_remaining,
        'group_bet': GROUP_BET,
    }

    if request.method == 'POST':
        from django.db import transaction
        from accounts.models import UserProfile

        order_ids = [request.POST.get(f'order_{i}', '').strip() for i in range(1, 5)]

        if len(order_ids) != 4 or '' in order_ids or len(set(order_ids)) != 4:
            messages.error(request, 'Debes ordenar los 4 equipos del grupo.')
            return render(request, 'tournament/group_predict.html', context)

        group_team_ids = {str(t.id) for t in teams}
        if set(order_ids) != group_team_ids:
            messages.error(request, 'Equipos no válidos para este grupo.')
            return render(request, 'tournament/group_predict.html', context)

        third_advances = request.POST.get('third_advances') == '1'

        if third_advances and thirds_count >= 8:
            messages.error(request, 'Ya alcanzaste el límite de 8 mejores terceros seleccionados.')
            return render(request, 'tournament/group_predict.html', context)

        try:
            first_team  = Team.objects.get(id=order_ids[0])
            second_team = Team.objects.get(id=order_ids[1])
            third_team  = Team.objects.get(id=order_ids[2])
        except Team.DoesNotExist:
            messages.error(request, 'Equipo no válido.')
            return render(request, 'tournament/group_predict.html', context)

        new_bet = GROUP_BET
        old_bet = existing.bet_credits if existing else 0
        # Créditos disponibles = saldo actual + lo apostado previamente en este grupo (se devuelve)
        effective_available = user_credits + old_bet

        if new_bet > effective_available:
            messages.error(
                request,
                f'No tienes suficientes créditos. Necesitas {new_bet:,} crd para predecir este grupo.'
            )
            return render(request, 'tournament/group_predict.html', context)

        with transaction.atomic():
            profile = UserProfile.objects.select_for_update().get(user=request.user)

            if existing:
                existing.predicted_first = first_team
                existing.predicted_second = second_team
                existing.predicted_third = third_team
                existing.predicted_third_advances = third_advances
                existing.bet_credits = new_bet
                existing.points_earned = 0
                existing.credits_won = 0
                existing.is_scored = False
                existing.save()
                messages.success(request, f'Predicción del Grupo {group.name} actualizada.')
            else:
                GroupPrediction.objects.create(
                    user=request.user,
                    group=group,
                    predicted_first=first_team,
                    predicted_second=second_team,
                    predicted_third=third_team,
                    predicted_third_advances=third_advances,
                    bet_credits=new_bet,
                )
                messages.success(request, f'Predicción del Grupo {group.name} guardada.')

            # Aplicar cambio neto
            net_change = old_bet - new_bet
            profile.credits += net_change
            profile.save(update_fields=['credits'])

        return redirect('tournament:groups')

    return render(request, 'tournament/group_predict.html', context)


def bracket_view(request):
    rounds = Round.objects.exclude(slug='groups').order_by('order')
    rounds_data = []
    user_preds = set()

    preds_by_match = {}
    if request.user.is_authenticated:
        preds_qs = KnockoutPrediction.objects.filter(
            user=request.user
        ).select_related('predicted_winner')
        preds_by_match = {p.match_id: p for p in preds_qs}
        user_preds = set(preds_by_match.keys())

    for round_obj in rounds:
        matches = list(round_obj.matches.select_related('team1', 'team2', 'winner').order_by('match_number'))
        for match in matches:
            match.user_pred = preds_by_match.get(match.id)
        rounds_data.append({'round': round_obj, 'matches': matches})

    context = {'rounds_data': rounds_data, 'user_preds': user_preds}
    return render(request, 'tournament/bracket.html', context)


@login_required
def round_predict_view(request, round_slug):
    round_obj = get_object_or_404(Round, slug=round_slug)

    if round_obj.is_locked:
        messages.warning(request, f'Las predicciones de {round_obj.name} ya están cerradas.')
        return redirect('tournament:bracket')

    matches = round_obj.matches.select_related('team1', 'team2', 'winner').order_by('match_number')
    available_matches = [m for m in matches if m.team1 and m.team2 and '[SANDBOX]' not in (m.description or '')]

    existing_preds = {
        p.match_id: p for p in KnockoutPrediction.objects.filter(
            user=request.user, match__in=available_matches)
    }

    user_credits = request.user.profile.credits
    profile = request.user.profile
    boost_mult = profile.underdog_multiplier
    boost_uses = profile.underdog_boost_uses
    # Usos ya consumidos en TODOS los partidos (no solo esta ronda)
    boost_used = KnockoutPrediction.objects.filter(
        user=request.user, boost_applied=True).count()
    boost_remaining = max(0, boost_uses - boost_used)

    # Preparar datos por partido con puntos estimados
    matches_data = []
    base_pts = round_obj.base_points
    for match in available_matches:
        upset1 = max(0, (match.team1.fifa_ranking - match.team2.fifa_ranking) * 0.5)
        upset2 = max(0, (match.team2.fifa_ranking - match.team1.fifa_ranking) * 0.5)
        pts1 = base_pts + int(upset1)
        pts2 = base_pts + int(upset2)
        existing = existing_preds.get(match.id)
        matches_data.append({
            'match': match,
            'pts1': pts1,
            'pts2': pts2,
            'pts1_boosted': int(pts1 * boost_mult),
            'pts2_boosted': int(pts2 * boost_mult),
            'existing': existing,
        })

    ROUND_BET_CONFIG = {
        'r32':   {'min_bet': 500,  'bet_step': 500},
        'r16':   {'min_bet': 1000, 'bet_step': 1000},
        'qf':    {'min_bet': 1000, 'bet_step': 1000},
        'sf':    {'min_bet': 2000, 'bet_step': 2000},
        'final': {'min_bet': 2000, 'bet_step': 2000},
    }
    bet_cfg = ROUND_BET_CONFIG.get(round_obj.slug, {'min_bet': 500, 'bet_step': 500})
    min_bet = bet_cfg['min_bet']

    context = {
        'round': round_obj,
        'matches_data': matches_data,
        'user_credits': user_credits,
        'min_bet': min_bet,
        'bet_step': bet_cfg['bet_step'],
        'boost_mult': boost_mult,
        'boost_uses': boost_uses,
        'boost_remaining': boost_remaining,
    }

    if request.method == 'POST':
        from django.db import transaction
        from accounts.models import UserProfile

        # ── Parsear todas las predicciones del POST ───────────────────────────
        to_save = []
        boosts_requested = 0
        for md in matches_data:
            match = md['match']
            winner_id = request.POST.get(f'winner_{match.id}')
            if not winner_id:
                continue
            if str(match.team1.id) != winner_id and str(match.team2.id) != winner_id:
                continue
            try:
                winner_team = Team.objects.get(id=winner_id)
            except Team.DoesNotExist:
                continue
            raw_bet_str = request.POST.get(f'bet_{match.id}', '0') or '0'
            try:
                raw_bet = max(0, int(raw_bet_str))
            except (ValueError, TypeError):
                raw_bet = 0
            bet = max(raw_bet, min_bet)
            pred = existing_preds.get(match.id)
            old_bet = pred.bet_credits if pred else 0
            # Boost: checkbox en el form, solo si tiene usos disponibles
            wants_boost = bool(request.POST.get(f'boost_{match.id}'))
            # Si ya tenía boost aplicado, no cuenta como nuevo uso
            already_boosted = pred.boost_applied if pred else False
            if wants_boost and not already_boosted:
                boosts_requested += 1
            to_save.append({
                'match': match, 'winner_team': winner_team,
                'bet': bet, 'pred': pred, 'old_bet': old_bet,
                'wants_boost': wants_boost,
                'already_boosted': already_boosted,
            })

        if not to_save:
            messages.error(request, 'No se seleccionó ningún ganador.')
            return render(request, 'tournament/round_predict.html', context)

        # Validar que no supere los usos restantes de boost
        if boosts_requested > boost_remaining:
            messages.error(
                request,
                f'Solo tenés {boost_remaining} uso(s) de potenciador disponibles, '
                f'pero seleccionaste {boosts_requested}.'
            )
            return render(request, 'tournament/round_predict.html', context)

        total_old_bets = sum(p['old_bet'] for p in to_save)
        total_new_bets = sum(p['bet'] for p in to_save)
        # Créditos disponibles = saldo actual + lo que ya estaba apostado (se devuelve)
        effective_available = user_credits + total_old_bets

        if total_new_bets > effective_available:
            messages.error(
                request,
                f'No tienes suficientes créditos. '
                f'Disponible: {effective_available:,} · Apuesta total: {total_new_bets:,}'
            )
            return render(request, 'tournament/round_predict.html', context)

        with transaction.atomic():
            # Bloquear perfil para evitar condiciones de carrera
            profile = UserProfile.objects.select_for_update().get(user=request.user)

            saved = 0
            for p in to_save:
                apply_boost = p['wants_boost'] and (p['already_boosted'] or boosts_requested <= boost_remaining)
                if p['pred']:
                    p['pred'].predicted_winner = p['winner_team']
                    p['pred'].bet_credits = p['bet']
                    p['pred'].boost_applied = apply_boost
                    p['pred'].points_earned = 0
                    p['pred'].credits_won = 0
                    p['pred'].is_correct = None
                    p['pred'].save()
                else:
                    KnockoutPrediction.objects.create(
                        user=request.user, match=p['match'],
                        predicted_winner=p['winner_team'], bet_credits=p['bet'],
                        boost_applied=apply_boost,
                    )
                saved += 1

            # Aplicar cambio neto de créditos: devolver apuestas viejas, cobrar nuevas
            net_change = total_old_bets - total_new_bets
            profile.credits += net_change
            profile.save(update_fields=['credits'])

        messages.success(
            request,
            f'{saved} predicción(es) guardada(s) para {round_obj.name}. '
            f'Saldo descontado: {total_new_bets:,} crd.'
        )
        return redirect('tournament:bracket')

    return render(request, 'tournament/round_predict.html', context)


def leaderboard_view(request):
    from django.core.paginator import Paginator

    users = (
        User.objects.filter(is_active=True, is_staff=False, is_superuser=False)
        .select_related('profile')
        .order_by(F('profile__total_points').desc(nulls_last=True), 'username')
    )

    paginator = Paginator(users, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    user_rank = None
    if request.user.is_authenticated and not request.user.is_staff and not request.user.is_superuser:
        better_count = User.objects.filter(
            is_active=True, is_staff=False, is_superuser=False,
            profile__total_points__gt=request.user.profile.total_points,
        ).count()
        user_rank = better_count + 1

    # ── Premio ────────────────────────────────────────────────────────────────
    # Comisión real de MercadoPago Colombia: 3.29% + IVA (19%) + 952 COP fijo
    MP_FEE_RATE  = 0.039151   # 3.29% × 1.19
    MP_FEE_FIXED = 952        # COP fijos por transacción

    # Del dinero que llega neto a la cuenta, qué % se queda la plataforma
    # El resto (1 - PLATFORM_CUT) va al pozo de premios
    PLATFORM_CUT = 0.35       # 35 % del neto para la plataforma

    purchases_qs    = CreditPurchase.objects.filter(status='completed')
    total_gross     = purchases_qs.aggregate(total=Sum('cop_paid'))['total'] or 0
    n_purchases     = purchases_qs.count()

    # Neto real que llega a la cuenta después de fees de MP
    total_net = max(0, total_gross * (1 - MP_FEE_RATE) - MP_FEE_FIXED * n_purchases)

    prize_pool = int(total_net * (1 - PLATFORM_CUT))   # 65 % del neto
    prizes = {
        1: int(prize_pool * 0.50),
        2: int(prize_pool * 0.30),
        3: int(prize_pool * 0.20),
    }

    top3 = list(users[:3])

    # Tournament finished flag + World Cup champion
    world_cup_winner = None
    final_match = Match.objects.filter(
        round__slug='final', winner__isnull=False
    ).select_related('winner').first()
    if final_match:
        world_cup_winner = final_match.winner
    tournament_finished = bool(world_cup_winner)

    return render(request, 'tournament/leaderboard.html', {
        'page_obj': page_obj,
        'user_rank': user_rank,
        'top3': top3,
        'top1': top3[0] if len(top3) >= 1 else None,
        'top2': top3[1] if len(top3) >= 2 else None,
        'top3_user': top3[2] if len(top3) >= 3 else None,
        'prizes': prizes,
        'prize_pool': prize_pool,
        'total_collected': total_gross,
        'tournament_finished': tournament_finished,
        'world_cup_winner': world_cup_winner,
    })


@login_required
def credits_view(request):
    profile = request.user.profile

    # Apuestas activas (sin resultado aún)
    active_group_bets = GroupPrediction.objects.filter(
        user=request.user, bet_credits__gt=0, is_scored=False
    ).select_related('group', 'predicted_first', 'predicted_second')

    active_knockout_bets = KnockoutPrediction.objects.filter(
        user=request.user, bet_credits__gt=0, is_correct__isnull=True
    ).select_related('match__round', 'predicted_winner', 'match__team1', 'match__team2')

    # Historial de apuestas resueltas
    history_group = GroupPrediction.objects.filter(
        user=request.user, is_scored=True, bet_credits__gt=0
    ).select_related('group', 'predicted_first', 'predicted_second').order_by('-id')

    history_knockout = KnockoutPrediction.objects.filter(
        user=request.user, is_correct__isnull=False, bet_credits__gt=0
    ).select_related('match__round', 'predicted_winner').order_by('-id')

    # Créditos totales apostados en apuestas activas
    active_group_sum = active_group_bets.aggregate(t=Sum('bet_credits'))['t'] or 0
    active_knockout_sum = active_knockout_bets.aggregate(t=Sum('bet_credits'))['t'] or 0
    total_in_play = active_group_sum + active_knockout_sum

    context = {
        'profile': profile,
        'active_group_bets': active_group_bets,
        'active_knockout_bets': active_knockout_bets,
        'history_group': history_group,
        'history_knockout': history_knockout,
        'total_in_play': total_in_play,
    }
    return render(request, 'tournament/credits.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de Mercado Pago
# ─────────────────────────────────────────────────────────────────────────────

def _mp_sdk():
    """Devuelve una instancia del SDK con el Access Token configurado."""
    return mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)


def _apply_payment(payment_id):
    """
    Consulta el pago en la API de MP y, si está aprobado, acredita los créditos.
    Idempotente: no hace nada si el purchase ya fue procesado.
    """
    try:
        sdk = _mp_sdk()
        resp = sdk.payment().get(str(payment_id))
        if resp["status"] != 200:
            logger.warning("MP payment %s → HTTP %s", payment_id, resp["status"])
            return

        payment = resp["response"]
        mp_status = payment.get("status")
        external_ref = payment.get("external_reference", "")

        purchase = CreditPurchase.objects.select_for_update().get(
            id=int(external_ref)
        )

        if purchase.status != 'pending':
            # Ya fue procesado (idempotencia)
            return

        purchase.mp_payment_id = str(payment_id)

        if mp_status == 'approved':
            purchase.status = 'completed'
            purchase.save(update_fields=['status', 'mp_payment_id'])
            profile = purchase.user.profile
            profile.credits += purchase.credits_applied
            profile.save(update_fields=['credits'])
            logger.info("Créditos aplicados: %s → %s crd", purchase.user, purchase.credits_applied)
        elif mp_status in ('rejected', 'cancelled'):
            purchase.status = 'cancelled'
            purchase.save(update_fields=['status', 'mp_payment_id'])
        else:
            # in_process, authorized, etc.
            purchase.save(update_fields=['mp_payment_id'])

    except (CreditPurchase.DoesNotExist, ValueError):
        logger.warning("No se encontró CreditPurchase para external_reference=%s", payment_id)
    except Exception as exc:
        logger.exception("Error al procesar pago MP %s: %s", payment_id, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Vistas de créditos
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def buy_credits_view(request):
    all_packages = CreditPackage.objects.filter(is_active=True).select_related('requires_round').order_by('order', 'cop_price')
    purchase_history = CreditPurchase.objects.filter(
        user=request.user
    ).select_related('package').order_by('-created_at')[:15]

    # Nombres de paquetes ya comprados (pagos completados)
    bought_names = set(
        CreditPurchase.objects.filter(user=request.user, status='completed')
        .values_list('package__name', flat=True)
    )

    # Reglas de visibilidad:
    # - Compró "Pase Completo" → no mostrar ningún paquete
    # - Compró "Fase de Grupos" → no mostrar "Pase Completo", solo "Pase Eliminatorias"
    # - No compró nada → mostrar todos
    if 'Pase Completo' in bought_names:
        packages = all_packages.none()
    elif 'Fase de Grupos' in bought_names:
        packages = all_packages.exclude(name__in=['Fase de Grupos', 'Pase Completo'])
    else:
        packages = all_packages

    if request.method == 'POST':
        package_id = request.POST.get('package_id')
        try:
            package = CreditPackage.objects.select_related('requires_round').get(id=package_id, is_active=True)
        except CreditPackage.DoesNotExist:
            messages.error(request, 'Paquete no válido.')
            return redirect('tournament:buy_credits')

        if not package.is_available:
            messages.error(
                request,
                f'El paquete «{package.name}» solo está disponible cuando '
                f'la fase «{package.requires_round.name}» esté activa.'
            )
            return redirect('tournament:buy_credits')

        if not settings.MERCADOPAGO_ACCESS_TOKEN:
            messages.error(request, 'Los pagos no están configurados aún. Contacta al administrador.')
            return redirect('tournament:buy_credits')

        # Crear registro pendiente
        purchase = CreditPurchase.objects.create(
            user=request.user,
            package=package,
            credits_applied=package.total_credits,
            cop_paid=package.cop_price,
            status='pending',
        )

        # Crear preferencia en Mercado Pago
        try:
            sdk = _mp_sdk()
            is_public_url = request.get_host() not in ('localhost', '127.0.0.1', 'localhost:8000', '127.0.0.1:8000')
            preference_data = {
                "items": [{
                    "id": str(package.id),
                    "title": f"CopaBet 26 — {package.name}",
                    "quantity": 1,
                    "unit_price": float(package.cop_price),
                    "currency_id": "COP",
                }],
                "back_urls": {
                    "success": request.build_absolute_uri(reverse('tournament:mp_success')),
                    "failure": request.build_absolute_uri(reverse('tournament:mp_failure')),
                    "pending": request.build_absolute_uri(reverse('tournament:mp_pending')),
                },
                "external_reference": str(purchase.id),
            }
            if is_public_url:
                # Redirección automática tras pago aprobado + webhook para notificaciones
                preference_data["auto_return"] = "approved"
                preference_data["notification_url"] = request.build_absolute_uri(reverse('tournament:mp_webhook'))
            pref_resp = sdk.preference().create(preference_data)
            preference = pref_resp["response"]

            if "error" in preference or "id" not in preference:
                raise ValueError(f"MP error: {preference.get('message', preference)}")

            purchase.mp_preference_id = preference["id"]
            purchase.save(update_fields=['mp_preference_id'])

            # URLs públicas → init_point real; localhost → sandbox_init_point
            checkout_url = preference.get(
                "init_point" if is_public_url else "sandbox_init_point"
            )
            return redirect(checkout_url)

        except Exception as exc:
            logger.exception("Error creando preferencia MP: %s", exc)
            purchase.status = 'cancelled'
            purchase.save(update_fields=['status'])
            messages.error(request, 'Error al conectar con Mercado Pago. Intenta de nuevo.')
            return redirect('tournament:buy_credits')

    context = {
        'packages': packages,
        'purchase_history': purchase_history,
        'profile': request.user.profile,
    }
    return render(request, 'tournament/buy_credits.html', context)


@login_required
def mp_success_view(request):
    """El usuario regresa aquí tras pago aprobado en MP."""
    payment_id = request.GET.get('payment_id') or request.GET.get('collection_id')
    external_ref = request.GET.get('external_reference')

    purchase = None
    if external_ref:
        try:
            purchase = CreditPurchase.objects.select_related('package').get(
                id=int(external_ref), user=request.user
            )
        except (CreditPurchase.DoesNotExist, ValueError):
            pass

    # Si tenemos payment_id y aún está pendiente, procesar ahora mismo
    if purchase and purchase.status == 'pending':
        from django.db import transaction
        if payment_id:
            with transaction.atomic():
                _apply_payment(payment_id)
            purchase.refresh_from_db()
        elif purchase.mp_preference_id:
            # Sin payment_id en la URL: buscar el pago via API de MP por preference_id
            try:
                sdk = _mp_sdk()
                resp = sdk.preference().get(purchase.mp_preference_id)
                if resp.get('status') == 200:
                    # Buscar pagos asociados a esta preferencia
                    search = sdk.payment().search({
                        'filters': {'external_reference': str(purchase.id)}
                    })
                    if search.get('status') == 200:
                        results = search['response'].get('results', [])
                        if results:
                            mp_pid = results[0].get('id')
                            if mp_pid:
                                with transaction.atomic():
                                    _apply_payment(mp_pid)
                                purchase.refresh_from_db()
            except Exception:
                pass

    return render(request, 'tournament/mp_success.html', {'purchase': purchase})


@login_required
def mp_failure_view(request):
    """El usuario regresa aquí si el pago fue rechazado."""
    external_ref = request.GET.get('external_reference')
    purchase = None
    if external_ref:
        try:
            purchase = CreditPurchase.objects.select_related('package').get(
                id=int(external_ref), user=request.user
            )
            if purchase.status == 'pending':
                purchase.status = 'cancelled'
                purchase.save(update_fields=['status'])
        except (CreditPurchase.DoesNotExist, ValueError):
            pass
    return render(request, 'tournament/mp_failure.html', {'purchase': purchase})


@login_required
def mp_pending_view(request):
    """El usuario regresa aquí si el pago está en proceso (ej: pago en efectivo)."""
    external_ref = request.GET.get('external_reference')
    purchase = None
    if external_ref:
        try:
            purchase = CreditPurchase.objects.select_related('package').get(
                id=int(external_ref), user=request.user
            )
        except (CreditPurchase.DoesNotExist, ValueError):
            pass
    return render(request, 'tournament/mp_pending.html', {'purchase': purchase})


@csrf_exempt
@require_POST
def mp_webhook_view(request):
    """
    Webhook de Mercado Pago. Recibe notificaciones de pagos.
    Verifica la firma HMAC-SHA256 si MERCADOPAGO_WEBHOOK_SECRET está configurado.
    """
    # ── Verificación de firma ─────────────────────────────────────────────────
    webhook_secret = settings.MERCADOPAGO_WEBHOOK_SECRET
    if not webhook_secret:
        logger.warning("Webhook MP: sin verificación de firma (MERCADOPAGO_WEBHOOK_SECRET no definido).")
    else:
        x_signature = request.headers.get('x-signature', '')
        x_request_id = request.headers.get('x-request-id', '')
        data_id = request.GET.get('data.id', '')

        ts = ''
        v1 = ''
        for part in x_signature.split(','):
            key, _, value = part.partition('=')
            key = key.strip()
            if key == 'ts':
                ts = value.strip()
            elif key == 'v1':
                v1 = value.strip()

        signed_template = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
        expected = hmac.new(
            webhook_secret.encode(),
            signed_template.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, v1):
            logger.warning("Firma MP inválida. Webhook rechazado.")
            return HttpResponse(status=401)

    # ── Parsear cuerpo ────────────────────────────────────────────────────────
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponse(status=400)

    event_type = body.get('type') or request.GET.get('type', '')
    if event_type == 'payment':
        payment_id = (
            body.get('data', {}).get('id')
            or request.GET.get('data.id')
            or request.GET.get('id')
        )
        if payment_id:
            from django.db import transaction
            with transaction.atomic():
                _apply_payment(payment_id)

    return HttpResponse(status=200)


def underdog_info_view(request):
    from django.contrib.auth.models import User
    avg_points = None
    users = User.objects.filter(profile__total_points__gt=0).select_related('profile')
    if users.exists():
        total = sum(u.profile.total_points for u in users)
        avg_points = total / users.count()
    return render(request, 'tournament/info.html', {'avg_points': avg_points, 'cur': 'info'})


def manifest_view(request):
    """PWA Web App Manifest"""
    base = request.build_absolute_uri('/')[:-1]
    manifest = {
        "name": "CopaBet 26",
        "short_name": "CopaBet26",
        "description": "Predice el FIFA World Cup 2026 y gana créditos.",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#070F1C",
        "theme_color": "#070F1C",
        "orientation": "portrait",
        "scope": "/",
        "icons": [
            {
                "src": f"{base}/static/tournament/img/wc2026-logo.webp",
                "sizes": "192x192",
                "type": "image/webp",
                "purpose": "any maskable"
            },
            {
                "src": f"{base}/static/tournament/img/wc2026-logo.webp",
                "sizes": "512x512",
                "type": "image/webp",
                "purpose": "any maskable"
            }
        ],
        "shortcuts": [
            {"name": "Grupos",        "url": "/grupos/",        "description": "Predicciones de grupos"},
            {"name": "Eliminatorias", "url": "/eliminatorias/", "description": "Bracket eliminatorio"},
            {"name": "Clasificación", "url": "/clasificacion/", "description": "Tabla de posiciones"},
        ]
    }
    return JsonResponse(manifest, content_type='application/manifest+json')
